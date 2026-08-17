import os
import shutil

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QLabel, QMenu, QMessageBox, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QFileSystemWatcher, QByteArray, QMimeData

from esx.app_paths import get_patterns_dir
from esx.pattern_transfer import read_pattern_summary
from ui.i18n import tr
from ui import icons

PATTERN_FILE_MIME_TYPE = "application/x-esx-pattern-file"


class SavedPatternTable(QTableWidget):
    """Table of saved .esxpat files. Dragging a row out exposes the file's
    absolute path as custom MIME data, so it can be dropped onto a row in
    the Patterns tab to import/replace that pattern."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

    def mimeData(self, items):
        mime = QMimeData()
        rows = sorted({item.row() for item in items})
        if rows:
            path_item = self.item(rows[0], 0)
            filepath = path_item.data(Qt.ItemDataRole.UserRole) if path_item else None
            if filepath:
                mime.setData(PATTERN_FILE_MIME_TYPE, QByteArray(filepath.encode("utf-8")))
                mime.setText(filepath)
        return mime


class PatternBrowser(QWidget):
    """Lists saved/exported pattern (.esxpat) files from the app's patterns
    folder in AppData, showing each pattern's name and BPM, so patterns can
    be dropped into any ESX file. Reordering pattern slots within the
    currently open file happens in the normal Patterns tab instead."""

    pattern_file_activated = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._patterns_dir = get_patterns_dir()
        self._files = []  # filepaths, parallel to the file table's rows
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        hint = QLabel(tr("pattern_browser.hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(hint)

        self._file_table = SavedPatternTable()
        self._file_table.setColumnCount(3)
        self._file_table.setHorizontalHeaderLabels(
            [tr("pattern_browser.pattern"), tr("pattern_browser.bpm"), tr("pattern_browser.file")]
        )
        self._file_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._file_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._file_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._file_table.verticalHeader().setVisible(False)
        self._file_table.setAlternatingRowColors(True)
        self._file_table.doubleClicked.connect(self._on_file_double_clicked)
        self._file_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._file_table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._file_table)

        self._watcher = QFileSystemWatcher()
        if os.path.isdir(self._patterns_dir):
            self._watcher.addPath(self._patterns_dir)
        self._watcher.directoryChanged.connect(self._reload)

        self._reload()

    def _reload(self, *_args):
        self._files = []
        self._file_table.setRowCount(0)
        if not os.path.isdir(self._patterns_dir):
            return

        try:
            filenames = sorted(
                f for f in os.listdir(self._patterns_dir) if f.lower().endswith('.esxpat')
            )
        except OSError:
            return

        self._file_table.setRowCount(len(filenames))
        for row, filename in enumerate(filenames):
            filepath = os.path.join(self._patterns_dir, filename)
            self._files.append(filepath)

            summary = read_pattern_summary(filepath)
            if summary is not None:
                name = summary["name"].strip() or tr("pattern_browser.unnamed")
                tempo = summary["tempo"]
                bpm_text = f"{tempo:.1f}" if isinstance(tempo, (int, float)) else "?"
            else:
                name = tr("pattern_browser.invalid_pattern_file")
                bpm_text = "?"

            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, filepath)
            self._file_table.setItem(row, 0, name_item)
            self._file_table.setItem(row, 1, QTableWidgetItem(bpm_text))
            self._file_table.setItem(row, 2, QTableWidgetItem(filename))

    def _on_file_double_clicked(self, index):
        row = index.row()
        if 0 <= row < len(self._files):
            self.pattern_file_activated.emit(self._files[row])

    def _show_context_menu(self, pos):
        row = self._file_table.rowAt(pos.y())
        if not (0 <= row < len(self._files)):
            return
        self._file_table.selectRow(row)
        filepath = self._files[row]

        menu = QMenu(self)
        import_action = menu.addAction(icons.icon("file-import"), tr("pattern_browser.import_into_selected"))
        export_action = menu.addAction(icons.icon("file-export"), tr("pattern_browser.export_as"))
        menu.addSeparator()
        delete_action = menu.addAction(icons.icon("trash"), tr("common.delete"))

        action = menu.exec(self._file_table.viewport().mapToGlobal(pos))
        if action == import_action:
            self.pattern_file_activated.emit(filepath)
        elif action == export_action:
            self._export_as(filepath)
        elif action == delete_action:
            self._delete_pattern_file(filepath)

    def _export_as(self, filepath: str):
        default_path = os.path.join(os.path.expanduser("~"), os.path.basename(filepath))
        path, _ = QFileDialog.getSaveFileName(
            self, tr("pattern_browser.export_pattern_as_title"), default_path,
            tr("common.esxpat_files_filter") + ";;" + tr("common.all_files_filter")
        )
        if not path:
            return
        try:
            shutil.copyfile(filepath, path)
        except OSError as exc:
            QMessageBox.critical(self, tr("tab_samples.export_error_title"), str(exc))

    def _delete_pattern_file(self, filepath: str):
        name = os.path.basename(filepath)
        reply = QMessageBox.question(
            self, tr("pattern_browser.delete_pattern_title"),
            tr("pattern_browser.delete_pattern_confirm", name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            os.remove(filepath)
        except OSError as exc:
            QMessageBox.critical(self, tr("pattern_browser.delete_error_title"), str(exc))
            return
        self._reload()
