from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QFormLayout, QLineEdit, QLabel,
    QHeaderView, QAbstractItemView, QGroupBox
)
from PyQt6.QtCore import Qt

from ui.i18n import tr


class TabSongs(QWidget):
    def __init__(self):
        super().__init__()
        self._esx = None
        self._current_song = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # Left: song list
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        title = QLabel(tr("tab_songs.songs_count"))
        title.setStyleSheet("font-weight: 600; color: #9aa0a8;")
        left_layout.addWidget(title)
        self._song_table = QTableWidget()
        self._song_table.setColumnCount(3)
        self._song_table.setHorizontalHeaderLabels([tr("common.hash"), tr("common.name"), tr("tab_songs.events")])
        self._song_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._song_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._song_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._song_table.verticalHeader().setVisible(False)
        self._song_table.setAlternatingRowColors(True)
        self._song_table.selectionModel().selectionChanged.connect(self._on_song_selected)
        left_layout.addWidget(self._song_table)
        splitter.addWidget(left_widget)

        # Right: song details tabs
        right_tabs = QTabWidget()

        # Song editor tab
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)

        info_group = QGroupBox(tr("tab_songs.song_properties"))
        form = QFormLayout(info_group)
        form.setSpacing(10)
        form.setContentsMargins(10, 14, 10, 10)
        self._name_edit = QLineEdit()
        self._name_edit.setMaxLength(8)
        form.addRow(tr("common.name_colon"), self._name_edit)
        self._tempo_label = QLabel("—")
        form.addRow(tr("common.tempo_colon"), self._tempo_label)
        self._song_length_label = QLabel("—")
        form.addRow(tr("tab_songs.song_length"), self._song_length_label)
        self._num_events_label = QLabel("—")
        form.addRow(tr("tab_songs.events_original"), self._num_events_label)
        self._next_song_label = QLabel("—")
        form.addRow(tr("tab_songs.next_song"), self._next_song_label)
        editor_layout.addWidget(info_group)
        editor_layout.addStretch()
        right_tabs.addTab(editor_widget, tr("tab_songs.song_editor"))

        # Song events tab
        events_widget = QWidget()
        events_layout = QVBoxLayout(events_widget)
        events_layout.addWidget(QLabel(tr("tab_songs.song_events_colon")))
        self._events_table = QTableWidget()
        self._events_table.setColumnCount(2)
        self._events_table.setHorizontalHeaderLabels([tr("common.hash"), tr("tab_songs.raw_data")])
        self._events_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._events_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._events_table.verticalHeader().setVisible(False)
        self._events_table.setAlternatingRowColors(True)
        events_layout.addWidget(self._events_table)
        right_tabs.addTab(events_widget, tr("tab_songs.song_events"))

        # Song patterns tab
        patterns_widget = QWidget()
        patterns_layout = QVBoxLayout(patterns_widget)
        patterns_layout.addWidget(QLabel(tr("tab_songs.song_pattern_offsets_colon")))
        self._patterns_table = QTableWidget()
        self._patterns_table.setColumnCount(2)
        self._patterns_table.setHorizontalHeaderLabels([tr("tab_global.index"), tr("tab_songs.note_offset")])
        self._patterns_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._patterns_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._patterns_table.verticalHeader().setVisible(False)
        self._patterns_table.setAlternatingRowColors(True)
        patterns_layout.addWidget(self._patterns_table)
        right_tabs.addTab(patterns_widget, tr("tab_songs.song_patterns"))

        splitter.addWidget(right_tabs)
        splitter.setSizes([250, 750])

    def update_data(self, esx_file):
        self._esx = esx_file
        songs = esx_file.songs

        self._song_table.setRowCount(len(songs))
        for i, s in enumerate(songs):
            self._song_table.setItem(i, 0, QTableWidgetItem(str(i)))
            name = s.name.strip('\x00').strip()
            self._song_table.setItem(i, 1, QTableWidgetItem(name if name else tr("common.empty_placeholder")))
            self._song_table.setItem(i, 2, QTableWidgetItem(str(len(s.song_events))))

    def _on_song_selected(self):
        if self._esx is None:
            return
        row = self._song_table.currentRow()
        if 0 <= row < len(self._esx.songs):
            self._current_song = self._esx.songs[row]
            self._populate_editor(self._current_song)

    def _populate_editor(self, song):
        self._name_edit.setText(song.name.strip('\x00'))
        self._tempo_label.setText(str(song.tempo.value))
        self._song_length_label.setText(str(song.song_length))
        self._num_events_label.setText(str(song.num_song_events_original))
        self._next_song_label.setText(str(song.next_song_number))

        # Song events
        self._events_table.setRowCount(len(song.song_events))
        for i, e in enumerate(song.song_events):
            self._events_table.setItem(i, 0, QTableWidgetItem(str(i)))
            self._events_table.setItem(i, 1, QTableWidgetItem(e.raw_data.hex()))

        # Song patterns (show first few non-zero)
        patterns = [sp for sp in song.song_patterns if sp.note_offset != 0]
        self._patterns_table.setRowCount(len(patterns))
        for i, sp in enumerate(patterns):
            idx = song.song_patterns.index(sp)
            self._patterns_table.setItem(i, 0, QTableWidgetItem(str(idx)))
            self._patterns_table.setItem(i, 1, QTableWidgetItem(str(sp.note_offset)))
