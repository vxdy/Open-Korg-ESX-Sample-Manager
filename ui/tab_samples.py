import os
import wave

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QFormLayout, QLineEdit, QLabel,
    QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QHeaderView,
    QAbstractItemView, QGroupBox, QFileDialog, QMessageBox, QDialog,
    QDialogButtonBox, QMenu, QProgressBar, QCheckBox
)
from PyQt6.QtCore import Qt

from esx.constants import (
    PlayLevel, StretchStep, NUM_SAMPLES_MONO, NUM_SAMPLES, MAX_SAMPLE_MEM_IN_BYTES
)
from esx.sample import Sample
from esx import audio_dsp
from esx.audio_dsp import EQBand
from ui.waveform_widget import WaveformWidget
from ui.eq_curve_widget import EqCurveWidget
from ui.error_log import report_error
from ui import icons
from ui.theme import TEXT_DIM, ACCENT, BG_FIELD, BORDER


class TabSamples(QWidget):
    def __init__(self):
        super().__init__()
        self._esx = None
        self._current_sample = None
        self._audio_player = None
        self._deleted_sample_indices = set()
        self.import_as_mono = True
        self.import_with_plus12db = False
        self._undo_snapshot = None
        self._undo_buttons = []
        self._eq_bands = [EQBand(type="peak", freq=1000.0, gain_db=0.0, q=1.0)]
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

        usage_bar_group = QGroupBox("Sample Memory")
        usage_bar_layout = QHBoxLayout(usage_bar_group)
        usage_bar_layout.setContentsMargins(10, 10, 10, 10)
        usage_bar_layout.setSpacing(10)
        self._memory_bar = QProgressBar()
        self._memory_bar.setRange(0, 1000)
        self._memory_bar.setTextVisible(False)
        self._memory_bar.setFixedHeight(14)
        usage_bar_layout.addWidget(self._memory_bar, 1)
        self._memory_label = QLabel("0.00 MB / 0.00 MB (0.00%)")
        self._memory_label.setStyleSheet(f"color: {TEXT_DIM}; font-weight: 600;")
        usage_bar_layout.addWidget(self._memory_label)
        left_layout.addWidget(usage_bar_group)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Filter by name or #...")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._apply_sample_filter)
        search_layout.addWidget(self._search_edit)
        left_layout.addLayout(search_layout)

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

        right_tabs.addTab(self._build_tools_tab(), "Sample Tools")
        right_tabs.addTab(self._build_eq_tab(), "EQ")

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

    def _build_tools_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)

        waveform_group = QGroupBox("Waveform")
        wf_layout = QVBoxLayout(waveform_group)
        self._tools_waveform = WaveformWidget()
        self._tools_waveform.set_editable(True)
        self._tools_waveform.selectionChanged.connect(self._on_waveform_selection_changed)
        wf_layout.addWidget(self._tools_waveform)
        wf_hint = QLabel("Drag the green (start) / red (end) handles to set the Trim/Cut selection.")
        wf_hint.setStyleSheet(f"color: {TEXT_DIM};")
        wf_hint.setWordWrap(True)
        wf_layout.addWidget(wf_hint)
        layout.addWidget(waveform_group)

        normalize_group = QGroupBox("Normalize")
        normalize_form = QFormLayout(normalize_group)
        normalize_form.setSpacing(8)

        peak_row = QHBoxLayout()
        self._normalize_peak_spin = QDoubleSpinBox()
        self._normalize_peak_spin.setRange(-24.0, 0.0)
        self._normalize_peak_spin.setValue(-0.1)
        self._normalize_peak_spin.setSuffix(" dB")
        self._normalize_peak_btn = QPushButton(icons.icon("arrows-up-down"), "Normalize (Peak)")
        self._normalize_peak_btn.clicked.connect(self._do_normalize_peak)
        peak_row.addWidget(self._normalize_peak_spin)
        peak_row.addWidget(self._normalize_peak_btn)
        normalize_form.addRow("Target Peak:", peak_row)

        lufs_row = QHBoxLayout()
        self._normalize_lufs_spin = QDoubleSpinBox()
        self._normalize_lufs_spin.setRange(-40.0, 0.0)
        self._normalize_lufs_spin.setValue(-14.0)
        self._normalize_lufs_spin.setSuffix(" LUFS")
        self._normalize_lufs_btn = QPushButton(icons.icon("volume-high"), "Normalize Loudness")
        self._normalize_lufs_btn.clicked.connect(self._do_normalize_loudness)
        lufs_row.addWidget(self._normalize_lufs_spin)
        lufs_row.addWidget(self._normalize_lufs_btn)
        normalize_form.addRow("Target Loudness:", lufs_row)

        self._normalize_status_label = QLabel("-")
        self._normalize_status_label.setStyleSheet(f"color: {TEXT_DIM};")
        self._normalize_status_label.setWordWrap(True)
        normalize_form.addRow("Status:", self._normalize_status_label)
        layout.addWidget(normalize_group)

        trim_group = QGroupBox("Trim / Cut")
        trim_form = QFormLayout(trim_group)
        trim_form.setSpacing(8)

        self._trim_start_spin = QSpinBox()
        self._trim_start_spin.setRange(0, 0)
        self._trim_end_spin = QSpinBox()
        self._trim_end_spin.setRange(0, 0)
        self._trim_start_spin.valueChanged.connect(self._on_trim_spin_changed)
        self._trim_end_spin.valueChanged.connect(self._on_trim_spin_changed)
        trim_form.addRow("Selection Start (frame):", self._trim_start_spin)
        trim_form.addRow("Selection End (frame):", self._trim_end_spin)

        reset_selection_btn = QPushButton("Select Full Range")
        reset_selection_btn.clicked.connect(self._reset_trim_selection)
        trim_form.addRow("", reset_selection_btn)

        trim_btn_row = QHBoxLayout()
        self._trim_btn = QPushButton(icons.icon("crop-simple"), "Trim to Selection")
        self._trim_btn.setToolTip("Keep only audio inside the selection; discard the rest.")
        self._trim_btn.clicked.connect(self._do_trim)
        self._cut_btn = QPushButton(icons.icon("scissors"), "Cut Selection")
        self._cut_btn.setToolTip("Remove audio inside the selection; splice the remainder together.")
        self._cut_btn.clicked.connect(self._do_cut)
        trim_btn_row.addWidget(self._trim_btn)
        trim_btn_row.addWidget(self._cut_btn)
        trim_form.addRow("", trim_btn_row)

        layout.addWidget(trim_group)

        self._tools_undo_btn = QPushButton(icons.icon("rotate-left"), "Undo Last Operation")
        self._tools_undo_btn.clicked.connect(self._undo_last_operation)
        self._tools_undo_btn.setEnabled(False)
        self._undo_buttons.append(self._tools_undo_btn)
        layout.addWidget(self._tools_undo_btn)

        playback_group = QGroupBox("Audio Playback")
        playback_layout = QHBoxLayout(playback_group)
        tools_play_btn = QPushButton(icons.icon("play"), "Play")
        tools_stop_btn = QPushButton(icons.icon("stop"), "Stop")
        tools_play_btn.clicked.connect(self._play_sample)
        tools_stop_btn.clicked.connect(self._stop_sample)
        playback_layout.addWidget(tools_play_btn)
        playback_layout.addWidget(tools_stop_btn)
        layout.addWidget(playback_group)

        layout.addStretch()
        return widget

    EQ_BAND_TYPE_CHOICES = [
        ("Peak", "peak"),
        ("Low Shelf", "low_shelf"),
        ("High Shelf", "high_shelf"),
        ("Low Pass", "low_pass"),
        ("High Pass", "high_pass"),
    ]
    MAX_EQ_BANDS = 15

    def _build_eq_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)

        curve_group = QGroupBox("Frequency Response")
        curve_layout = QVBoxLayout(curve_group)
        self._eq_curve = EqCurveWidget()
        self._eq_curve.bandChanged.connect(self._on_eq_node_dragged)
        self._eq_curve.bandQChanged.connect(self._on_eq_node_q_changed)
        curve_layout.addWidget(self._eq_curve)
        curve_hint = QLabel("Drag a numbered point to set its Freq/Gain. Scroll over a point to change Q.")
        curve_hint.setStyleSheet(f"color: {TEXT_DIM};")
        curve_hint.setWordWrap(True)
        curve_layout.addWidget(curve_hint)
        layout.addWidget(curve_group)

        bands_group = QGroupBox("Parametric EQ")
        bands_group_layout = QVBoxLayout(bands_group)
        bands_group_layout.setSpacing(6)

        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)
        header_specs = [("#", 0, 18), ("Type", 2, None), ("Freq", 2, None),
                         ("Gain", 2, None), ("Q", 1, None), ("On", 0, 28), ("", 0, 32)]
        for text, stretch, fixed_w in header_specs:
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {TEXT_DIM}; font-weight: 600;")
            if fixed_w:
                lbl.setFixedWidth(fixed_w)
            header_layout.addWidget(lbl, stretch)
        bands_group_layout.addWidget(header_widget)

        self._eq_rows_container = QWidget()
        self._eq_rows_layout = QVBoxLayout(self._eq_rows_container)
        self._eq_rows_layout.setContentsMargins(0, 0, 0, 0)
        self._eq_rows_layout.setSpacing(4)
        bands_group_layout.addWidget(self._eq_rows_container)

        self._eq_rows = []
        for band in list(self._eq_bands):
            self._add_eq_band_row(band)
        self._renumber_eq_rows()

        add_row = QHBoxLayout()
        self._eq_add_btn = QPushButton(icons.icon("plus"), "Add Band")
        self._eq_add_btn.setToolTip(f"Add a new EQ band (max {self.MAX_EQ_BANDS}).")
        self._eq_add_btn.clicked.connect(lambda: self._add_eq_band())
        self._eq_count_label = QLabel()
        self._eq_count_label.setStyleSheet(f"color: {TEXT_DIM};")
        add_row.addWidget(self._eq_add_btn)
        add_row.addWidget(self._eq_count_label)
        add_row.addStretch()
        bands_group_layout.addLayout(add_row)
        self._update_eq_add_button_state()

        layout.addWidget(bands_group)

        reset_eq_btn = QPushButton(icons.icon("rotate-left"), "Reset Bands (Flat)")
        reset_eq_btn.setToolTip("Removes all extra bands and resets to a single flat Peak band.")
        reset_eq_btn.clicked.connect(self._reset_eq_bands)
        layout.addWidget(reset_eq_btn)

        apply_row = QHBoxLayout()
        self._apply_eq_btn = QPushButton(icons.icon("check"), "Apply EQ to Sample")
        self._apply_eq_btn.setToolTip("Permanently bakes the current EQ curve into the sample audio.")
        self._apply_eq_btn.clicked.connect(self._apply_eq_to_sample)
        self._eq_undo_btn = QPushButton(icons.icon("rotate-left"), "Undo Last Operation")
        self._eq_undo_btn.clicked.connect(self._undo_last_operation)
        self._eq_undo_btn.setEnabled(False)
        self._undo_buttons.append(self._eq_undo_btn)
        apply_row.addWidget(self._apply_eq_btn)
        apply_row.addWidget(self._eq_undo_btn)
        layout.addLayout(apply_row)

        playback_group = QGroupBox("Audio Playback (EQ Preview)")
        playback_layout = QHBoxLayout(playback_group)
        eq_play_btn = QPushButton(icons.icon("play"), "Play with EQ")
        eq_stop_btn = QPushButton(icons.icon("stop"), "Stop")
        eq_play_btn.clicked.connect(self._play_eq_preview)
        eq_stop_btn.clicked.connect(self._stop_sample)
        playback_layout.addWidget(eq_play_btn)
        playback_layout.addWidget(eq_stop_btn)
        layout.addWidget(playback_group)

        layout.addStretch()
        self._on_eq_band_changed()
        return widget

    def _add_eq_band_row(self, band: EQBand) -> dict:
        container = QWidget()
        row_layout = QHBoxLayout(container)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        number_label = QLabel("")
        number_label.setFixedWidth(18)
        number_label.setStyleSheet(f"color: {TEXT_DIM};")
        row_layout.addWidget(number_label, 0)

        type_combo = QComboBox()
        for label, value in self.EQ_BAND_TYPE_CHOICES:
            type_combo.addItem(label, value)
        type_combo.setCurrentIndex(max(0, type_combo.findData(band.type)))
        row_layout.addWidget(type_combo, 2)

        freq_spin = QDoubleSpinBox()
        freq_spin.setRange(20.0, 20000.0)
        freq_spin.setDecimals(0)
        freq_spin.setSuffix(" Hz")
        freq_spin.setValue(band.freq)
        row_layout.addWidget(freq_spin, 2)

        gain_spin = QDoubleSpinBox()
        gain_spin.setRange(-24.0, 24.0)
        gain_spin.setDecimals(1)
        gain_spin.setSuffix(" dB")
        gain_spin.setValue(band.gain_db)
        row_layout.addWidget(gain_spin, 2)

        q_spin = QDoubleSpinBox()
        q_spin.setRange(0.1, 10.0)
        q_spin.setDecimals(2)
        q_spin.setSingleStep(0.1)
        q_spin.setValue(band.q)
        row_layout.addWidget(q_spin, 1)

        enable_check = QCheckBox()
        enable_check.setChecked(band.enabled)
        enable_check.setToolTip("Enable/disable this band")
        row_layout.addWidget(enable_check, 0)

        remove_btn = QPushButton(icons.icon("trash"), "")
        remove_btn.setToolTip("Remove this band")
        remove_btn.setFixedWidth(32)
        row_layout.addWidget(remove_btn, 0)

        row = {
            "band": band,
            "container": container,
            "number_label": number_label,
            "type_combo": type_combo,
            "freq_spin": freq_spin,
            "gain_spin": gain_spin,
            "q_spin": q_spin,
            "enable_check": enable_check,
            "remove_btn": remove_btn,
        }

        type_combo.currentIndexChanged.connect(self._on_eq_band_changed)
        freq_spin.valueChanged.connect(self._on_eq_band_changed)
        gain_spin.valueChanged.connect(self._on_eq_band_changed)
        q_spin.valueChanged.connect(self._on_eq_band_changed)
        enable_check.stateChanged.connect(self._on_eq_band_changed)
        remove_btn.clicked.connect(lambda: self._remove_eq_band(row))

        self._eq_rows.append(row)
        self._eq_rows_layout.addWidget(container)
        return row

    def _renumber_eq_rows(self):
        for i, row in enumerate(self._eq_rows):
            row["number_label"].setText(str(i + 1))

    def _update_eq_add_button_state(self):
        count = len(self._eq_bands)
        self._eq_add_btn.setEnabled(count < self.MAX_EQ_BANDS)
        self._eq_count_label.setText(f"{count} / {self.MAX_EQ_BANDS} bands")

    def _add_eq_band(self, band: EQBand = None):
        if len(self._eq_bands) >= self.MAX_EQ_BANDS:
            return
        if band is None:
            band = EQBand(type="peak", freq=1000.0, gain_db=0.0, q=1.0)
        self._eq_bands.append(band)
        self._add_eq_band_row(band)
        self._renumber_eq_rows()
        self._update_eq_add_button_state()
        self._on_eq_band_changed()

    def _remove_eq_band(self, row: dict):
        if len(self._eq_bands) <= 1:
            return
        idx = self._eq_rows.index(row)
        self._eq_bands.pop(idx)
        self._eq_rows.pop(idx)
        self._eq_rows_layout.removeWidget(row["container"])
        row["container"].deleteLater()
        self._renumber_eq_rows()
        self._update_eq_add_button_state()
        self._on_eq_band_changed()

    def _sync_eq_bands_from_ui(self):
        for band, row in zip(self._eq_bands, self._eq_rows):
            band.type = row["type_combo"].currentData()
            band.freq = row["freq_spin"].value()
            band.gain_db = row["gain_spin"].value()
            band.q = row["q_spin"].value()
            band.enabled = row["enable_check"].isChecked()

    def _on_eq_band_changed(self, *args):
        self._sync_eq_bands_from_ui()
        rate = self._current_sample.sample_rate if self._current_sample else 44100
        self._eq_curve.set_bands(self._eq_bands, rate)

    def _on_eq_node_dragged(self, index: int):
        # The curve widget already mutated self._eq_bands[index] directly;
        # just mirror the new freq/gain into the spin boxes without
        # re-triggering _on_eq_band_changed (which would fight the drag).
        band = self._eq_bands[index]
        row = self._eq_rows[index]
        row["freq_spin"].blockSignals(True)
        row["freq_spin"].setValue(band.freq)
        row["freq_spin"].blockSignals(False)
        row["gain_spin"].blockSignals(True)
        row["gain_spin"].setValue(band.gain_db)
        row["gain_spin"].blockSignals(False)

    def _on_eq_node_q_changed(self, index: int):
        q_spin = self._eq_rows[index]["q_spin"]
        q_spin.blockSignals(True)
        q_spin.setValue(self._eq_bands[index].q)
        q_spin.blockSignals(False)

    def _reset_eq_bands(self):
        while len(self._eq_rows) > 1:
            self._remove_eq_band(self._eq_rows[-1])
        if not self._eq_rows:
            self._add_eq_band()
            return
        row = self._eq_rows[0]
        row["type_combo"].setCurrentIndex(row["type_combo"].findData("peak"))
        row["freq_spin"].setValue(1000.0)
        row["gain_spin"].setValue(0.0)
        row["q_spin"].setValue(1.0)
        row["enable_check"].setChecked(True)
        self._on_eq_band_changed()

    def _play_eq_preview(self):
        if self._current_sample is None or self._audio_player is None or self._current_sample.is_empty():
            return
        try:
            self._sync_eq_bands_from_ui()
            audio_bytes = self._current_sample.get_audio_channel_both()
            if not audio_bytes:
                return
            arr = audio_dsp.be16_to_float(audio_bytes)
            processed, = audio_dsp.apply_eq([arr], self._current_sample.sample_rate, self._eq_bands)
            pcm = audio_dsp.float_to_be16(processed)
            wav_bytes = audio_dsp.pcm_be16_to_wav_bytes(pcm, self._current_sample.sample_rate)
            if wav_bytes:
                self._audio_player.play(wav_bytes, self._current_sample.sample_rate)
        except Exception as exc:
            report_error("play_eq_preview", exc)
            print(f"EQ preview playback error: {exc}")

    def _apply_eq_to_sample(self):
        sample = self._current_sample
        if sample is None or sample.is_empty():
            QMessageBox.warning(self, "Apply EQ", "No sample selected")
            return
        self._sync_eq_bands_from_ui()
        if not audio_dsp.any_band_active(self._eq_bands):
            QMessageBox.information(self, "Apply EQ", "All EQ bands are flat/disabled - nothing to apply.")
            return
        self._push_undo_snapshot(sample)
        ch1, ch2 = self._get_sample_channels(sample)
        ch1, ch2 = audio_dsp.apply_eq([ch1, ch2], sample.sample_rate, self._eq_bands)
        self._commit_channels(sample, ch1, ch2)
        QMessageBox.information(self, "Apply EQ", "EQ applied to sample.")

    def _get_sample_channels(self, sample):
        ch1 = audio_dsp.be16_to_float(sample.audio_data_ch1)
        ch2 = audio_dsp.be16_to_float(sample.audio_data_ch2)
        return ch1, ch2

    def _push_undo_snapshot(self, sample):
        self._undo_snapshot = {
            "sample": sample,
            "audio_data_ch1": sample.audio_data_ch1,
            "audio_data_ch2": sample.audio_data_ch2,
            "num_frames": sample.num_frames,
            "start": sample.start,
            "end": sample.end,
            "loop_start": sample.loop_start,
        }
        for btn in self._undo_buttons:
            btn.setEnabled(True)

    def _clear_undo_snapshot(self):
        self._undo_snapshot = None
        for btn in self._undo_buttons:
            btn.setEnabled(False)

    def _undo_last_operation(self):
        snap = self._undo_snapshot
        if snap is None:
            return
        sample = snap["sample"]
        if sample is not self._current_sample:
            QMessageBox.warning(self, "Undo", "Selected sample has changed; cannot undo.")
            return
        sample.audio_data_ch1 = snap["audio_data_ch1"]
        sample.audio_data_ch2 = snap["audio_data_ch2"]
        sample.num_frames = snap["num_frames"]
        sample.start = snap["start"]
        sample.end = snap["end"]
        sample.loop_start = snap["loop_start"]
        self._clear_undo_snapshot()
        self._refresh_after_edit(sample)
        self._normalize_status_label.setText("Last operation undone.")

    def _commit_channels(self, sample, ch1_arr, ch2_arr):
        sample.audio_data_ch1 = audio_dsp.float_to_be16(ch1_arr)
        sample.audio_data_ch2 = audio_dsp.float_to_be16(ch2_arr)
        sample.num_frames = len(ch1_arr)
        sample.end = max(0, sample.num_frames - 1)
        if sample.start > sample.end:
            sample.start = 0
        if sample.loop_start > sample.end:
            sample.loop_start = sample.end
        self._refresh_after_edit(sample)

    def _refresh_after_edit(self, sample):
        self._populate_editor(sample)
        row = self._sample_table.currentRow()
        if 0 <= row < self._sample_table.rowCount():
            self._set_sample_row(row, sample)
        self._update_memory_usage()

    def _update_tools_waveform(self, sample=None):
        sample = sample or self._current_sample
        if sample is None:
            self._tools_waveform.clear()
            return
        self._tools_waveform.set_audio(
            sample.get_audio_channel_both(), sample.start, sample.end, sample.loop_start
        )

    def _on_waveform_selection_changed(self, start: int, end: int):
        self._trim_start_spin.blockSignals(True)
        self._trim_end_spin.blockSignals(True)
        self._trim_start_spin.setValue(start)
        self._trim_end_spin.setValue(end)
        self._trim_start_spin.blockSignals(False)
        self._trim_end_spin.blockSignals(False)

    def _on_trim_spin_changed(self, _value=None):
        self._tools_waveform.set_selection(self._trim_start_spin.value(), self._trim_end_spin.value())

    def _reset_trim_selection(self):
        sample = self._current_sample
        if sample is None:
            return
        self._trim_start_spin.setValue(0)
        self._trim_end_spin.setValue(max(0, sample.num_frames - 1))

    def _do_trim(self):
        sample = self._current_sample
        if sample is None or sample.is_empty():
            QMessageBox.warning(self, "Trim", "No sample selected")
            return
        start = self._trim_start_spin.value()
        end = self._trim_end_spin.value()
        if start > end:
            QMessageBox.warning(self, "Trim", "Selection start must be before end")
            return
        if start == 0 and end >= sample.num_frames - 1:
            QMessageBox.information(self, "Trim", "Selection already covers the full sample.")
            return
        self._push_undo_snapshot(sample)
        ch1, ch2 = self._get_sample_channels(sample)
        ch1 = audio_dsp.trim(ch1, start, end)
        ch2 = audio_dsp.trim(ch2, start, end)
        self._commit_channels(sample, ch1, ch2)
        self._reset_trim_selection()
        self._normalize_status_label.setText(f"Trimmed to {len(ch1)} frames.")

    def _do_cut(self):
        sample = self._current_sample
        if sample is None or sample.is_empty():
            QMessageBox.warning(self, "Cut", "No sample selected")
            return
        start = self._trim_start_spin.value()
        end = self._trim_end_spin.value()
        if start > end:
            QMessageBox.warning(self, "Cut", "Selection start must be before end")
            return
        if end - start + 1 >= sample.num_frames:
            QMessageBox.warning(self, "Cut", "Cannot cut the entire sample.")
            return
        reply = QMessageBox.question(
            self, "Cut Selection",
            f"Remove frames {start}-{end} and splice the remainder together?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._push_undo_snapshot(sample)
        ch1, ch2 = self._get_sample_channels(sample)
        ch1 = audio_dsp.cut_range(ch1, start, end)
        ch2 = audio_dsp.cut_range(ch2, start, end)
        self._commit_channels(sample, ch1, ch2)
        self._reset_trim_selection()
        self._normalize_status_label.setText(f"Cut {end - start + 1} frames; {len(ch1)} frames remain.")

    def _do_normalize_peak(self):
        sample = self._current_sample
        if sample is None or sample.is_empty():
            QMessageBox.warning(self, "Normalize", "No sample selected")
            return
        self._push_undo_snapshot(sample)
        ch1, ch2 = self._get_sample_channels(sample)
        target_db = self._normalize_peak_spin.value()
        channels, gain_db, had_signal = audio_dsp.normalize_peak([ch1, ch2], target_db)
        if not had_signal:
            self._clear_undo_snapshot()
            self._normalize_status_label.setText("Sample is silent; nothing to normalize.")
            return
        ch1, ch2 = channels
        self._commit_channels(sample, ch1, ch2)
        self._normalize_status_label.setText(
            f"Peak normalized to {target_db:.1f} dB (gain {gain_db:+.2f} dB)."
        )

    def _do_normalize_loudness(self):
        sample = self._current_sample
        if sample is None or sample.is_empty():
            QMessageBox.warning(self, "Normalize Loudness", "No sample selected")
            return
        self._push_undo_snapshot(sample)
        ch1, ch2 = self._get_sample_channels(sample)
        target_lufs = self._normalize_lufs_spin.value()
        channels, measured_before, gain_db, clipped = audio_dsp.normalize_loudness(
            [ch1, ch2], sample.sample_rate, target_lufs
        )
        if measured_before == float('-inf'):
            self._clear_undo_snapshot()
            self._normalize_status_label.setText("Sample is silent; nothing to normalize.")
            return
        ch1, ch2 = channels
        self._commit_channels(sample, ch1, ch2)
        clip_note = " (limited to avoid clipping)" if clipped else ""
        self._normalize_status_label.setText(
            f"Loudness normalized: {measured_before:.1f} -> {target_lufs:.1f} LUFS "
            f"(gain {gain_db:+.2f} dB){clip_note}."
        )

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

        self._apply_sample_filter()
        self._update_memory_usage()

    def _update_memory_usage(self):
        if self._esx is None:
            self._memory_bar.setValue(0)
            self._memory_label.setText("0.00 MB / 0.00 MB (0.00%)")
            return

        used_bytes = self._esx.get_sample_memory_used_bytes()
        max_bytes = MAX_SAMPLE_MEM_IN_BYTES
        used_mb = used_bytes / (1024 * 1024)
        max_mb = max_bytes / (1024 * 1024)
        pct = (used_bytes / max_bytes * 100) if max_bytes > 0 else 0

        self._memory_bar.setValue(min(1000, int(round(pct * 10))))
        over_limit = used_bytes > max_bytes
        bar_color = "#e5484d" if over_limit else ACCENT
        self._memory_bar.setStyleSheet(
            f"QProgressBar {{ background-color: {BG_FIELD}; border: 1px solid {BORDER}; "
            f"border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background-color: {bar_color}; border-radius: 3px; }}"
        )
        self._memory_label.setText(f"{used_mb:.2f} MB / {max_mb:.2f} MB ({pct:.2f}%)")

    def _apply_sample_filter(self):
        query = self._search_edit.text().strip().lower()
        for row in range(self._sample_table.rowCount()):
            if not query:
                self._sample_table.setRowHidden(row, False)
                continue
            name_item = self._sample_table.item(row, 1)
            index_item = self._sample_table.item(row, 0)
            name = name_item.text().lower() if name_item else ""
            index_text = index_item.text().lower() if index_item else ""
            match = query in name or query in index_text
            self._sample_table.setRowHidden(row, not match)

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
            has_undo = (
                self._undo_snapshot is not None
                and self._undo_snapshot["sample"] is self._current_sample
            )
            for btn in self._undo_buttons:
                btn.setEnabled(has_undo)

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
        self._trim_start_spin.setRange(0, max_frame)
        self._trim_end_spin.setRange(0, max_frame)
        self._trim_start_spin.setValue(min(max(sample.start, 0), max_frame))
        self._trim_end_spin.setValue(min(max(sample.end, 0), max_frame))
        self._normalize_status_label.setText("-")
        self._update_tools_waveform(sample)
        self._eq_curve.set_bands(self._eq_bands, sample.sample_rate)

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
                if self.import_with_plus12db:
                    new_sample.play_level = PlayLevel.DB_12
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
