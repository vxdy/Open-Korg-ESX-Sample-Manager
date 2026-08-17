from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QGroupBox,
    QFormLayout, QComboBox, QTableWidget, QTableWidgetItem,
    QTabWidget, QLabel, QSpinBox, QCheckBox, QHeaderView, QAbstractItemView
)
from PyQt6.QtCore import Qt

from esx.constants import (
    EnabledFlag, ArpeggiatorControl, AudioInMode, MidiClock, PitchBendRange
)
from ui.i18n import tr, AVAILABLE_LANGUAGES, current_language, save_language
from ui.theme import TEXT_DIM


class TabGlobal(QWidget):
    def __init__(self):
        super().__init__()
        self._gp = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # Left: app settings + main parameters form
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        app_group = QGroupBox(tr("tab_global.app_settings"))
        app_form = QFormLayout(app_group)
        app_form.setSpacing(10)
        app_form.setContentsMargins(10, 14, 10, 10)

        self._language_combo = QComboBox()
        self._language_codes = list(AVAILABLE_LANGUAGES.keys())
        self._language_combo.addItems([AVAILABLE_LANGUAGES[code] for code in self._language_codes])
        self._language_combo.setCurrentIndex(max(0, self._language_codes.index(current_language())))
        self._language_combo.currentIndexChanged.connect(self._on_language_changed)
        app_form.addRow(tr("tab_global.language"), self._language_combo)

        self._language_hint = QLabel(tr("tab_global.language_restart_hint"))
        self._language_hint.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        self._language_hint.setWordWrap(True)
        self._language_hint.setVisible(False)
        app_form.addRow("", self._language_hint)

        left_layout.addWidget(app_group)

        form_group = QGroupBox(tr("tab_global.main_parameters"))
        form = QFormLayout(form_group)
        form.setSpacing(10)
        form.setContentsMargins(10, 14, 10, 10)

        self._memory_protect = QComboBox()
        self._memory_protect.addItems([e.name for e in EnabledFlag])
        form.addRow(tr("tab_global.memory_protect"), self._memory_protect)

        self._arp_control = QComboBox()
        self._arp_control.addItems([e.name for e in ArpeggiatorControl])
        form.addRow(tr("tab_global.arpeggiator_control"), self._arp_control)

        self._audio_in_mode = QComboBox()
        self._audio_in_mode.addItems([e.name for e in AudioInMode])
        form.addRow(tr("tab_global.audio_in_mode"), self._audio_in_mode)

        self._midi_clock = QComboBox()
        self._midi_clock.addItems([e.name for e in MidiClock])
        form.addRow(tr("tab_global.midi_clock"), self._midi_clock)

        self._note_msg = QComboBox()
        self._note_msg.addItems([e.name for e in EnabledFlag])
        form.addRow(tr("tab_global.note_message"), self._note_msg)

        self._sys_ex = QComboBox()
        self._sys_ex.addItems([e.name for e in EnabledFlag])
        form.addRow(tr("tab_global.sysex"), self._sys_ex)

        self._cc_enabled = QComboBox()
        self._cc_enabled.addItems([e.name for e in EnabledFlag])
        form.addRow(tr("tab_global.control_change"), self._cc_enabled)

        self._pc_enabled = QComboBox()
        self._pc_enabled.addItems([e.name for e in EnabledFlag])
        form.addRow(tr("tab_global.program_change"), self._pc_enabled)

        self._pitch_bend = QComboBox()
        self._pitch_bend.addItems([e.name for e in PitchBendRange])
        form.addRow(tr("tab_global.pitch_bend_range"), self._pitch_bend)

        left_layout.addWidget(form_group)
        left_layout.addStretch()
        splitter.addWidget(left_widget)

        # Right: sub-tabs
        right_tabs = QTabWidget()

        # MIDI CC Assignments tab
        self._cc_table = QTableWidget()
        self._cc_table.setColumnCount(2)
        self._cc_table.setHorizontalHeaderLabels([tr("common.name"), tr("common.value")])
        self._cc_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._cc_table.verticalHeader().setVisible(False)
        self._cc_table.setAlternatingRowColors(True)
        self._cc_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        right_tabs.addTab(self._cc_table, tr("tab_global.midi_cc_assignments"))

        # Part Note Numbers tab
        self._pnn_table = QTableWidget()
        self._pnn_table.setColumnCount(2)
        self._pnn_table.setHorizontalHeaderLabels([tr("tab_global.part"), tr("tab_global.note_number")])
        self._pnn_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._pnn_table.verticalHeader().setVisible(False)
        self._pnn_table.setAlternatingRowColors(True)
        self._pnn_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        right_tabs.addTab(self._pnn_table, tr("tab_global.part_note_numbers"))

        # Pattern Set Parameters tab
        self._psp_table = QTableWidget()
        self._psp_table.setColumnCount(2)
        self._psp_table.setHorizontalHeaderLabels([tr("tab_global.index"), tr("tab_global.pattern_pointer")])
        self._psp_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._psp_table.verticalHeader().setVisible(False)
        self._psp_table.setAlternatingRowColors(True)
        self._psp_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        right_tabs.addTab(self._psp_table, tr("tab_global.pattern_set_parameters"))

        splitter.addWidget(right_tabs)
        splitter.setSizes([300, 600])

    def _on_language_changed(self, index):
        code = self._language_codes[index]
        save_language(code)
        self._language_hint.setVisible(code != current_language())

    def update_data(self, gp):
        self._gp = gp
        if gp is None:
            return

        self._memory_protect.setCurrentIndex(int(gp.memory_protect_enabled))
        self._arp_control.setCurrentIndex(int(gp.arpeggiator_control))
        self._audio_in_mode.setCurrentIndex(int(gp.audio_in_mode))
        self._midi_clock.setCurrentIndex(int(gp.midi_clock))
        self._note_msg.setCurrentIndex(int(gp.note_message_enabled))
        self._sys_ex.setCurrentIndex(int(gp.system_ex_enabled))
        self._cc_enabled.setCurrentIndex(int(gp.control_change_enabled))
        self._pc_enabled.setCurrentIndex(int(gp.program_change_enabled))
        self._pitch_bend.setCurrentIndex(int(gp.pitch_bend_range))

        # MIDI CC Assignments
        self._cc_table.setRowCount(len(gp.midi_cc_assignments))
        for i, cc in enumerate(gp.midi_cc_assignments):
            self._cc_table.setItem(i, 0, QTableWidgetItem(cc.name))
            self._cc_table.setItem(i, 1, QTableWidgetItem(str(cc.value)))

        # Part Note Numbers
        self._pnn_table.setRowCount(len(gp.part_note_numbers))
        for i, pnn in enumerate(gp.part_note_numbers):
            self._pnn_table.setItem(i, 0, QTableWidgetItem(pnn.name))
            self._pnn_table.setItem(i, 1, QTableWidgetItem(str(pnn.note_number)))

        # Pattern Set Parameters
        self._psp_table.setRowCount(len(gp.pattern_set_parameters))
        for i, psp in enumerate(gp.pattern_set_parameters):
            self._psp_table.setItem(i, 0, QTableWidgetItem(str(i)))
            self._psp_table.setItem(i, 1, QTableWidgetItem(str(psp.pattern_pointer)))

    def apply_changes(self):
        if self._gp is None:
            return
        self._gp.memory_protect_enabled = EnabledFlag(self._memory_protect.currentIndex())
        self._gp.arpeggiator_control = ArpeggiatorControl(self._arp_control.currentIndex())
        self._gp.audio_in_mode = AudioInMode(self._audio_in_mode.currentIndex())
        self._gp.midi_clock = MidiClock(self._midi_clock.currentIndex())
        self._gp.note_message_enabled = EnabledFlag(self._note_msg.currentIndex())
        self._gp.system_ex_enabled = EnabledFlag(self._sys_ex.currentIndex())
        self._gp.control_change_enabled = EnabledFlag(self._cc_enabled.currentIndex())
        self._gp.program_change_enabled = EnabledFlag(self._pc_enabled.currentIndex())
        self._gp.pitch_bend_range = PitchBendRange(self._pitch_bend.currentIndex())
