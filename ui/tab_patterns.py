import os
from enum import IntEnum

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QFormLayout, QComboBox, QLineEdit,
    QDoubleSpinBox, QSpinBox, QLabel, QHeaderView, QAbstractItemView,
    QPushButton, QMessageBox, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont

from esx.constants import (
    AmpEg, BpmSync, Beat, FilterType, FxChain, FxSelect, FxSend,
    FxType, LastStep, ModDest, ModType, PATTERN_PART_NAMES,
    PatternLength, Reverse, Roll, RollType, Swing
)
from esx.pattern import Pattern
from esx.pattern_transfer import export_pattern, import_pattern
from esx.app_paths import get_patterns_dir
from audio.sequencer_engine import SequencerPlaybackEngine
from ui.error_log import report_error
from ui.i18n import tr
from ui import icons
from ui.searchable_combo import SearchableComboBox
from ui.theme import ACCENT, BG_FIELD, BG_FIELD_HOVER, BG_PANEL, BORDER, BORDER_LIGHT, TEXT_DIM


# The first element of each spec is a tr() key, not already-resolved text:
# PART_FIELD_SPECS is a module-level (class-body-adjacent) constant built at
# import time, before main.py has chosen a language (see ui/i18n.py's
# module docstring) - so it must never hold tr()-resolved text itself. The
# label is only resolved with tr() where it's actually displayed (see
# _populate_parts), which runs well after the language is set.
PART_FIELD_SPECS = [
    ("tab_patterns.field_part", None, "label", None),
    ("tab_patterns.field_sample", "sample_pointer", "sample", None),
    ("tab_patterns.field_level", "level", "int", None),
    ("tab_patterns.field_pan", "pan", "int", None),
    ("tab_patterns.field_pitch", "pitch", "int", None),
    ("tab_patterns.field_glide", "glide", "int", None),
    ("tab_patterns.field_filter", "filter_type", "enum", FilterType),
    ("tab_patterns.field_cutoff", "cutoff", "int", None),
    ("tab_patterns.field_resonance", "resonance", "int", None),
    ("tab_patterns.field_eg_intensity", "eg_intensity", "int", None),
    ("tab_patterns.field_eg_time", "eg_time", "int", None),
    ("tab_patterns.field_start_point", "start_point", "int", None),
    ("tab_patterns.field_fx_select", "fx_select", "enum", FxSelect),
    ("tab_patterns.field_fx_send", "fx_send", "enum", FxSend),
    ("tab_patterns.field_roll", "roll", "enum", Roll),
    ("tab_patterns.field_amp_eg", "amp_eg", "enum", AmpEg),
    ("tab_patterns.field_reverse", "reverse", "enum", Reverse),
    ("tab_patterns.field_mod_dest", "mod_dest", "enum", ModDest),
    ("tab_patterns.field_mod_type", "mod_type", "enum", ModType),
    ("tab_patterns.field_bpm_sync", "bpm_sync", "enum", BpmSync),
    ("tab_patterns.field_mod_speed", "mod_speed", "int", None),
    ("tab_patterns.field_mod_depth", "mod_depth", "int", None),
    ("tab_patterns.field_motion_seq", "motion_sequence_status", "int", None),
    ("tab_patterns.field_slice_no", "slice_number", "int", None),
    ("tab_patterns.field_reserved_byte", "reserved_byte", "int", None),
    ("tab_patterns.field_reserved_reverse", "reserved_bits_after_reverse", "int", None),
    ("tab_patterns.field_reserved_mod", "reserved_bit_after_mod_depth", "int", None),
    ("tab_patterns.field_reserved_byte7", "reserved_bits_byte7", "int", None),
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

# Steps tab: one row-group per part (Accent has no row, but keeps its bit in
# mute_status), stacked into one sub-row per bar (Pattern Length, 1-8) with
# one toggle button per step in that bar. "bits" parts pack 1 bit/step into
# sequence_data (bit order assumed LSB-first per byte, undocumented in the
# ESX format); "gate" parts (keyboard) use 1 byte/step in sequence_data_gate.
# Both buffers hold 128 steps total, so a part's addressable steps across all
# bars are laid out back-to-back: global_step = bar_index * steps_per_bar + col.
# Single unified table: each part is one info row directly followed by that
# part's bar rows (collapsible via row-hiding, not a separate widget) - so
# the sequencer for a part always sits right under that part's own row
# instead of in one block at the end. Only "Bar" is a real dedicated column
# (shared with the step columns); Mute/Solo/Part/Sample/Copy/Paste have no
# columns of their own - they live in one widget that spans the entire row,
# only on the info row, so the step grid on bar rows can start flush at the
# left edge (column 0) instead of being indented behind reserved columns
# that are blank on every bar row anyway.
SEQ_BAR_COL = 0
SEQ_FIXED_COLUMNS = 1

STEPS_MAX_STEPS = 32
STEPS_MAX_BARS = 8
STEPS_ROW_HEIGHT = 26
# The info row packs in Mute/Solo/Part/Sample/Copy/Paste controls - taller
# than a bar row so those controls have room to render clearly instead of
# looking cramped.
STEPS_INFO_ROW_HEIGHT = 34
# Inline column-header row (Bar / step numbers), repeated directly above
# each part's own bar rows - see _populate_steps - instead of relying on the
# table's single sticky header, which only ever sits above the first row.
STEPS_COLHEADER_ROW_HEIGHT = 20
STEPS_SPACER_ROW_HEIGHT = 6
STEPS_GROUP_SIZE = 4  # visual divider every N step columns
DIVIDER_COL_WIDTH = 6
# Every step column is pinned to this exact width after layout, since
# resizeColumnsToContents() would otherwise size 2-digit header labels
# ("10".."16") a little wider than 1-digit ones, making the group dividers
# look inconsistent from one group to the next.
STEP_COL_WIDTH = 35

# The sequencer table's step columns are interleaved with dedicated narrow
# "divider" columns every STEPS_GROUP_SIZE steps, so the group separator is a
# real gap between two columns rather than a border painted on a step button.
# SEQ_STEP_TABLE_COL maps a step's position within a bar (0-based) to its
# table column; SEQ_DIVIDER_TABLE_COLS maps each divider's table column to
# the step index immediately before it (used to hide dividers past the
# pattern's current Last Step).
_seq_column_plan = []
for _s in range(STEPS_MAX_STEPS):
    _seq_column_plan.append(("step", _s))
    if (_s + 1) % STEPS_GROUP_SIZE == 0 and (_s + 1) < STEPS_MAX_STEPS:
        _seq_column_plan.append(("divider", _s))
SEQ_STEP_TABLE_COL = {s: SEQ_FIXED_COLUMNS + i for i, (kind, s) in enumerate(_seq_column_plan) if kind == "step"}
SEQ_DIVIDER_TABLE_COLS = [(SEQ_FIXED_COLUMNS + i, s) for i, (kind, s) in enumerate(_seq_column_plan) if kind == "divider"]
SEQ_TOTAL_COLUMNS = SEQ_FIXED_COLUMNS + len(_seq_column_plan)

STEP_DATA_CAPACITY = 128  # bits/bytes available in sequence_data / sequence_data_gate
PARTS_SAMPLE_COL = 1  # index of the "Sample" column in PART_FIELD_SPECS
PARTS_LABEL_COL = 0  # index of the "Part" column in PART_FIELD_SPECS

# Wide enough to show the longest part label ("Keyboard1"/"Keyboard2") and a
# typical sample name without the user having to manually drag the column,
# used both on the Steps grid and the Parts table.
PART_LABEL_COL_WIDTH = 130
SAMPLE_COL_WIDTH = 220

STEP_ON_COLOR = ACCENT
MUTE_ON_COLOR = "#e5484d"
SOLO_ON_COLOR = "#f5c451"
PLAYHEAD_COLOR = "#ffd166"

# Piano Roll (Keyboard parts only) - an alternate view of the exact same
# sequence_data_gate/sequence_data_note bytes the plain on/off grid edits,
# just laid out as notes (rows) x steps (columns) instead of one on/off
# button per step. Covers the full raw byte range (0-127) sequence_data_note
# can hold, not just a "musical" subset, so no existing pattern data - even
# an unusual note value written by other software - is ever hidden.
PIANO_ROLL_LOW_NOTE = 0
PIANO_ROLL_HIGH_NOTE = 127
# The note a plain Steps-grid toggle assigns to a freshly-enabled Keyboard
# step (see TabPatterns._on_step_toggled) - C4 (MIDI 60), matching the
# fallback sequencer_engine._get_step_note already used for playback.
DEFAULT_KEYBOARD_NOTE = 60
PIANO_ROLL_ROW_HEIGHT = 14
PIANO_ROLL_KEY_COL_WIDTH = 42
PIANO_ROLL_AREA_HEIGHT = 260

_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def _note_name(note: int) -> str:
    return f"{_NOTE_NAMES[note % 12]}{note // 12 - 1}"


def _is_black_key(note: int) -> bool:
    return (note % 12) in (1, 3, 6, 8, 10)


def _piano_roll_column_plan(num_bars, steps_per_bar):
    """Continuous (all-bars-back-to-back) column plan for the Piano Roll:
    every bar's steps sit side by side in one row instead of the plain
    grid's one-row-per-bar layout, so besides the plain grid's group-of-4
    divider every bar boundary also gets its own (bolder) divider. Global
    step numbering matches the plain grid exactly (bar_index * steps_per_bar
    + col), capped at STEP_DATA_CAPACITY the same way."""
    total_steps = min(num_bars * steps_per_bar, STEP_DATA_CAPACITY)
    plan = []
    for s in range(total_steps):
        plan.append(("step", s))
        if s == total_steps - 1:
            continue
        if (s + 1) % steps_per_bar == 0:
            plan.append(("divider", "bar"))
        elif (s + 1) % STEPS_GROUP_SIZE == 0:
            plan.append(("divider", "group"))
    return plan, total_steps


class PianoRollWidget(QWidget):
    """Piano-roll step editor for one Keyboard part, swapped in for that
    part's plain on/off Sequencer grid (see TabPatterns._on_piano_roll_toggled).
    Rows are MIDI notes (highest pitch at the top, as in a DAW piano roll);
    columns are steps, using the same global_step numbering as the plain
    grid - so switching views back and forth edits the very same
    sequence_data_note/sequence_data_gate bytes, never a separate copy. A
    Keyboard part is monophonic per step (one note byte + one gate byte,
    see esx.pattern.PartKeyboard), so each step column can only have one lit
    cell - clicking a cell sets that step's note to the row's pitch and
    turns its gate on; clicking the already-lit cell for that step turns
    the gate back off, the same toggle semantics as the plain grid."""

    edited = pyqtSignal()

    def __init__(self, get_note, set_note, get_gate, set_gate, num_bars, steps_per_bar, parent=None):
        super().__init__(parent)
        self._get_note = get_note
        self._set_note = set_note
        self._get_gate = get_gate
        self._set_gate = set_gate
        self._notes = list(range(PIANO_ROLL_HIGH_NOTE, PIANO_ROLL_LOW_NOTE - 1, -1))
        self._plan, self._total_steps = _piano_roll_column_plan(num_bars, steps_per_bar)
        self._col_step = {1 + i: s for i, (kind, s) in enumerate(self._plan) if kind == "step"}
        self._step_col = {s: c for c, s in self._col_step.items()}
        self._table = None
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        table = QTableWidget()
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(False)
        table.setRowCount(len(self._notes))
        table.setColumnCount(1 + len(self._plan))
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        table.verticalHeader().setDefaultSectionSize(PIANO_ROLL_ROW_HEIGHT)
        table.verticalHeader().setMinimumSectionSize(1)
        table.horizontalHeader().setMinimumSectionSize(1)

        headers = [""] * (1 + len(self._plan))
        for col, step in self._col_step.items():
            headers[col] = str(step + 1)
        table.setHorizontalHeaderLabels(headers)

        bold_font = QFont()
        bold_font.setBold(True)

        for r, note in enumerate(self._notes):
            is_default = note == DEFAULT_KEYBOARD_NOTE
            label_item = QTableWidgetItem(_note_name(note))
            label_item.setFlags(Qt.ItemFlag.NoItemFlags)
            label_item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
            label_bg = ACCENT if is_default else ("#1c1d20" if _is_black_key(note) else "#303236")
            label_item.setBackground(QColor(label_bg))
            label_item.setForeground(QColor("#0b0c0d" if is_default else TEXT_DIM))
            if is_default:
                label_item.setFont(bold_font)
            label_item.setToolTip(tr("tab_patterns.piano_roll_default_note_tooltip") if is_default else "")
            table.setItem(r, 0, label_item)

            row_bg = "#232427" if _is_black_key(note) else BG_FIELD
            for i, (kind, s) in enumerate(self._plan):
                col = 1 + i
                item = QTableWidgetItem("")
                if kind == "divider":
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                    item.setBackground(QColor(BORDER_LIGHT if s == "bar" else BORDER))
                else:
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    item.setBackground(QColor(row_bg))
                table.setItem(r, col, item)

        table.setColumnWidth(0, PIANO_ROLL_KEY_COL_WIDTH)
        for i, (kind, s) in enumerate(self._plan):
            table.setColumnWidth(1 + i, DIVIDER_COL_WIDTH if kind == "divider" else STEP_COL_WIDTH)

        table.cellClicked.connect(self._on_cell_clicked)
        self._table = table
        layout.addWidget(table)

        default_row = self._notes.index(DEFAULT_KEYBOARD_NOTE)
        anchor_row = max(0, default_row - 5)
        QTimer.singleShot(0, lambda: table.scrollToItem(
            table.item(anchor_row, 0), QAbstractItemView.ScrollHint.PositionAtTop
        ))

    def _on_cell_clicked(self, row, col):
        step = self._col_step.get(col)
        if step is None or not (0 <= row < len(self._notes)):
            return
        note = self._notes[row]
        currently_on = self._get_gate(step) and self._get_note(step) == note
        if currently_on:
            self._set_gate(step, False)
        else:
            self._set_note(step, note)
            self._set_gate(step, True)
        self._refresh_column(step)
        self.edited.emit()

    def refresh(self):
        for step in self._step_col:
            self._refresh_column(step)

    def _refresh_column(self, step):
        col = self._step_col.get(step)
        if col is None or self._table is None:
            return
        gate_on = self._get_gate(step)
        active_note = self._get_note(step) if gate_on else None
        for r, note in enumerate(self._notes):
            item = self._table.item(r, col)
            if item is None:
                continue
            if active_note is not None and note == active_note:
                item.setBackground(QColor(STEP_ON_COLOR))
            else:
                item.setBackground(QColor("#232427" if _is_black_key(note) else BG_FIELD))


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
        self._step_rows = []
        self._step_groups = []
        self._step_buttons = {}
        self._part_sequencer_expanded = {}
        self._part_piano_roll_mode = {}
        self._piano_roll_widgets = {}
        self._step_clipboard = None
        self._solo_bits = set()
        self._pre_solo_mute_status = None
        self._sequencer_engine = SequencerPlaybackEngine()
        self._playhead_step = None
        self._playhead_timer = QTimer(self)
        self._playhead_timer.setInterval(40)
        self._playhead_timer.timeout.connect(self._update_playhead)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        hint = QLabel(tr("tab_patterns.patterns_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9aa0a8; font-size: 11px;")
        left_layout.addWidget(hint)
        self._pattern_table = PatternTable()
        self._pattern_table.setColumnCount(3)
        self._pattern_table.setHorizontalHeaderLabels([tr("common.hash"), tr("common.name"), tr("common.tempo")])
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
        self._copy_pattern_btn = QPushButton(icons.icon("copy"), tr("tab_patterns.copy_pattern"))
        self._paste_pattern_btn = QPushButton(icons.icon("paste"), tr("tab_patterns.paste_pattern"))
        self._paste_pattern_btn.setEnabled(False)
        self._copy_pattern_btn.clicked.connect(self._copy_pattern)
        self._paste_pattern_btn.clicked.connect(self._paste_pattern)
        copy_paste_layout.addWidget(self._copy_pattern_btn)
        copy_paste_layout.addWidget(self._paste_pattern_btn)
        left_layout.addLayout(copy_paste_layout)

        self._clipboard_label = QLabel(tr("tab_patterns.clipboard_empty"))
        self._clipboard_label.setStyleSheet("color: #9aa0a8; font-size: 11px;")
        left_layout.addWidget(self._clipboard_label)

        transfer_layout = QHBoxLayout()
        self._export_pattern_btn = QPushButton(icons.icon("file-export"), tr("tab_patterns.export_pattern"))
        self._import_pattern_btn = QPushButton(icons.icon("file-import"), tr("tab_patterns.import_pattern_ellipsis"))
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
        editor_layout.addRow(tr("common.name_colon"), self._name_edit)

        self._tempo_spin = QDoubleSpinBox()
        self._tempo_spin.setRange(20.0, 300.0)
        self._tempo_spin.setDecimals(1)
        editor_layout.addRow(tr("common.tempo_colon"), self._tempo_spin)

        self._swing_combo = QComboBox()
        self._swing_combo.addItems([f"{50+i}%" for i in range(26)])
        editor_layout.addRow(tr("tab_patterns.swing_colon"), self._swing_combo)

        self._pattern_length = QComboBox()
        self._pattern_length.addItems([f"{i+1}" for i in range(8)])
        self._pattern_length.currentIndexChanged.connect(self._on_pattern_length_changed)
        editor_layout.addRow(tr("tab_patterns.pattern_length_colon"), self._pattern_length)

        self._beat_combo = QComboBox()
        self._beat_combo.addItems(["16th", "32nd", "8Tri", "16Tri"])
        editor_layout.addRow(tr("tab_patterns.beat_colon"), self._beat_combo)

        self._fx_chain_combo = QComboBox()
        self._fx_chain_combo.addItems(["None", "1->2", "2->3", "1->2->3"])
        editor_layout.addRow(tr("tab_patterns.fx_chain_colon"), self._fx_chain_combo)

        self._last_step_combo = QComboBox()
        self._last_step_combo.addItems([str(i+1) for i in range(32)])
        self._last_step_combo.currentIndexChanged.connect(self._on_last_step_changed)
        editor_layout.addRow(tr("tab_patterns.last_step_colon"), self._last_step_combo)

        self._right_tabs.addTab(editor_widget, tr("tab_patterns.tab_pattern_editor"))

        self._right_tabs.addTab(self._setup_steps_tab(), tr("tab_patterns.tab_steps"))

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
            fx_layout.addRow(tr("tab_patterns.fx_type_colon", n=i + 1), combo)
            self._fx_combos.append(combo)

            edit1 = QSpinBox()
            edit1.setRange(0, 127)
            fx_layout.addRow(tr("tab_patterns.fx_edit1_colon", n=i + 1), edit1)
            self._fx_edit1.append(edit1)

            edit2 = QSpinBox()
            edit2.setRange(0, 127)
            fx_layout.addRow(tr("tab_patterns.fx_edit2_colon", n=i + 1), edit2)
            self._fx_edit2.append(edit2)

            motion = QSpinBox()
            motion.setRange(0, 127)
            fx_layout.addRow(tr("tab_patterns.fx_motion_seq_colon", n=i + 1), motion)
            self._fx_motion_status.append(motion)
        self._right_tabs.addTab(fx_widget, tr("tab_patterns.tab_fx"))

        parts_widget = QWidget()
        parts_layout = QVBoxLayout(parts_widget)
        parts_layout.addWidget(QLabel(tr("tab_patterns.pattern_parts_colon")))
        self._parts_table = QTableWidget()
        self._parts_table.setColumnCount(len(PART_FIELD_SPECS))
        self._parts_table.setHorizontalHeaderLabels([tr(spec[0]) for spec in PART_FIELD_SPECS])
        self._parts_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._parts_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._parts_table.horizontalHeader().setStretchLastSection(False)
        self._parts_table.verticalHeader().setVisible(False)
        self._parts_table.setAlternatingRowColors(True)
        parts_layout.addWidget(self._parts_table)
        self._right_tabs.addTab(parts_widget, tr("tab_patterns.tab_parts"))

        motion_widget = QWidget()
        motion_layout = QVBoxLayout(motion_widget)
        motion_layout.addWidget(QLabel(tr("tab_patterns.motion_sequences_colon")))
        self._motion_table = QTableWidget()
        self._motion_table.setColumnCount(2)
        self._motion_table.setHorizontalHeaderLabels([tr("common.hash"), tr("tab_patterns.operation_number")])
        self._motion_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._motion_table.verticalHeader().setVisible(False)
        self._motion_table.setAlternatingRowColors(True)
        motion_layout.addWidget(self._motion_table)
        self._right_tabs.addTab(motion_widget, tr("tab_patterns.tab_motion_sequences"))

        splitter.addWidget(self._right_tabs)
        splitter.setSizes([300, 900])

    def _setup_steps_tab(self):
        steps_widget = QWidget()
        steps_layout = QVBoxLayout(steps_widget)
        steps_layout.setContentsMargins(16, 16, 16, 16)

        hint = QLabel(tr("tab_patterns.steps_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        steps_layout.addWidget(hint)

        toggle_layout = QHBoxLayout()
        self._play_btn = QPushButton()
        self._play_btn.setCheckable(True)
        self._style_play_button(False)
        self._play_btn.toggled.connect(self._on_play_toggled)
        toggle_layout.addWidget(self._play_btn)
        toggle_layout.addSpacing(10)
        self._sequencer_toggle_btn = QPushButton(tr("tab_patterns.collapse_all"))
        self._sequencer_toggle_btn.setCheckable(True)
        self._sequencer_toggle_btn.setChecked(True)
        self._sequencer_toggle_btn.toggled.connect(self._on_sequencer_toggle)
        toggle_layout.addWidget(self._sequencer_toggle_btn)
        toggle_layout.addStretch(1)
        steps_layout.addLayout(toggle_layout)

        # Sits flush against the table's top edge so it reads as that table's
        # header - a real QTableWidget header can't be reused here since it
        # only ever labels plain columns, not the info row's mix of buttons/
        # combo/label, so this mirrors the info row's own widget layout
        # (same widths/spacing) with plain labels instead of controls.
        steps_layout.addWidget(self._build_steps_table_header())

        self._sequencer_table = QTableWidget()
        self._sequencer_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._sequencer_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._sequencer_table.verticalHeader().setVisible(False)
        self._sequencer_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._sequencer_table.verticalHeader().setDefaultSectionSize(STEPS_ROW_HEIGHT)
        self._sequencer_table.verticalHeader().setMinimumSectionSize(1)
        # Lets the group-divider columns be narrower than Qt's default
        # minimum column width, so they read as a thin line, not a cell.
        self._sequencer_table.horizontalHeader().setMinimumSectionSize(1)
        self._sequencer_table.setAlternatingRowColors(False)
        self._sequencer_table.setColumnCount(SEQ_TOTAL_COLUMNS)
        # The table's own (single, sticky-at-top) header only ever sits above
        # the very first row - the first part's info row, not its actual
        # step grid - so it can't label "the sequencer" for every part.
        # Instead each part gets its own inline column-header row (built in
        # _populate_steps) placed directly above that part's own bar rows,
        # and the table's built-in header is hidden entirely.
        self._sequencer_table.horizontalHeader().setVisible(False)
        steps_layout.addWidget(self._sequencer_table)

        return steps_widget

    def _build_steps_table_header(self):
        """A static label row matching the info row's own widget widths
        (mute/solo/part/sample/copy/paste/collapse), styled like a table
        header and pinned directly above the sequencer table - explains
        those controls once, in the one place a real QTableWidget header
        can't reach since the info row is a single widget spanning every
        column, not one value per column."""
        header = QWidget()
        header.setStyleSheet(f"background-color: {BG_PANEL};")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        def label(text, width=None, min_width=None, font_size=11):
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: {font_size}px; font-weight: 600;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if width is not None:
                lbl.setFixedWidth(width)
            if min_width is not None:
                lbl.setMinimumWidth(min_width)
            return lbl

        # The narrow labels (Mute/Solo/Copy/Paste) sit above 30px-wide
        # buttons - too tight for their full word at the row's normal font
        # size, so those specific labels drop a size to avoid clipping.
        layout.addWidget(label(tr("common.mute"), 30, font_size=9))
        layout.addWidget(label(tr("common.solo"), 30, font_size=9))
        layout.addWidget(label(tr("common.part"), PART_LABEL_COL_WIDTH))
        layout.addWidget(label(tr("common.sample"), min_width=SAMPLE_COL_WIDTH - 10))
        layout.addWidget(label(tr("common.copy"), 30, font_size=9))
        layout.addWidget(label(tr("common.paste"), 34, font_size=9))
        layout.addStretch(1)
        layout.addWidget(label(tr("tab_patterns.seq_abbr"), 26, font_size=9))
        return header

    def _sequencer_header_labels(self):
        labels = [tr("tab_patterns.bar")] + [""] * len(_seq_column_plan)
        for i, (kind, s) in enumerate(_seq_column_plan):
            if kind == "step":
                labels[SEQ_FIXED_COLUMNS + i] = str(s + 1)
        return labels

    def _on_sequencer_toggle(self, checked):
        self._sequencer_toggle_btn.setText(tr("tab_patterns.collapse_all") if checked else tr("tab_patterns.expand_all"))
        for part_idx in range(len(self._step_groups)):
            self._set_part_sequencer_expanded(part_idx, checked)

    def _set_part_sequencer_expanded(self, part_idx, expanded):
        self._part_sequencer_expanded[part_idx] = expanded
        group = self._step_groups[part_idx]
        self._sequencer_table.setRowHidden(group["header_row"], not expanded)
        for bar in range(group["num_bars"]):
            self._sequencer_table.setRowHidden(group["seq_start"] + bar, not expanded)
        btn = group.get("collapse_btn")
        if btn:
            btn.blockSignals(True)
            btn.setChecked(expanded)
            btn.blockSignals(False)
            self._style_collapse_button(btn, expanded)

    def _style_collapse_button(self, btn, expanded):
        btn.setIcon(icons.icon("chevron-down" if expanded else "chevron-right"))
        btn.setToolTip(
            tr("tab_patterns.collapse_this_part_sequencer") if expanded
            else tr("tab_patterns.expand_this_part_sequencer")
        )

    def _make_piano_roll_callbacks(self, part):
        def get_note(step):
            data = part.sequence_data_note.data
            return data[step] if step < len(data) else DEFAULT_KEYBOARD_NOTE

        def set_note(step, note):
            data = part.sequence_data_note.data
            if step < len(data):
                data[step] = max(0, min(127, note))

        def get_gate(step):
            data = part.sequence_data_gate.data
            return step < len(data) and data[step] != 0

        def set_gate(step, on):
            data = part.sequence_data_gate.data
            if step < len(data):
                data[step] = 1 if on else 0

        return get_note, set_note, get_gate, set_gate

    def _on_piano_roll_toggled(self, part_idx, checked):
        self._part_piano_roll_mode[part_idx] = checked
        if self._current_pattern is None:
            return
        self._stop_sequencer_playback()
        # Switching views rebuilds the whole Steps grid (_populate_steps),
        # which otherwise also resets the step clipboard - preserve it
        # across the rebuild so toggling Piano Roll doesn't silently drop
        # whatever the user had copied.
        saved_clipboard = self._step_clipboard
        self._populate_steps(self._current_pattern)
        self._step_clipboard = saved_clipboard
        self._refresh_paste_buttons()

    def _on_piano_roll_edited(self, part_idx):
        self._refresh_sequencer_playback()

    def _style_play_button(self, playing):
        self._play_btn.setIcon(icons.icon("pause" if playing else "play"))
        self._play_btn.setText(tr("common.pause") if playing else tr("common.play"))
        self._play_btn.setToolTip(
            tr("tab_patterns.pause_sequencer_tooltip") if playing else tr("tab_patterns.play_pattern_tooltip")
        )

    def _on_play_toggled(self, checked):
        self._style_play_button(checked)
        if checked:
            self._start_sequencer_playback()
            if self._play_btn.isChecked():
                self._playhead_timer.start()
        else:
            self._sequencer_engine.pause()
            self._playhead_timer.stop()

    def _start_sequencer_playback(self):
        if self._current_pattern is None or self._esx is None:
            self._play_btn.setChecked(False)
            return
        ok = self._sequencer_engine.play(self._current_pattern, self._esx.samples)
        if not ok:
            self._play_btn.setChecked(False)
            QMessageBox.warning(
                self, tr("tab_patterns.playback_title"),
                tr("tab_patterns.playback_unavailable"),
            )

    def _stop_sequencer_playback(self):
        self._sequencer_engine.stop()
        self._playhead_timer.stop()
        self._clear_playhead()
        if self._play_btn.isChecked():
            self._play_btn.blockSignals(True)
            self._play_btn.setChecked(False)
            self._play_btn.blockSignals(False)
            self._style_play_button(False)

    def _refresh_sequencer_playback(self):
        """Hot-swaps the loop buffer if the sequencer is currently playing
        or paused, so mute/solo/step edits are heard right away instead of
        only after the next Play press. No-ops if it isn't running. The
        re-render runs on a background thread (update_buffer_async) since a
        Stretch part's WSOLA render can take a second or more - doing it
        synchronously here would freeze the UI on every step/mute click."""
        if self._current_pattern is not None and self._esx is not None:
            self._sequencer_engine.update_buffer_async(self._current_pattern, self._esx.samples)

    def _clear_playhead(self):
        """Restores the previously-highlighted playhead step button (if any)
        to its normal on/off style."""
        if self._playhead_step is not None:
            for part_idx in range(len(self._step_rows)):
                btn = self._step_buttons.get((part_idx, self._playhead_step))
                if btn is not None:
                    self._style_step_button(btn, btn.isChecked())
            self._playhead_step = None

    def _update_playhead(self):
        """Polled by self._playhead_timer while the sequencer is playing -
        highlights the step column currently sounding across every part
        row, so the Steps grid visibly follows along with playback."""
        step = self._sequencer_engine.get_playback_step()
        if step == self._playhead_step:
            return
        self._clear_playhead()
        if step is None:
            return
        for part_idx in range(len(self._step_rows)):
            btn = self._step_buttons.get((part_idx, step))
            if btn is not None:
                self._style_step_button(btn, btn.isChecked(), playhead=True)
        self._playhead_step = step

    def _build_step_rows(self, pattern):
        """One group per part in mute_status bit order, skipping Accent (bit 9
        stays under the app's control but has no row in the Steps grid)."""
        rows = []
        bit = 0
        for i, part in enumerate(pattern.drum_parts):
            rows.append({"label": PATTERN_PART_NAMES[i], "part": part, "bit": bit, "kind": "bits"})
            bit += 1
        bit += 1  # Accent
        for i, part in enumerate(pattern.keyboard_parts):
            rows.append({"label": PATTERN_PART_NAMES[10 + i], "part": part, "bit": bit, "kind": "gate"})
            bit += 1
        for i, part in enumerate(pattern.stretch_slice_parts):
            rows.append({"label": PATTERN_PART_NAMES[12 + i], "part": part, "bit": bit, "kind": "bits"})
            bit += 1
        rows.append({"label": PATTERN_PART_NAMES[15], "part": pattern.audio_in_part, "bit": bit, "kind": "bits"})
        return rows

    def _current_last_step_count(self):
        return self._last_step_combo.currentIndex() + 1

    def _current_pattern_length_bars(self):
        return self._pattern_length.currentIndex() + 1

    def _on_last_step_changed(self, index):
        if self._current_pattern is not None:
            self._stop_sequencer_playback()
            self._populate_steps(self._current_pattern)

    def _on_pattern_length_changed(self, index):
        if self._current_pattern is not None:
            self._stop_sequencer_playback()
            self._populate_steps(self._current_pattern)

    def _populate_steps(self, pattern):
        self._step_rows = self._build_step_rows(pattern)
        self._step_clipboard = None
        self._solo_bits = set()
        self._pre_solo_mute_status = None
        sample_names = self._get_sample_names_list()

        num_bars = self._current_pattern_length_bars()
        steps_per_bar = self._current_last_step_count()
        num_parts = len(self._step_rows)

        self._step_groups = []
        self._step_buttons = {}
        self._piano_roll_widgets = {}
        self._playhead_step = None
        # One info row per part, followed by an inline column-header row
        # (Bar / step numbers) and then that part's bar rows (collapsed/
        # expanded together via row-hiding - see _set_part_sequencer_expanded),
        # plus one thin spacer row between parts. A row index that held a
        # cell widget (e.g. a Mute button) in a previous call can be reused
        # here for a blank filler cell - and setItem() doesn't clear a
        # pre-existing cell widget - so the table is fully reset first
        # rather than just re-sized.
        self._sequencer_table.setRowCount(0)
        self._sequencer_table.setRowCount(num_parts * (2 + num_bars) + num_parts - 1)
        default_expanded = self._sequencer_toggle_btn.isChecked()

        bold_font = QFont()
        bold_font.setBold(True)

        row_cursor = 0
        for info in self._step_rows:
            part = info["part"]
            part_idx = len(self._step_groups)
            shade = BG_FIELD_HOVER if part_idx % 2 else BG_FIELD

            info_row = row_cursor
            header_row = info_row + 1
            expanded = self._part_sequencer_expanded.get(part_idx, default_expanded)
            self._part_sequencer_expanded[part_idx] = expanded
            self._step_groups.append({
                "info_row": info_row, "header_row": header_row,
                "seq_start": header_row + 1, "num_bars": num_bars,
            })
            self._sequencer_table.setRowHeight(info_row, STEPS_INFO_ROW_HEIGHT)

            mute_btn = QPushButton("M")
            mute_btn.setCheckable(True)
            mute_btn.setFixedSize(30, 28)
            mute_btn.setChecked(self._mute_bit(pattern, info["bit"]))
            self._style_mute_button(mute_btn)
            mute_btn.toggled.connect(lambda checked, i=part_idx: self._on_mute_toggled(i, checked))

            solo_btn = QPushButton("S")
            solo_btn.setCheckable(True)
            solo_btn.setFixedSize(30, 28)
            solo_btn.setChecked(False)
            self._style_solo_button(solo_btn)
            solo_btn.toggled.connect(lambda checked, i=part_idx: self._on_solo_toggled(i, checked))

            part_label = QLabel(info["label"])
            part_label.setFont(bold_font)
            part_label.setToolTip(info["label"])
            part_label.setFixedWidth(PART_LABEL_COL_WIDTH)

            sample_combo = None
            # No dedicated Mute/Solo/Part/Sample/Copy/Paste columns - this
            # cell spans the whole row (the same columns the step grid uses
            # below) instead, since that space is otherwise blank on the
            # info row anyway and reserving it as real columns pushed the
            # step grid on bar rows out of alignment with the left edge.
            info_cell = QWidget()
            info_cell_layout = QHBoxLayout(info_cell)
            info_cell_layout.setContentsMargins(4, 0, 4, 0)
            info_cell_layout.setSpacing(6)
            info_cell_layout.addWidget(mute_btn)
            info_cell_layout.addWidget(solo_btn)
            info_cell_layout.addWidget(part_label)
            if hasattr(part, "sample_pointer"):
                idx = part.sample_pointer + 1 if part.sample_pointer >= 0 else 0
                sample_combo = self._make_sample_combo(sample_names, idx)
                sample_combo.activated.connect(
                    lambda _, p=part, c=sample_combo: self._on_steps_sample_activated(p, c)
                )
                info_cell_layout.addWidget(sample_combo)
            else:
                info_cell_layout.addWidget(QLabel("-"))

            piano_roll_btn = None
            if info["kind"] == "gate":
                piano_roll_btn = QPushButton(icons.icon("music"), tr("tab_patterns.piano"))
                piano_roll_btn.setCheckable(True)
                piano_roll_btn.setChecked(self._part_piano_roll_mode.get(part_idx, False))
                piano_roll_btn.setToolTip(tr("tab_patterns.piano_roll_toggle_tooltip"))
                piano_roll_btn.toggled.connect(lambda checked, i=part_idx: self._on_piano_roll_toggled(i, checked))
                info_cell_layout.addWidget(piano_roll_btn)

            copy_btn = QPushButton(icons.icon("copy"), "")
            copy_btn.setFixedSize(30, 28)
            copy_btn.setToolTip(tr("tab_patterns.copy_steps_tooltip"))
            copy_btn.clicked.connect(lambda _, i=part_idx: self._copy_steps(i))
            info_cell_layout.addWidget(copy_btn)

            paste_btn = QPushButton(icons.icon("paste"), "")
            paste_btn.setFixedSize(30, 28)
            paste_btn.setToolTip(tr("tab_patterns.paste_steps_tooltip"))
            paste_btn.setEnabled(False)
            paste_btn.clicked.connect(lambda _, i=part_idx: self._paste_steps(i))
            info_cell_layout.addWidget(paste_btn)
            info_cell_layout.addStretch(1)

            # Sits at the far right of the row so it reads as "collapse
            # just this part", separate from the "Collapse/Expand All"
            # button above the whole table.
            collapse_btn = QPushButton("")
            collapse_btn.setCheckable(True)
            collapse_btn.setFixedSize(26, 28)
            collapse_btn.setChecked(expanded)
            self._style_collapse_button(collapse_btn, expanded)
            collapse_btn.toggled.connect(lambda checked, i=part_idx: self._set_part_sequencer_expanded(i, checked))
            info_cell_layout.addWidget(collapse_btn)

            self._sequencer_table.setCellWidget(info_row, 0, info_cell)
            self._sequencer_table.setSpan(info_row, 0, 1, SEQ_TOTAL_COLUMNS)

            self._step_groups[-1].update({
                "mute_btn": mute_btn, "solo_btn": solo_btn, "sample_combo": sample_combo,
                "copy_btn": copy_btn, "paste_btn": paste_btn, "collapse_btn": collapse_btn,
                "piano_roll_btn": piano_roll_btn,
            })

            piano_mode = info["kind"] == "gate" and self._part_piano_roll_mode.get(part_idx, False)

            if piano_mode:
                self._sequencer_table.setRowHeight(header_row, PIANO_ROLL_AREA_HEIGHT)
            else:
                # Inline column-header row - repeats "Bar" / step-number labels
                # directly above this part's own bar rows, since the table's
                # single sticky header (now hidden) could only ever sit above
                # the very first row in the whole table.
                self._sequencer_table.setRowHeight(header_row, STEPS_COLHEADER_ROW_HEIGHT)
                for col_idx, label in enumerate(self._sequencer_header_labels()):
                    header_item = QTableWidgetItem(label)
                    header_item.setFlags(Qt.ItemFlag.NoItemFlags)
                    header_item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
                    header_item.setBackground(QColor(BG_PANEL))
                    header_item.setForeground(QColor(TEXT_DIM))
                    header_item.setFont(bold_font)
                    self._sequencer_table.setItem(header_row, col_idx, header_item)
            self._sequencer_table.setRowHidden(header_row, not expanded)

            row_cursor += 2
            seq_group_start = row_cursor

            if piano_mode:
                for bar in range(num_bars):
                    row = seq_group_start + bar
                    self._sequencer_table.setRowHeight(row, 1)
                    self._sequencer_table.setRowHidden(row, not expanded)
                get_note, set_note, get_gate, set_gate = self._make_piano_roll_callbacks(part)
                piano = PianoRollWidget(get_note, set_note, get_gate, set_gate, num_bars, steps_per_bar)
                piano.edited.connect(lambda i=part_idx: self._on_piano_roll_edited(i))
                self._sequencer_table.setSpan(header_row, 0, 1 + num_bars, SEQ_TOTAL_COLUMNS)
                self._sequencer_table.setCellWidget(header_row, 0, piano)
                self._piano_roll_widgets[part_idx] = piano
            else:
                for bar in range(num_bars):
                    row = seq_group_start + bar
                    self._set_readonly_item(row, SEQ_BAR_COL, str(bar + 1), table=self._sequencer_table,
                                             alignment=Qt.AlignmentFlag.AlignCenter)
                    bar_item = self._sequencer_table.item(row, SEQ_BAR_COL)
                    bar_item.setBackground(QColor(shade))
                    bar_item.setForeground(QColor(TEXT_DIM))
                    self._sequencer_table.setRowHidden(row, not expanded)
                    for col in range(steps_per_bar):
                        global_step = bar * steps_per_bar + col
                        if global_step >= STEP_DATA_CAPACITY:
                            break
                        on = self._get_step_state(info, global_step)
                        step_btn = QPushButton("")
                        step_btn.setCheckable(True)
                        step_btn.setChecked(on)
                        step_btn.setFixedSize(22, 24)
                        self._style_step_button(step_btn, on)
                        step_btn.toggled.connect(
                            lambda checked, r=row, c=col, g=global_step: self._on_step_toggled(r, c, g, checked)
                        )
                        self._step_buttons[(part_idx, global_step)] = step_btn
                        # Wrapped so the fixed-size button is centered in the step
                        # column instead of hugging the cell's top-left corner
                        # when the column is wider than the button.
                        step_cell = QWidget()
                        step_cell_layout = QHBoxLayout(step_cell)
                        step_cell_layout.setContentsMargins(0, 0, 0, 0)
                        step_cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        step_cell_layout.addWidget(step_btn)
                        self._sequencer_table.setCellWidget(row, SEQ_STEP_TABLE_COL[col], step_cell)

                    for divider_col, boundary_step in SEQ_DIVIDER_TABLE_COLS:
                        if boundary_step + 1 >= steps_per_bar:
                            continue
                        divider_item = QTableWidgetItem("")
                        divider_item.setFlags(Qt.ItemFlag.NoItemFlags)
                        divider_item.setBackground(QColor(BORDER_LIGHT))
                        self._sequencer_table.setItem(row, divider_col, divider_item)

            row_cursor = seq_group_start + num_bars
            if part_idx < num_parts - 1:
                spacer_row = row_cursor
                self._sequencer_table.setRowHeight(spacer_row, STEPS_SPACER_ROW_HEIGHT)
                spacer_item = QTableWidgetItem("")
                spacer_item.setFlags(Qt.ItemFlag.NoItemFlags)
                spacer_item.setBackground(QColor(BORDER))
                self._sequencer_table.setItem(spacer_row, 0, spacer_item)
                self._sequencer_table.setSpan(spacer_row, 0, 1, SEQ_TOTAL_COLUMNS)
                row_cursor += 1

        self._apply_steps_column_visibility(steps_per_bar)
        self._refresh_paste_buttons()
        self._sequencer_table.resizeColumnsToContents()
        self._sequencer_table.setColumnWidth(SEQ_BAR_COL, 40)
        for divider_col, _ in SEQ_DIVIDER_TABLE_COLS:
            self._sequencer_table.setColumnWidth(divider_col, DIVIDER_COL_WIDTH)
        for step in range(STEPS_MAX_STEPS):
            self._sequencer_table.setColumnWidth(SEQ_STEP_TABLE_COL[step], STEP_COL_WIDTH)

    def _apply_steps_column_visibility(self, num_steps):
        for step in range(STEPS_MAX_STEPS):
            self._sequencer_table.setColumnHidden(SEQ_STEP_TABLE_COL[step], step >= num_steps)
        for divider_col, boundary_step in SEQ_DIVIDER_TABLE_COLS:
            self._sequencer_table.setColumnHidden(divider_col, boundary_step + 1 >= num_steps)

    def _make_sample_combo(self, sample_names, current_index):
        """A closed dropdown (not a text field) whose popup has a built-in
        search box above the scrollable sample list."""
        combo = SearchableComboBox()
        combo.setMinimumWidth(SAMPLE_COL_WIDTH - 10)
        combo.add_items_with_data((name, i) for i, name in enumerate(sample_names))
        combo.set_current_data(max(0, min(current_index, len(sample_names) - 1)))
        combo.setToolTip(combo.currentText())
        combo.currentTextChanged.connect(combo.setToolTip)
        return combo

    def _steps_sample_combo_for_part(self, part):
        for i, info in enumerate(self._step_rows):
            if info["part"] is part:
                return self._step_groups[i].get("sample_combo")
        return None

    def _parts_row_for_part(self, part):
        for i, (_, p) in enumerate(self._part_rows):
            if p is part:
                return i
        return -1

    def _sync_combo(self, combo, real_index):
        if combo and combo.currentData() != real_index:
            combo.blockSignals(True)
            combo.set_current_data(real_index)
            combo.blockSignals(False)

    def _on_parts_sample_activated(self, part, combo):
        real_index = combo.currentData()
        if real_index is not None:
            self._on_parts_sample_changed(part, real_index)

    def _on_steps_sample_activated(self, part, combo):
        real_index = combo.currentData()
        if real_index is not None:
            self._on_steps_sample_changed(part, real_index)

    def _on_parts_sample_changed(self, part, index):
        part.sample_pointer = index - 1
        self._sync_combo(self._steps_sample_combo_for_part(part), index)

    def _on_steps_sample_changed(self, part, index):
        part.sample_pointer = index - 1
        row = self._parts_row_for_part(part)
        if row >= 0:
            self._sync_combo(self._parts_table.cellWidget(row, PARTS_SAMPLE_COL), index)

    def _get_step_state(self, info, step):
        part = info["part"]
        if info["kind"] == "bits":
            data = part.sequence_data.data
            byte_i, bit_i = divmod(step, 8)
            return byte_i < len(data) and bool(data[byte_i] & (1 << bit_i))
        data = part.sequence_data_gate.data
        return step < len(data) and data[step] != 0

    def _set_step_state(self, info, step, on):
        part = info["part"]
        if info["kind"] == "bits":
            data = part.sequence_data.data
            byte_i, bit_i = divmod(step, 8)
            if byte_i >= len(data):
                return
            if on:
                data[byte_i] |= (1 << bit_i)
            else:
                data[byte_i] &= ~(1 << bit_i) & 0xFF
        else:
            data = part.sequence_data_gate.data
            if step < len(data):
                data[step] = 1 if on else 0

    def _step_button_at(self, row, col):
        """Step buttons are wrapped in a centering container widget, so the
        cell widget itself isn't the button - look inside it."""
        cell = self._sequencer_table.cellWidget(row, SEQ_STEP_TABLE_COL[col])
        return cell.findChild(QPushButton) if cell else None

    def _on_step_toggled(self, row, col, global_step, checked):
        info = self._step_rows[self._part_index_for_table_row(row)]
        if checked and info["kind"] == "gate":
            # A Keyboard step turned on from the plain grid (rather than
            # picked explicitly in the Piano Roll) has no note of its own
            # yet - default it to C4, same as a fresh/never-edited note
            # byte, so it plays at a sane pitch instead of MIDI note 0.
            note_data = info["part"].sequence_data_note.data
            if global_step < len(note_data) and note_data[global_step] == 0:
                note_data[global_step] = DEFAULT_KEYBOARD_NOTE
        self._set_step_state(info, global_step, checked)
        btn = self._step_button_at(row, col)
        if btn:
            self._style_step_button(btn, checked)
        self._refresh_sequencer_playback()

    def _part_index_for_table_row(self, table_row):
        for i, group in enumerate(self._step_groups):
            if group["seq_start"] <= table_row < group["seq_start"] + group["num_bars"]:
                return i
        return -1

    def _style_step_button(self, btn, on, playhead=False):
        bg = STEP_ON_COLOR if on else BG_FIELD
        border = STEP_ON_COLOR if on else BORDER
        border_width = 1
        if playhead:
            border = PLAYHEAD_COLOR
            border_width = 2
        btn.setStyleSheet(
            f"QPushButton {{ background-color: {bg}; border: {border_width}px solid {border}; border-radius: 3px; }}"
            f"QPushButton:hover {{ border-color: {STEP_ON_COLOR}; }}"
        )

    def _style_mute_button(self, btn):
        bg = MUTE_ON_COLOR if btn.isChecked() else BG_FIELD
        btn.setStyleSheet(
            f"QPushButton {{ background-color: {bg}; border: 1px solid {BORDER}; "
            f"border-radius: 4px; font-weight: 600; }}"
        )

    def _style_solo_button(self, btn):
        bg = SOLO_ON_COLOR if btn.isChecked() else BG_FIELD
        color = "#0b0c0d" if btn.isChecked() else None
        style = (
            f"QPushButton {{ background-color: {bg}; border: 1px solid {BORDER}; "
            f"border-radius: 4px; font-weight: 600;"
        )
        if color:
            style += f" color: {color};"
        style += " }"
        btn.setStyleSheet(style)

    def _mute_bit(self, pattern, bit):
        return bool(pattern.mute_status & (1 << bit))

    def _set_mute_bit(self, pattern, bit, on):
        if on:
            pattern.mute_status |= (1 << bit)
        else:
            pattern.mute_status &= ~(1 << bit) & 0xFFFF

    def _on_mute_toggled(self, part_idx, checked):
        if self._current_pattern is None:
            return
        info = self._step_rows[part_idx]
        self._set_mute_bit(self._current_pattern, info["bit"], checked)
        self._style_mute_button(self._step_groups[part_idx]["mute_btn"])
        self._refresh_sequencer_playback()

    def _on_solo_toggled(self, part_idx, checked):
        if self._current_pattern is None:
            return
        pattern = self._current_pattern
        bit = self._step_rows[part_idx]["bit"]

        if checked:
            if not self._solo_bits:
                self._pre_solo_mute_status = pattern.mute_status
            # Only one part may be soloed at a time - uncheck any other solo button.
            for other_idx, other_info in enumerate(self._step_rows):
                if other_idx != part_idx and other_info["bit"] in self._solo_bits:
                    other_btn = self._step_groups[other_idx]["solo_btn"]
                    other_btn.blockSignals(True)
                    other_btn.setChecked(False)
                    other_btn.blockSignals(False)
                    self._style_solo_button(other_btn)
            self._solo_bits = {bit}
        else:
            self._solo_bits.discard(bit)

        if self._solo_bits:
            for info in self._step_rows:
                self._set_mute_bit(pattern, info["bit"], info["bit"] not in self._solo_bits)
        elif self._pre_solo_mute_status is not None:
            pattern.mute_status = self._pre_solo_mute_status
            self._pre_solo_mute_status = None

        self._refresh_mute_buttons()
        self._style_solo_button(self._step_groups[part_idx]["solo_btn"])
        self._refresh_sequencer_playback()

    def _refresh_mute_buttons(self):
        for part_idx, info in enumerate(self._step_rows):
            btn = self._step_groups[part_idx]["mute_btn"]
            btn.blockSignals(True)
            btn.setChecked(self._mute_bit(self._current_pattern, info["bit"]))
            btn.blockSignals(False)
            self._style_mute_button(btn)

    def _copy_steps(self, part_idx):
        info = self._step_rows[part_idx]
        part = info["part"]
        if info["kind"] == "bits":
            self._step_clipboard = ("bits", bytearray(part.sequence_data.data))
        else:
            # Notes travel along with the gate bytes - copying only the
            # gate would silently drop every note set via the Piano Roll
            # once pasted elsewhere.
            self._step_clipboard = (
                "gate", bytearray(part.sequence_data_gate.data), bytearray(part.sequence_data_note.data)
            )
        self._refresh_paste_buttons()

    def _paste_steps(self, part_idx):
        if self._step_clipboard is None:
            return
        kind = self._step_clipboard[0]
        info = self._step_rows[part_idx]
        if info["kind"] != kind:
            return
        if kind == "bits":
            info["part"].sequence_data.data[:] = self._step_clipboard[1]
        else:
            info["part"].sequence_data_gate.data[:] = self._step_clipboard[1]
            info["part"].sequence_data_note.data[:] = self._step_clipboard[2]
        self._refresh_step_buttons(part_idx)
        self._refresh_sequencer_playback()

    def _refresh_step_buttons(self, part_idx):
        if self._part_piano_roll_mode.get(part_idx):
            widget = self._piano_roll_widgets.get(part_idx)
            if widget:
                widget.refresh()
            return
        info = self._step_rows[part_idx]
        group = self._step_groups[part_idx]
        steps_per_bar = self._current_last_step_count()
        for bar in range(group["num_bars"]):
            row = group["seq_start"] + bar
            for col in range(steps_per_bar):
                global_step = bar * steps_per_bar + col
                if global_step >= STEP_DATA_CAPACITY:
                    break
                btn = self._step_button_at(row, col)
                if not btn:
                    continue
                on = self._get_step_state(info, global_step)
                btn.blockSignals(True)
                btn.setChecked(on)
                btn.blockSignals(False)
                self._style_step_button(btn, on)

    def _refresh_paste_buttons(self):
        kind = self._step_clipboard[0] if self._step_clipboard else None
        for part_idx, info in enumerate(self._step_rows):
            self._step_groups[part_idx]["paste_btn"].setEnabled(kind is not None and info["kind"] == kind)

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
        self._stop_sequencer_playback()
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
        self._clipboard_pattern_label = f"{row} - {name}" if name else f"{row} - " + tr("common.empty_placeholder")
        self._clipboard_label.setText(tr("tab_patterns.clipboard_label", label=self._clipboard_pattern_label))
        self._paste_pattern_btn.setEnabled(True)

    def _paste_pattern(self):
        if self._esx is None or self._clipboard_pattern_bytes is None:
            return
        row = self._pattern_table.currentRow()
        if not (0 <= row < len(self._esx.patterns)):
            return

        reply = QMessageBox.question(
            self, tr("tab_patterns.paste_pattern_title"),
            tr("tab_patterns.paste_pattern_confirm", row=row, label=self._clipboard_pattern_label),
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
            QMessageBox.warning(self, tr("tab_patterns.export_pattern_title"), tr("tab_samples.no_esx_file_loaded"))
            return
        row = self._pattern_table.currentRow()
        if not (0 <= row < len(self._esx.patterns)):
            QMessageBox.warning(self, tr("tab_patterns.export_pattern_title"), tr("tab_patterns.no_pattern_selected"))
            return
        if self._current_pattern is self._esx.patterns[row]:
            self.apply_changes()

        pattern = self._esx.patterns[row]
        if pattern.is_empty():
            QMessageBox.information(self, tr("tab_patterns.export_pattern_title"), tr("tab_patterns.pattern_empty_nothing_to_export"))
            return

        name = pattern.name.strip('\x00').strip() or f"pattern_{row}"
        path = os.path.join(get_patterns_dir(), f"{row}_{name}.esxpat")
        try:
            export_pattern(self._esx, row, path)
            QMessageBox.information(
                self, tr("tab_patterns.export_pattern_title"),
                tr("tab_patterns.pattern_saved_to", path=path)
            )
        except Exception as exc:
            report_error("export_pattern", exc)
            QMessageBox.critical(self, tr("tab_samples.export_error_title"), str(exc))

    def _import_pattern(self):
        if self._esx is None:
            QMessageBox.warning(self, tr("tab_patterns.import_pattern_title"), tr("tab_samples.no_esx_file_loaded"))
            return
        path, _ = QFileDialog.getOpenFileName(
            self, tr("tab_patterns.import_pattern_title"), get_patterns_dir(),
            f"{tr('common.esxpat_files_filter')};;{tr('common.all_files_filter')}"
        )
        if not path:
            return
        self.import_pattern_from_path(path)

    def import_pattern_from_path(self, path: str):
        """Import a .esxpat file (as produced by export_pattern) into the
        currently selected pattern slot. Used by both the Import Pattern
        button and the Pattern Browser (double-clicking a saved pattern)."""
        if self._esx is None:
            QMessageBox.warning(self, tr("tab_patterns.import_pattern_title"), tr("tab_samples.no_esx_file_loaded"))
            return
        row = self._pattern_table.currentRow()
        if not (0 <= row < len(self._esx.patterns)):
            QMessageBox.warning(self, tr("tab_patterns.import_pattern_title"), tr("tab_patterns.no_target_slot_selected"))
            return

        existing = self._esx.patterns[row]
        if not existing.is_empty():
            existing_name = existing.name.strip(chr(0)).strip()
            reply = QMessageBox.question(
                self, tr("tab_patterns.import_pattern_title"),
                tr(
                    "tab_patterns.overwrite_pattern_confirm",
                    row=row, name=existing_name or tr("common.empty_placeholder"),
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            new_pattern, warnings = import_pattern(self._esx, path, row)
        except Exception as exc:
            report_error("import_pattern", exc)
            QMessageBox.critical(self, tr("tab_patterns.import_error_title"), str(exc))
            return

        self._set_pattern_row(row, new_pattern)
        if row == self._pattern_table.currentRow():
            self._current_row = row
            self._current_pattern = new_pattern
            self._populate_editor(new_pattern)

        if warnings:
            QMessageBox.warning(self, tr("tab_patterns.import_pattern_title"), "\n".join(warnings))
        else:
            QMessageBox.information(
                self, tr("tab_patterns.import_pattern_title"), tr("tab_patterns.pattern_imported_into_slot", row=row)
            )

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
        self._populate_steps(pattern)

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
                    self._parts_table.item(row, col).setToolTip(label)
                elif kind == "sample":
                    if hasattr(part, attr):
                        idx = part.sample_pointer + 1 if part.sample_pointer >= 0 else 0
                        combo = self._make_sample_combo(sample_names, idx)
                        combo.activated.connect(
                            lambda _, p=part, c=combo: self._on_parts_sample_activated(p, c)
                        )
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
        self._parts_table.setColumnWidth(PARTS_LABEL_COL, PART_LABEL_COL_WIDTH)
        self._parts_table.setColumnWidth(PARTS_SAMPLE_COL, SAMPLE_COL_WIDTH)

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

    def _set_readonly_item(self, row, col, text, table=None, alignment=None):
        table = table if table is not None else self._parts_table
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if alignment is not None:
            item.setTextAlignment(int(alignment))
        table.setItem(row, col, item)

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
                        real_index = combo.currentData()
                        if real_index is not None:
                            part.sample_pointer = real_index - 1
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

