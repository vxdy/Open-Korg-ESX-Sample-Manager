import os
from enum import IntEnum

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QFormLayout, QComboBox, QLineEdit,
    QDoubleSpinBox, QSpinBox, QLabel, QHeaderView, QAbstractItemView,
    QPushButton, QMessageBox, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal

from esx.constants import (
    AmpEg, BpmSync, Beat, FilterType, FxChain, FxSelect, FxSend,
    FxType, LastStep, ModDest, ModType, PATTERN_PART_NAMES,
    PatternLength, Reverse, Roll, RollType, Swing
)
from esx.pattern import Pattern
from esx.pattern_transfer import export_pattern, import_pattern
from esx.app_paths import get_patterns_dir
from ui.error_log import report_error
from ui import icons


PART_FIELD_SPECS = [
    ("Part", None, "label", None),
    ("Sample", "sample_pointer", "sample", None),
    ("Level", "level", "int", None),
    ("Pan", "pan", "int", None),
    ("Pitch", "pitch", "int", None),
    ("Glide", "glide", "int", None),
    ("Filter", "filter_type", "enum", FilterType),
    ("Cutoff", "cutoff", "int", None),
    ("Resonance", "resonance", "int", None),
    ("EG Intensity", "eg_intensity", "int", None),
    ("EG Time", "eg_time", "int", None),
    ("Start Point", "start_point", "int", None),
    ("FX Select", "fx_select", "enum", FxSelect),
    ("FX Send", "fx_send", "enum", FxSend),
    ("Roll", "roll", "enum", Roll),
    ("Amp EG", "amp_eg", "enum", AmpEg),
    ("Reverse", "reverse", "enum", Reverse),
    ("Mod Dest", "mod_dest", "enum", ModDest),
    ("Mod Type", "mod_type", "enum", ModType),
    ("BPM Sync", "bpm_sync", "enum", BpmSync),
    ("Mod Speed", "mod_speed", "int", None),
    ("Mod Depth", "mod_depth", "int", None),
    ("Motion Seq", "motion_sequence_status", "int", None),
    ("Slice No.", "slice_number", "int", None),
    ("Reserved Byte", "reserved_byte", "int", None),
    ("Reserved Reverse", "reserved_bits_after_reverse", "int", None),
    ("Reserved Mod", "reserved_bit_after_mod_depth", "int", None),
    ("Reserved Byte 7", "reserved_bits_byte7", "int", None),
]

INT_RANGES = {
    "sample_pointer": (-1, 383),
    "cutoff": (-128, 127),
    "eg_intensity": (-64, 63),
    "pitch": (-64, 63),
    "pan": (-64, 63),
    "mod_speed": (-128, 127),
    "mod_depth": (-128, 127),
    "slice_number": (-128, 127),
    "level": (0, 127),
    "glide": (0, 127),
    "resonance": (0, 127),
    "eg_time": (0, 127),
    "start_point": (0, 127),
    "motion_sequence_status": (0, 255),
    "reserved_byte": (0, 255),
    "reserved_bits_after_reverse": (0, 3),
    "reserved_bit_after_mod_depth": (0, 1),
    "reserved_bits_byte7": (0, 7),
}


PATTERN_FILE_MIME_TYPE = "application/x-esx-pattern-file"


