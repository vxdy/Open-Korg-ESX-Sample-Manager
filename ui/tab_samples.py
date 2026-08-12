import os
import wave

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QFormLayout, QLineEdit, QLabel,
    QPushButton, QComboBox, QSpinBox, QHeaderView, QAbstractItemView,
    QGroupBox, QFileDialog, QMessageBox, QDialog,
    QDialogButtonBox, QMenu
)
from PyQt6.QtCore import Qt

from esx.constants import PlayLevel, StretchStep, NUM_SAMPLES_MONO, NUM_SAMPLES
from esx.sample import Sample
from ui.waveform_widget import WaveformWidget
from ui.error_log import report_error
from ui import icons


class TabSamples(QWidget):
    def __init__(self):
        super().__init__()
        self._esx = None
        self._current_sample = None
        self._audio_player = None
        self._deleted_sample_indices = set()
        self.import_as_mono = True
        self._setup_ui()
        self._init_player()

    def _init_player(self):
        try:
            from audio.audio_player import AudioPlayer
            self._audio_player = AudioPlayer()
        except Exception:
            self._audio_player = None

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        title = QLabel("Samples (384: 256 mono + 128 stereo)")
        title.setStyleSheet("font-weight: 600; color: #9aa0a8;")
        left_layout.addWidget(title)
        self._sample_table = QTableWidget()
        self._sample_table.setColumnCount(5)
        self._sample_table.setHorizontalHeaderLabels(["#", "Name", "Type", "Rate", "Duration"])
        self._sample_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._sample_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._sample_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._sample_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._sample_table.verticalHeader().setVisible(False)
        self._sample_table.setAlternatingRowColors(True)
        self._sample_table.selectionModel().selectionChanged.connect(self._on_sample_selected)
        self._sample_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._sample_table.customContextMenuRequested.connect(self._show_context_menu)
        left_layout.addWidget(self._sample_table)
        splitter.addWidget(left_widget)

        right_tabs = QTabWidget()

        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setSpacing(10)

        form_group = QGroupBox("Sample Properties")
        form = QFormLayout(form_group)
        form.setSpacing(8)
        form.setContentsMargins(10, 14, 10, 10)

        self._name_edit = QLineEdit()
        self._name_edit.setMaxLength(8)
        form.addRow("Name:", self._name_edit)

        self._sample_rate_label = QLabel("-")
        form.addRow("Sample Rate:", self._sample_rate_label)

        self._num_frames_label = QLabel("-")
        form.addRow("Frames:", self._num_frames_label)

        self._duration_label = QLabel("-")
        form.addRow("Duration:", self._duration_label)

        self._start_label = QLabel("-")
        form.addRow("Start:", self._start_label)

        self._end_label = QLabel("-")
        form.addRow("End:", self._end_label)

        self._loop_start_spin = QSpinBox()
        self._loop_start_spin.setRange(0, 0)
        self._loop_start_spin.setToolTip(
            "Loop start frame. Only stored for mono samples; stereo sample "
            "headers have no loop-start field."
        )
        self._loop_start_spin.valueChanged.connect(self._on_loop_start_changed)
        form.addRow("Loop Start:", self._loop_start_spin)

        self._play_level_combo = QComboBox()
        self._play_level_combo.addItem("0 dB", int(PlayLevel.DB_0))
        self._play_level_combo.addItem("+12 dB", int(PlayLevel.DB_12))
        form.addRow("Play Level:", self._play_level_combo)

        self._stretch_step_combo = QComboBox()
        self._stretch_step_combo.addItem("0 (Off)", int(StretchStep.OFF))
        for step in range(1, 129):
            self._stretch_step_combo.addItem(str(step), step - 1)
        form.addRow("Stretch Step:", self._stretch_step_combo)

        editor_layout.addWidget(form_group)

        waveform_group = QGroupBox("Waveform")
        waveform_layout = QVBoxLayout(waveform_group)
        self._waveform = WaveformWidget()
        waveform_layout.addWidget(self._waveform)
        editor_layout.addWidget(waveform_group)

        playback_group = QGroupBox("Audio Playback")
        playback_layout = QHBoxLayout(playback_group)
        self._play_btn = QPushButton(icons.icon("play"), "Play")
        self._stop_btn = QPushButton(icons.icon("stop"), "Stop")
        self._play_btn.clicked.connect(self._play_sample)
        self._stop_btn.clicked.connect(self._stop_sample)
        playback_layout.addWidget(self._play_btn)
        playback_layout.addWidget(self._stop_btn)
        editor_layout.addWidget(playback_group)
        editor_layout.addStretch()

        right_tabs.addTab(editor_widget, "Sample Editor")

        usage_widget = QWidget()
        usage_layout = QVBoxLayout(usage_widget)
        usage_layout.addWidget(QLabel("Patterns using this sample:"))
        self._usage_table = QTableWidget()
        self._usage_table.setColumnCount(2)
        self._usage_table.setHorizontalHeaderLabels(["Pattern #", "Part"])
        self._usage_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._usage_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._usage_table.verticalHeader().setVisible(False)
        self._usage_table.setAlternatingRowColors(True)
        usage_layout.addWidget(self._usage_table)
        right_tabs.addTab(usage_widget, "Pattern Usage")

        splitter.addWidget(right_tabs)
        splitter.setSizes([350, 650])

    def update_data(self, esx_file):
        if self._esx is not esx_file:
            self._deleted_sample_indices.clear()
        self._esx = esx_file
        selected_row = self._sample_table.currentRow()
        samples = esx_file.samples

        self._sample_table.setRowCount(len(samples))
        for i, sample in enumerate(samples):
            self._set_sample_row(i, sample)

        if 0 <= selected_row < len(samples):
            self._sample_table.selectRow(selected_row)
        elif samples:
            self._sample_table.selectRow(0)

    def _set_sample_row(self, row: int, sample):
        self._sample_table.setItem(row, 0, QTableWidgetItem(str(row)))
        name = sample.name.strip('\x00').strip()
        self._sample_table.setItem(row, 1, QTableWidgetItem(name if name else "(empty)"))
        stype = "Stereo" if sample.is_stereo_original else "Mono"
        self._sample_table.setItem(row, 2, QTableWidgetItem(stype))
        self._sample_table.setItem(row, 3, QTableWidgetItem(str(sample.sample_rate)))
        self._sample_table.setItem(row, 4, QTableWidgetItem(f"{sample.duration_seconds():.3f}s"))

    def _on_sample_selected(self):
        if self._esx is None:
            return
        row = self._sample_table.currentRow()
        if 0 <= row < len(self._esx.samples):
            self._current_sample = self._esx.samples[row]
            self._populate_editor(self._current_sample)
            self._populate_usage(self._current_sample)

    def _populate_editor(self, sample):
        self._name_edit.setText(sample.name.strip('\x00'))
        self._sample_rate_label.setText(str(sample.sample_rate))
        self._num_frames_label.setText(str(sample.num_frames))
        self._duration_label.setText(f"{sample.duration_seconds():.3f} s")
        self._start_label.setText(str(sample.start))
        self._end_label.setText(str(sample.end))
        max_frame = max(0, sample.num_frames - 1)
        self._loop_start_spin.setRange(0, max_frame)
        self._loop_start_spin.setValue(min(max(sample.loop_start, 0), max_frame))
        self._loop_start_spin.setEnabled(not sample.is_stereo_original)
        play_level_index = self._play_level_combo.findData(int(sample.play_level))
        self._play_level_combo.setCurrentIndex(max(0, play_level_index))
        stretch_step_index = self._stretch_step_combo.findData(int(sample.stretch_step))
        self._stretch_step_combo.setCurrentIndex(max(0, stretch_step_index))
        self._waveform.set_audio(
            sample.get_audio_channel_both(), sample.start, sample.end, sample.loop_start
        )

    def _populate_usage(self, sample):
        if self._esx is None:
            return

        usage = []
        sample_idx = self._esx.samples.index(sample)
        for pi, pattern in enumerate(self._esx.patterns):
            for di, part in enumerate(pattern.drum_parts):
                if part.sample_pointer == sample_idx:
                    usage.append((pi, f"Drum {di + 1}"))
            for ki, part in enumerate(pattern.keyboard_parts):
                if part.sample_pointer == sample_idx:
                    usage.append((pi, f"Keyboard {ki + 1}"))
            for si, part in enumerate(pattern.stretch_slice_parts):
                if part.sample_pointer == sample_idx:
                    usage.append((pi, f"Stretch/Slice {si + 1}"))

        self._usage_table.setRowCount(len(usage))
        for i, (pattern_idx, part_name) in enumerate(usage):
            self._usage_table.setItem(i, 0, QTableWidgetItem(str(pattern_idx)))
            self._usage_table.setItem(i, 1, QTableWidgetItem(part_name))

    def _on_loop_start_changed(self, value: int):
        self._waveform.set_loop_start(value)

    def _play_sample(self):
        if self._current_sample is None or self._audio_player is None:
            return
        try:
            wav_bytes = self._current_sample.to_wav_bytes()
            if wav_bytes:
                self._audio_player.play(wav_bytes, self._current_sample.sample_rate)
        except Exception as exc:
            report_error("play_sample", exc)
            print(f"Playback error: {exc}")

    def _stop_sample(self):
        if self._audio_player:
            self._audio_player.stop()

    def apply_changes(self):
        if self._esx is not None:
            for sample_idx in self._deleted_sample_indices:
                self._clear_sample_references(sample_idx)
        if self._current_sample is None:
            return
        self._current_sample.name = self._name_edit.text()
        self._current_sample.play_level = PlayLevel(self._play_level_combo.currentData())
        self._current_sample.stretch_step = StretchStep(self._stretch_step_combo.currentData())
        if not self._current_sample.is_stereo_original:
            self._current_sample.loop_start = self._loop_start_spin.value()

    def import_samples(self):
        if self._esx is None:
            QMessageBox.warning(self, "Import", "No ESX file loaded")
            return

        self.apply_changes()
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Import WAV Sample(s)",
            "",
            "WAV Files (*.wav);;All Files (*)"
        )
        if not files:
            return

        force_mono = self.import_as_mono
        selected_row = self._sample_table.currentRow()
        imported = []
        errors = []
        next_mono_start = selected_row if 0 <= selected_row < NUM_SAMPLES_MONO else 0
        next_stereo_start = selected_row if selected_row >= NUM_SAMPLES_MONO else NUM_SAMPLES_MONO

        for file_index, filepath in enumerate(files):
            try:
                source_channels = self._wav_channel_count(filepath)
                want_stereo = source_channels > 1 and not force_mono
                slot = None

                if file_index == 0 and 0 <= selected_row < NUM_SAMPLES:
                    selected_is_stereo_slot = selected_row >= NUM_SAMPLES_MONO
                    if force_mono and not selected_is_stereo_slot:
                        slot = selected_row
                    elif not force_mono:
                        if selected_is_stereo_slot and source_channels > 1:
                            slot = selected_row
                            want_stereo = True
                        elif not selected_is_stereo_slot:
                            slot = selected_row
                            want_stereo = False

                if slot is not None and not self._esx.samples[slot].is_empty():
                    reply = QMessageBox.question(
                        self,
                        "Overwrite Sample",
                        f"Sample slot {slot} is not empty. Overwrite it?",
                        QMessageBox.StandardButton.Yes
                        | QMessageBox.StandardButton.No
                        | QMessageBox.StandardButton.Cancel
                    )
                    if reply == QMessageBox.StandardButton.Cancel:
                        break
                    if reply == QMessageBox.StandardButton.No:
                        slot = None

                if slot is None:
                    slot = self._find_next_empty_slot(
                        next_stereo_start if want_stereo else next_mono_start,
                        want_stereo
                    )
                    if slot is None:
                        kind = "stereo" if want_stereo else "mono"
                        raise ValueError(f"No empty {kind} sample slots available")

                as_mono = force_mono or slot < NUM_SAMPLES_MONO or source_channels == 1
                new_sample = Sample.from_wav_file(filepath, slot, as_mono=as_mono)
                if slot >= NUM_SAMPLES_MONO and new_sample.is_stereo_original is False:
                    raise ValueError("Cannot store a mono import in a stereo sample slot")
                if slot < NUM_SAMPLES_MONO and new_sample.is_stereo_original:
                    raise ValueError("Cannot store a stereo import in a mono sample slot")

                self._esx.samples[slot] = new_sample
                self._deleted_sample_indices.discard(slot)
                imported.append(slot)
                if slot < NUM_SAMPLES_MONO:
                    next_mono_start = slot + 1
                else:
                    next_stereo_start = slot + 1
            except Exception as exc:
                report_error("import_sample", exc)
                errors.append(f"{filepath}: {exc}")

        if imported:
            self.update_data(self._esx)
            self._sample_table.selectRow(imported[-1])
            self._on_sample_selected()

        if errors:
            QMessageBox.warning(self, "Import Errors", "\n".join(errors))
        elif imported:
            QMessageBox.information(self, "Import", f"Imported {len(imported)} sample(s)")

    def _selected_rows(self) -> list[int]:
        return sorted({idx.row() for idx in self._sample_table.selectionModel().selectedRows()})

    def delete_selected_samples(self):
        if self._esx is None:
            QMessageBox.warning(self, "Delete", "No ESX file loaded")
            return
        rows = self._selected_rows()
        if not rows:
            QMessageBox.warning(self, "Delete", "No sample selected")
            return
        self._delete_samples(rows)

    def _delete_samples(self, rows: list[int]):
        non_empty_rows = [
            r for r in rows
            if 0 <= r < len(self._esx.samples) and not self._esx.samples[r].is_empty()
        ]
        if not non_empty_rows:
            return

        if len(non_empty_rows) == 1:
            message = f"Delete sample {non_empty_rows[0]} and clear pattern references to it?"
        else:
            message = (
                f"Delete {len(non_empty_rows)} samples "
                f"({', '.join(str(r) for r in non_empty_rows)}) "
                "and clear pattern references to them?"
            )

        reply = QMessageBox.question(
            self, "Delete Sample(s)", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for row in non_empty_rows:
            self._esx.samples[row].clear()
            self._deleted_sample_indices.add(row)
            self._clear_sample_references(row)

        self.update_data(self._esx)
        self._sample_table.selectRow(non_empty_rows[0])
        self._on_sample_selected()

    def _show_context_menu(self, pos):
        if self._esx is None:
            return
        rows = self._selected_rows()
        if not rows:
            return

        menu = QMenu(self)
        export_action = menu.addAction(
            icons.icon("file-export"),
            "Export as WAV..." if len(rows) == 1 else f"Export {len(rows)} Samples as WAV..."
        )
        delete_action = menu.addAction(
            icons.icon("trash"),
            "Delete Sample" if len(rows) == 1 else f"Delete {len(rows)} Samples"
        )
        action = menu.exec(self._sample_table.viewport().mapToGlobal(pos))
        if action == export_action:
            self._export_samples(rows)
        elif action == delete_action:
            self._delete_samples(rows)

    def _export_samples(self, rows: list[int]):
        non_empty = [
            (r, self._esx.samples[r]) for r in rows
            if 0 <= r < len(self._esx.samples) and not self._esx.samples[r].is_empty()
        ]
        if not non_empty:
            QMessageBox.information(self, "Export", "No non-empty samples selected.")
            return

        if len(non_empty) == 1:
            idx, sample = non_empty[0]
            name = sample.name.strip('\x00').strip() or f"sample_{idx}"
            default_name = f"{idx}_{name}.wav"
            path, _ = QFileDialog.getSaveFileName(
                self, "Export Sample as WAV", default_name,
                "WAV Files (*.wav);;All Files (*)"
            )
            if not path:
                return
            try:
                with open(path, 'wb') as f:
                    f.write(sample.to_export_wav_bytes())
                QMessageBox.information(self, "Export", f"Exported to:\n{path}")
            except Exception as exc:
                report_error("export_sample", exc)
                QMessageBox.critical(self, "Export Error", str(exc))
            return

        directory = QFileDialog.getExistingDirectory(self, "Select Export Directory")
        if not directory:
            return

        exported = 0
        errors = []
        for idx, sample in non_empty:
            name = sample.name.strip('\x00').strip() or f"sample_{idx}"
            path = os.path.join(directory, f"{idx}_{name}.wav")
            try:
                with open(path, 'wb') as f:
                    f.write(sample.to_export_wav_bytes())
                exported += 1
            except Exception as exc:
                report_error("export_sample", exc)
                errors.append(f"{idx} ({name}): {exc}")

        if errors:
            QMessageBox.warning(self, "Export Errors", "\n".join(errors))
        if exported:
            QMessageBox.information(self, "Export", f"Exported {exported} sample(s) to:\n{directory}")

    def delete_unused_samples(self):
        if self._esx is None:
            QMessageBox.warning(self, "Delete Unused Samples", "No ESX file loaded")
            return

        self.apply_changes()
        unused_samples = self._get_unused_nonempty_samples()
        if not unused_samples:
            QMessageBox.information(
                self,
                "Delete Unused Samples",
                "No unused samples found."
            )
            return

        if not self._confirm_delete_unused_samples(unused_samples):
            return

        for sample_idx, _ in unused_samples:
            self._esx.samples[sample_idx].clear()
            self._deleted_sample_indices.add(sample_idx)

        selected_row = self._sample_table.currentRow()
        self.update_data(self._esx)
        if 0 <= selected_row < len(self._esx.samples):
            self._sample_table.selectRow(selected_row)
            self._on_sample_selected()

        QMessageBox.information(
            self,
            "Delete Unused Samples",
            f"Deleted {len(unused_samples)} unused sample(s)."
        )

    def _confirm_delete_unused_samples(self, unused_samples) -> bool:
        dialog = QDialog(self)
        dialog.setWindowTitle("Delete Unused Samples")
        dialog.resize(640, 420)

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(
            f"The following {len(unused_samples)} sample(s) are not used in any pattern:"
        ))

        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["#", "Name", "Type", "Rate", "Duration"])
        table.setRowCount(len(unused_samples))
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        for row, (sample_idx, sample) in enumerate(unused_samples):
            name = sample.name.strip('\x00').strip() or "(empty)"
            stype = "Stereo" if sample.is_stereo_original else "Mono"
            table.setItem(row, 0, QTableWidgetItem(str(sample_idx)))
            table.setItem(row, 1, QTableWidgetItem(name))
            table.setItem(row, 2, QTableWidgetItem(stype))
            table.setItem(row, 3, QTableWidgetItem(str(sample.sample_rate)))
            table.setItem(row, 4, QTableWidgetItem(f"{sample.duration_seconds():.3f}s"))

        layout.addWidget(table)
        layout.addWidget(QLabel("Delete these samples now? This keeps sample slots in place."))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Delete Listed Samples")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        return dialog.exec() == QDialog.DialogCode.Accepted

    def _get_unused_nonempty_samples(self):
        used_indices = self._get_used_sample_indices()
        return [
            (idx, sample)
            for idx, sample in enumerate(self._esx.samples)
            if idx not in used_indices and not sample.is_empty()
        ]

    def _get_used_sample_indices(self):
        used_indices = set()
        for pattern in self._esx.patterns:
            for part in pattern.drum_parts:
                if 0 <= part.sample_pointer < len(self._esx.samples):
                    used_indices.add(part.sample_pointer)
            for part in pattern.keyboard_parts:
                if 0 <= part.sample_pointer < len(self._esx.samples):
                    used_indices.add(part.sample_pointer)
            for part in pattern.stretch_slice_parts:
                if 0 <= part.sample_pointer < len(self._esx.samples):
                    used_indices.add(part.sample_pointer)
        return used_indices

    def _clear_sample_references(self, sample_idx: int):
        for pattern in self._esx.patterns:
            for part in pattern.drum_parts:
                if part.sample_pointer == sample_idx:
                    part.sample_pointer = -1
            for part in pattern.keyboard_parts:
                if part.sample_pointer == sample_idx:
                    part.sample_pointer = -1
            for part in pattern.stretch_slice_parts:
                if part.sample_pointer == sample_idx:
                    part.sample_pointer = -1

    def _find_next_empty_slot(self, start: int, want_stereo: bool):
        if want_stereo:
            begin = NUM_SAMPLES_MONO
            end = NUM_SAMPLES
        else:
            begin = 0
            end = NUM_SAMPLES_MONO

        start = max(begin, min(start, end - 1))
        for idx in list(range(start, end)) + list(range(begin, start)):
            if self._esx.samples[idx].is_empty():
                return idx
        return None

    def _wav_channel_count(self, filepath: str) -> int:
        with wave.open(filepath, 'rb') as wav_file:
            return wav_file.getnchannels()
