import os
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QSplitter, QTreeView,
    QTableView, QHeaderView, QAbstractItemView
)
from PyQt6.QtGui import QFileSystemModel
from PyQt6.QtCore import Qt, QDir, QModelIndex, pyqtSignal, QSortFilterProxyModel


class EsxFileFilterModel(QSortFilterProxyModel):
    def filterAcceptsRow(self, source_row, source_parent):
        index = self.sourceModel().index(source_row, 0, source_parent)
        file_path = self.sourceModel().filePath(index)
        if os.path.isdir(file_path):
            return True
        ext = os.path.splitext(file_path)[1].lower()
        return ext in ('.esx', '.wav', '.mp3', '.aiff', '.aif')


class FileExplorer(QWidget):
    file_open_requested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Directory tree
        self._tree_model = QFileSystemModel()
        self._tree_model.setRootPath(QDir.rootPath())
        self._tree_model.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot)

        self._tree_view = QTreeView()
        self._tree_view.setModel(self._tree_model)
        self._tree_view.setRootIndex(self._tree_model.index(QDir.rootPath()))
        self._tree_view.setHeaderHidden(True)
        for col in range(1, 4):
            self._tree_view.hideColumn(col)
        # Set initial directory to home
        home = QDir.homePath()
        home_idx = self._tree_model.index(home)
        self._tree_view.expand(home_idx)
        self._tree_view.setCurrentIndex(home_idx)

        splitter.addWidget(self._tree_view)

        # File list
        self._file_model = QFileSystemModel()
        self._file_model.setFilter(
            QDir.Filter.Files | QDir.Filter.NoDotAndDotDot
        )
        self._file_model.setNameFilters(['*.esx', '*.wav', '*.mp3', '*.aiff', '*.aif'])
        self._file_model.setNameFilterDisables(False)

        self._file_view = QTableView()
        self._file_view.setModel(self._file_model)
        self._file_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._file_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._file_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._file_view.verticalHeader().setVisible(False)
        self._file_view.setAlternatingRowColors(True)
        self._file_view.doubleClicked.connect(self._on_file_double_clicked)

        splitter.addWidget(self._file_view)
        splitter.setSizes([200, 200])

        layout.addWidget(splitter)

        # Set initial directory for files
        self._file_model.setRootPath(home)
        self._file_view.setRootIndex(self._file_model.index(home))

        # Connect tree selection after file model is ready
        self._tree_view.selectionModel().selectionChanged.connect(self._on_dir_selected)

    def _on_dir_selected(self):
        indexes = self._tree_view.selectedIndexes()
        if not indexes:
            return
        dir_path = self._tree_model.filePath(indexes[0])
        self._file_model.setRootPath(dir_path)
        self._file_view.setRootIndex(self._file_model.index(dir_path))

    def _on_file_double_clicked(self, index: QModelIndex):
        file_path = self._file_model.filePath(index)
        if not os.path.isfile(file_path):
            return
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.esx':
            self.file_open_requested.emit(file_path)
        elif ext in ('.wav', '.mp3', '.aiff', '.aif'):
            self._play_audio(file_path)

    def _play_audio(self, filepath: str):
        try:
            from audio.audio_player import AudioPlayer
            player = AudioPlayer()
            with open(filepath, 'rb') as f:
                wav_bytes = f.read()
            player.play(wav_bytes)
        except Exception as e:
            from ui.error_log import report_error
            report_error("play_audio", e)
            print(f"Cannot play audio: {e}")