class PatternTable(QTableWidget):
    """Pattern list where dragging one row onto another swaps their
    contents. An ESX pattern "slot" is a fixed hardware address, so
    reordering here is implemented as a two-slot swap rather than a shift.

    Also accepts drops originating from the Pattern Browser (a saved
    .esxpat file dragged onto a row), which are reported separately via
    pattern_file_drop_requested rather than being treated as a swap."""

    swap_requested = pyqtSignal(int, int)
    pattern_file_drop_requested = pyqtSignal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)

    def _accepts(self, event) -> bool:
        return event.source() is self or event.mimeData().hasFormat(PATTERN_FILE_MIME_TYPE)

    def dragEnterEvent(self, event):
        if self._accepts(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._accepts(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        target_index = self.indexAt(event.position().toPoint())
        dst_row = target_index.row()
        if dst_row < 0:
            dst_row = self.rowCount() - 1

        if event.source() is self:
            src_row = self.currentRow()
            if src_row >= 0 and dst_row >= 0 and src_row != dst_row:
                self.swap_requested.emit(src_row, dst_row)
            event.acceptProposedAction()
            return

        mime = event.mimeData()
        if mime.hasFormat(PATTERN_FILE_MIME_TYPE) and dst_row >= 0:
            filepath = bytes(mime.data(PATTERN_FILE_MIME_TYPE)).decode("utf-8")
            self.pattern_file_drop_requested.emit(filepath, dst_row)
            event.acceptProposedAction()
            return

        event.ignore()


class TabPatterns(QWidget):
    def __init__(self):
        super().__init__()
        self._esx = None
        self._current_pattern = None
        self._current_row = -1
        self._part_rows = []
        self._clipboard_pattern_bytes = None
        self._clipboard_pattern_label = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        hint = QLabel("Patterns (256) — drag a row onto another to swap slots")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9aa0a8; font-size: 11px;")
        left_layout.addWidget(hint)
        self._pattern_table = PatternTable()
        self._pattern_table.setColumnCount(3)
        self._pattern_table.setHorizontalHeaderLabels(["#", "Name", "Tempo"])
        self._pattern_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._pattern_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._pattern_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._pattern_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._pattern_table.verticalHeader().setVisible(False)
        self._pattern_table.setAlternatingRowColors(True)
        self._pattern_table.selectionModel().selectionChanged.connect(self._on_pattern_selected)
        self._pattern_table.swap_requested.connect(self._on_pattern_swap_requested)
        self._pattern_table.pattern_file_drop_requested.connect(self._on_pattern_file_dropped)
        left_layout.addWidget(self._pattern_table)

        copy_paste_layout = QHBoxLayout()
        self._copy_pattern_btn = QPushButton(icons.icon("copy"), "Copy Pattern")
        self._paste_pattern_btn = QPushButton(icons.icon("paste"), "Paste Pattern")
        self._paste_pattern_btn.setEnabled(False)
        self._copy_pattern_btn.clicked.connect(self._copy_pattern)
        self._paste_pattern_btn.clicked.connect(self._paste_pattern)
        copy_paste_layout.addWidget(self._copy_pattern_btn)
        copy_paste_layout.addWidget(self._paste_pattern_btn)
        left_layout.addLayout(copy_paste_layout)

        self._clipboard_label = QLabel("Clipboard: (empty)")
        self._clipboard_label.setStyleSheet("color: #9aa0a8; font-size: 11px;")
        left_layout.addWidget(self._clipboard_label)

        transfer_layout = QHBoxLayout()
        self._export_pattern_btn = QPushButton(icons.icon("file-export"), "Export Pattern")
        self._import_pattern_btn = QPushButton(icons.icon("file-import"), "Import Pattern...")
        self._export_pattern_btn.clicked.connect(self._export_pattern)
        self._import_pattern_btn.clicked.connect(self._import_pattern)
        transfer_layout.addWidget(self._export_pattern_btn)
        transfer_layout.addWidget(self._import_pattern_btn)
        left_layout.addLayout(transfer_layout)

        splitter.addWidget(left_widget)

        self._right_tabs = QTabWidget()

        editor_widget = QWidget()
        editor_layout = QFormLayout(editor_widget)
        editor_layout.setSpacing(10)
        editor_layout.setContentsMargins(16, 16, 16, 16)

        self._name_edit = QLineEdit()
        self._name_edit.setMaxLength(8)
        editor_layout.addRow("Name:", self._name_edit)

        self._tempo_spin = QDoubleSpinBox()
        self._tempo_spin.setRange(20.0, 300.0)
        self._tempo_spin.setDecimals(1)
        editor_layout.addRow("Tempo:", self._tempo_spin)

        self._swing_combo = QComboBox()
        self._swing_combo.addItems([f"{50+i}%" for i in range(26)])
        editor_layout.addRow("Swing:", self._swing_combo)

        self._pattern_length = QComboBox()
        self._pattern_length.addItems([f"{i+1}" for i in range(8)])
        editor_layout.addRow("Pattern Length:", self._pattern_length)

        self._beat_combo = QComboBox()
        self._beat_combo.addItems(["16th", "32nd", "8Tri", "16Tri"])
        editor_layout.addRow("Beat:", self._beat_combo)

        self._fx_chain_combo = QComboBox()
        self._fx_chain_combo.addItems(["None", "1->2", "2->3", "1->2->3"])
        editor_layout.addRow("FX Chain:", self._fx_chain_combo)

        self._last_step_combo = QComboBox()
        self._last_step_combo.addItems([str(i+1) for i in range(32)])
        editor_layout.addRow("Last Step:", self._last_step_combo)

        self._right_tabs.addTab(editor_widget, "Pattern Editor")

        fx_widget = QWidget()
        fx_layout = QFormLayout(fx_widget)
        fx_layout.setSpacing(8)
        fx_layout.setContentsMargins(16, 16, 16, 16)
        self._fx_combos = []
        self._fx_edit1 = []
        self._fx_edit2 = []
        self._fx_motion_status = []
        for i in range(3):
            combo = QComboBox()
            combo.addItems([e.name for e in FxType])
            fx_layout.addRow(f"FX {i+1} Type:", combo)
            self._fx_combos.append(combo)

            edit1 = QSpinBox()
            edit1.setRange(0, 127)
            fx_layout.addRow(f"FX {i+1} Edit 1:", edit1)
            self._fx_edit1.append(edit1)

            edit2 = QSpinBox()
            edit2.setRange(0, 127)
            fx_layout.addRow(f"FX {i+1} Edit 2:", edit2)
            self._fx_edit2.append(edit2)

            motion = QSpinBox()
            motion.setRange(0, 127)
            fx_layout.addRow(f"FX {i+1} Motion Seq:", motion)
            self._fx_motion_status.append(motion)
        self._right_tabs.addTab(fx_widget, "FX")

        parts_widget = QWidget()
        parts_layout = QVBoxLayout(parts_widget)
        parts_layout.addWidget(QLabel("Pattern Parts:"))
        self._parts_table = QTableWidget()
        self._parts_table.setColumnCount(len(PART_FIELD_SPECS))
        self._parts_table.setHorizontalHeaderLabels([spec[0] for spec in PART_FIELD_SPECS])
        self._parts_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._parts_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._parts_table.horizontalHeader().setStretchLastSection(False)
        self._parts_table.verticalHeader().setVisible(False)
        self._parts_table.setAlternatingRowColors(True)
        parts_layout.addWidget(self._parts_table)
        self._right_tabs.addTab(parts_widget, "Parts")

        motion_widget = QWidget()
        motion_layout = QVBoxLayout(motion_widget)
        motion_layout.addWidget(QLabel("Motion Sequences:"))
        self._motion_table = QTableWidget()
        self._motion_table.setColumnCount(2)
        self._motion_table.setHorizontalHeaderLabels(["#", "Operation Number"])
        self._motion_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._motion_table.verticalHeader().setVisible(False)
        self._motion_table.setAlternatingRowColors(True)
        motion_layout.addWidget(self._motion_table)
        self._right_tabs.addTab(motion_widget, "Motion Sequences")

        splitter.addWidget(self._right_tabs)
        splitter.setSizes([300, 900])

    def update_data(self, esx_file):
        self._esx = esx_file
        patterns = esx_file.patterns
        selected_row = self._pattern_table.currentRow()

        self._pattern_table.setRowCount(len(patterns))
        for i, p in enumerate(patterns):
            self._set_pattern_row(i, p)

        if 0 <= selected_row < len(patterns):
            self._pattern_table.selectRow(selected_row)
        elif patterns:
            self._pattern_table.selectRow(0)

    def _set_pattern_row(self, row: int, pattern):
        self._pattern_table.setItem(row, 0, QTableWidgetItem(str(row)))
        name = pattern.name.strip('\x00').strip()
        self._pattern_table.setItem(row, 1, QTableWidgetItem(name if name else "(empty)"))
        self._pattern_table.setItem(row, 2, QTableWidgetItem(f"{pattern.tempo.value:.1f}"))

    def select_pattern(self, row: int):
        if self._esx is None or not (0 <= row < len(self._esx.patterns)):
            return
        self._pattern_table.selectRow(row)

    def _on_pattern_selected(self):
        if self._esx is None:
            return
        # Commit any pending edits still sitting in the editor fields for the
        # previously selected pattern before we overwrite them below.
        if self._current_pattern is not None and 0 <= self._current_row < len(self._esx.patterns):
            self.apply_changes()
            self._set_pattern_row(self._current_row, self._current_pattern)

        row = self._pattern_table.currentRow()
        if 0 <= row < len(self._esx.patterns):
            self._current_row = row
            self._current_pattern = self._esx.patterns[row]
            self._populate_editor(self._current_pattern)

    def _on_pattern_swap_requested(self, src_row: int, dst_row: int):
        if self._esx is None:
            return
        patterns = self._esx.patterns
        if not (0 <= src_row < len(patterns) and 0 <= dst_row < len(patterns)):
            return

        # Commit any pending editor edits before we move patterns around,
        # so they land on the right object.
        if self._current_pattern is not None and 0 <= self._current_row < len(patterns):
            self.apply_changes()

        patterns[src_row], patterns[dst_row] = patterns[dst_row], patterns[src_row]
        patterns[src_row].pattern_number = src_row
        patterns[dst_row].pattern_number = dst_row

        self._set_pattern_row(src_row, patterns[src_row])
        self._set_pattern_row(dst_row, patterns[dst_row])

        # The currently open pattern object may have moved to the other row;
        # follow it so the editor and the highlighted row stay in sync.
        if self._current_row == src_row:
            self._current_row = dst_row
        elif self._current_row == dst_row:
            self._current_row = src_row

        if self._current_pattern is not None:
            self._pattern_table.blockSignals(True)
            self._pattern_table.selectRow(self._current_row)
            self._pattern_table.blockSignals(False)

    def _on_pattern_file_dropped(self, filepath: str, target_row: int):
        if self._esx is None or not (0 <= target_row < len(self._esx.patterns)):
            return
        # Select the drop target first so import_pattern_from_path() (which
        # reads currentRow()) and its "pattern will be replaced" confirmation
        # act on the row the user actually dropped onto.
        self._pattern_table.selectRow(target_row)
        self.import_pattern_from_path(filepath)

    def _copy_pattern(self):
        if self._esx is None:
            return
        row = self._pattern_table.currentRow()
        if not (0 <= row < len(self._esx.patterns)):
            return
        # Make sure unsaved edits in the editor are captured if the source
        # pattern is the one currently shown.
        if self._current_pattern is self._esx.patterns[row]:
            self.apply_changes()

        pattern = self._esx.patterns[row]
        self._clipboard_pattern_bytes = pattern.to_bytes()
        name = pattern.name.strip('\x00').strip()
        self._clipboard_pattern_label = f"{row} - {name}" if name else f"{row} - (empty)"
        self._clipboard_label.setText(f"Clipboard: {self._clipboard_pattern_label}")
        self._paste_pattern_btn.setEnabled(True)

    def _paste_pattern(self):
        if self._esx is None or self._clipboard_pattern_bytes is None:
            return
        row = self._pattern_table.currentRow()
        if not (0 <= row < len(self._esx.patterns)):
            return

        reply = QMessageBox.question(
            self, "Paste Pattern",
            f"Overwrite pattern {row} with the copied pattern "
            f"({self._clipboard_pattern_label})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        new_pattern = Pattern.from_bytes(self._clipboard_pattern_bytes, row)
        self._esx.patterns[row] = new_pattern
        self._set_pattern_row(row, new_pattern)

        if row == self._pattern_table.currentRow():
            self._current_row = row
            self._current_pattern = new_pattern
            self._populate_editor(new_pattern)

    def _export_pattern(self):
        if self._esx is None:
            QMessageBox.warning(self, "Export Pattern", "No ESX file loaded")
            return
        row = self._pattern_table.currentRow()
        if not (0 <= row < len(self._esx.patterns)):
            QMessageBox.warning(self, "Export Pattern", "No pattern selected")
            return
        if self._current_pattern is self._esx.patterns[row]:
            self.apply_changes()

        pattern = self._esx.patterns[row]
        if pattern.is_empty():
            QMessageBox.information(self, "Export Pattern", "Pattern is empty, nothing to export.")
            return

        name = pattern.name.strip('\x00').strip() or f"pattern_{row}"
        path = os.path.join(get_patterns_dir(), f"{row}_{name}.esxpat")
        try:
            export_pattern(self._esx, row, path)
            QMessageBox.information(
                self, "Export Pattern",
                f"Pattern (with its referenced samples) saved to:\n{path}"
            )
        except Exception as exc:
            report_error("export_pattern", exc)
            QMessageBox.critical(self, "Export Error", str(exc))

    def _import_pattern(self):
        if self._esx is None:
            QMessageBox.warning(self, "Import Pattern", "No ESX file loaded")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Pattern", get_patterns_dir(),
            "Electribe Pattern Files (*.esxpat);;All Files (*)"
        )
        if not path:
            return
        self.import_pattern_from_path(path)

    def import_pattern_from_path(self, path: str):
        """Import a .esxpat file (as produced by export_pattern) into the
        currently selected pattern slot. Used by both the Import Pattern
        button and the Pattern Browser (double-clicking a saved pattern)."""
        if self._esx is None:
            QMessageBox.warning(self, "Import Pattern", "No ESX file loaded")
            return
        row = self._pattern_table.currentRow()
        if not (0 <= row < len(self._esx.patterns)):
            QMessageBox.warning(self, "Import Pattern", "No target pattern slot selected")
            return

        existing = self._esx.patterns[row]
        if not existing.is_empty():
            existing_name = existing.name.strip(chr(0)).strip()
            reply = QMessageBox.question(
                self, "Import Pattern",
                f"Overwrite pattern {row} ({existing_name or '(empty)'}) with the imported pattern?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            new_pattern, warnings = import_pattern(self._esx, path, row)
        except Exception as exc:
            report_error("import_pattern", exc)
            QMessageBox.critical(self, "Import Error", str(exc))
            return

        self._set_pattern_row(row, new_pattern)
        if row == self._pattern_table.currentRow():
            self._current_row = row
            self._current_pattern = new_pattern
            self._populate_editor(new_pattern)

        if warnings:
            QMessageBox.warning(self, "Import Pattern", "\n".join(warnings))
        else:
            QMessageBox.information(self, "Import Pattern", f"Pattern imported into slot {row}.")

    def _populate_editor(self, pattern):
        self._name_edit.setText(pattern.name.strip('\x00'))
        self._tempo_spin.setValue(pattern.tempo.value)
        self._swing_combo.setCurrentIndex(int(pattern.swing))
        self._pattern_length.setCurrentIndex(int(pattern.pattern_length))
        self._beat_combo.setCurrentIndex(int(pattern.beat))
        self._fx_chain_combo.setCurrentIndex(int(pattern.fx_chain))
        self._last_step_combo.setCurrentIndex(int(pattern.last_step))

        for i, fx in enumerate(pattern.fx_parameters[:3]):
            self._fx_combos[i].setCurrentIndex(int(fx.effect_type))
            self._fx_edit1[i].setValue(max(0, min(127, fx.edit1)))
            self._fx_edit2[i].setValue(max(0, min(127, fx.edit2)))
            self._fx_motion_status[i].setValue(max(0, min(127, fx.motion_sequence_status)))

        self._populate_parts(pattern)

        self._motion_table.setRowCount(len(pattern.motion_parameters))
        for i, mo in enumerate(pattern.motion_parameters):
            self._motion_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self._motion_table.setItem(i, 1, QTableWidgetItem(str(mo.operation_number)))

    def _populate_parts(self, pattern):
        self._part_rows = self._build_part_rows(pattern)
        sample_names = self._get_sample_names_list()
        self._parts_table.setRowCount(len(self._part_rows))

        for row, (label, part) in enumerate(self._part_rows):
            for col, (_, attr, kind, enum_cls) in enumerate(PART_FIELD_SPECS):
                if kind == "label":
                    self._set_readonly_item(row, col, label)
                elif kind == "sample":
                    if hasattr(part, attr):
                        combo = QComboBox()
                        combo.addItems(sample_names)
                        idx = part.sample_pointer + 1 if part.sample_pointer >= 0 else 0
                        combo.setCurrentIndex(max(0, min(idx, len(sample_names) - 1)))
                        self._parts_table.setCellWidget(row, col, combo)
                    else:
                        self._set_readonly_item(row, col, "")
                elif kind == "enum":
                    if hasattr(part, attr):
                        self._set_enum_combo(row, col, enum_cls, getattr(part, attr))
                    else:
                        self._set_readonly_item(row, col, "")
                elif kind == "int":
                    actual_attr = self._resolve_attr(part, attr)
                    if actual_attr:
                        self._set_editable_item(row, col, str(getattr(part, actual_attr)))
                    else:
                        self._set_readonly_item(row, col, "")

        self._parts_table.resizeColumnsToContents()

    def _build_part_rows(self, pattern):
        rows = []
        for i, part in enumerate(pattern.drum_parts):
            rows.append((PATTERN_PART_NAMES[i], part))
        rows.append((PATTERN_PART_NAMES[9], pattern.accent_part))
        for i, part in enumerate(pattern.keyboard_parts):
            rows.append((PATTERN_PART_NAMES[10 + i], part))
        for i, part in enumerate(pattern.stretch_slice_parts):
            rows.append((PATTERN_PART_NAMES[12 + i], part))
        rows.append((PATTERN_PART_NAMES[15], pattern.audio_in_part))
        return rows

    def _resolve_attr(self, part, attr):
        if attr == "reserved_bits_byte7" and hasattr(part, "reserved_bits"):
            return "reserved_bits"
        return attr if hasattr(part, attr) else None

    def _set_readonly_item(self, row, col, text):
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._parts_table.setItem(row, col, item)

    def _set_editable_item(self, row, col, text):
        self._parts_table.setItem(row, col, QTableWidgetItem(text))

    def _set_enum_combo(self, row, col, enum_cls, value):
        combo = QComboBox()
        for enum_value in enum_cls:
            combo.addItem(enum_value.name, int(enum_value))
        combo.setCurrentIndex(max(0, combo.findData(int(value))))
        self._parts_table.setCellWidget(row, col, combo)

    def _get_sample_names_list(self):
        names = ["(none)"]
        if self._esx is None:
            return names
        for i, sample in enumerate(self._esx.samples):
            name = sample.name.strip('\x00').strip()
            names.append(f"{i}: {name}" if name else f"{i}: (empty)")
        return names

    def apply_changes(self):
        if self._current_pattern is None:
            return
        p = self._current_pattern
        p.name = self._name_edit.text()
        p.tempo.value = self._tempo_spin.value()
        p.swing = Swing(self._swing_combo.currentIndex())
        p.pattern_length = PatternLength(self._pattern_length.currentIndex())
        p.beat = Beat(self._beat_combo.currentIndex())
        p.fx_chain = FxChain(self._fx_chain_combo.currentIndex())
        p.last_step = LastStep(self._last_step_combo.currentIndex())

        for i, fx in enumerate(p.fx_parameters[:3]):
            fx.effect_type = FxType(self._fx_combos[i].currentIndex())
            fx.edit1 = self._fx_edit1[i].value()
            fx.edit2 = self._fx_edit2[i].value()
            fx.motion_sequence_status = self._fx_motion_status[i].value()

        for row, (_, part) in enumerate(self._part_rows):
            for col, (_, attr, kind, enum_cls) in enumerate(PART_FIELD_SPECS):
                if kind == "sample" and hasattr(part, attr):
                    combo = self._parts_table.cellWidget(row, col)
                    if combo:
                        part.sample_pointer = combo.currentIndex() - 1
                elif kind == "enum" and hasattr(part, attr):
                    combo = self._parts_table.cellWidget(row, col)
                    if combo:
                        setattr(part, attr, enum_cls(combo.currentData()))
                elif kind == "int":
                    actual_attr = self._resolve_attr(part, attr)
                    if actual_attr:
                        item = self._parts_table.item(row, col)
                        value = self._parse_item_int(item, *INT_RANGES.get(actual_attr, (-128, 255)))
                        setattr(part, actual_attr, value)

    def _parse_item_int(self, item, min_value, max_value):
        return self._clamp_int(item.text() if item else "", min_value, max_value)

    def _clamp_int(self, text, min_value, max_value):
        try:
            value = int(text.strip())
        except ValueError:
            value = min_value
        return max(min_value, min(max_value, value))

