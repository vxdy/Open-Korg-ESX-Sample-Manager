import os
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QDockWidget, QFileDialog,
    QMessageBox, QProgressDialog, QApplication, QLabel
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QSettings
from PyQt6.QtGui import QAction

from esx.esx_file import EsxFile
from esx.app_paths import get_blank_template_path, create_backup
from ui.tab_info import TabInfo
from ui.tab_global import TabGlobal
from ui.tab_patterns import TabPatterns
from ui.tab_samples import TabSamples
from ui.tab_songs import TabSongs
from ui.file_explorer import FileExplorer
from ui.pattern_browser import PatternBrowser
from ui.debug_upload import DebugUploadThread
from ui.error_log import report_error, set_current_esx_path
from ui.i18n import tr
from ui import icons


class LoadThread(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, filepath):
        super().__init__()
        self.filepath = filepath

    def run(self):
        try:
            esx = EsxFile.load(self.filepath)
        except Exception as e:
            report_error("load_esx", e, self.filepath)
            self.error.emit(str(e))
            return

        try:
            create_backup(self.filepath)
        except OSError as e:
            report_error("create_backup", e, self.filepath)

        self.finished.emit(esx)


class SaveThread(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, esx_file, filepath):
        super().__init__()
        self.esx_file = esx_file
        self.filepath = filepath

    def run(self):
        try:
            self.esx_file.save(self.filepath)
            self.finished.emit()
        except Exception as e:
            report_error("save_esx", e, self.filepath)
            self.error.emit(str(e))


def _make_busy_dialog(parent, text: str) -> QProgressDialog:
    """Indeterminate (min == max == 0) busy dialog, so long-running loads
    and saves show visible progress instead of looking like a freeze/crash."""
    progress = QProgressDialog(text, None, 0, 0, parent)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    progress.setCancelButton(None)
    progress.show()
    return progress


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.esx_file = None
        self.current_filepath = None
        self._setup_ui()
        self._setup_actions()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_dock()
        self._setup_statusbar()

    def _setup_ui(self):
        self.setWindowTitle("Open Electribe Editor")
        self.resize(1280, 820)

        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.setCentralWidget(self.tab_widget)

        self.tab_info = TabInfo()
        self.tab_global = TabGlobal()
        self.tab_patterns = TabPatterns()
        self.tab_samples = TabSamples()
        self.tab_songs = TabSongs()

        self.tab_widget.addTab(self.tab_info, tr("main_window.tab_info"))
        self.tab_widget.addTab(self.tab_global, tr("main_window.tab_global"))
        self.tab_widget.addTab(self.tab_patterns, tr("main_window.tab_patterns"))
        self.tab_widget.addTab(self.tab_samples, tr("main_window.tab_samples"))
        self.tab_widget.addTab(self.tab_songs, tr("main_window.tab_songs"))

    def _setup_actions(self):
        """Create actions once so the menu bar and the toolbar can share
        the same QAction instances (single source of truth for shortcuts,
        enabled state, etc.)."""
        self.new_action = QAction(icons.icon("file"), tr("main_window.action_new"), self)
        self.new_action.setShortcut("Ctrl+N")
        self.new_action.setToolTip(tr("main_window.action_new_tooltip"))
        self.new_action.triggered.connect(self.new_file)

        self.open_action = QAction(icons.icon("folder-open"), tr("main_window.action_open"), self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.setToolTip(tr("main_window.action_open_tooltip"))
        self.open_action.triggered.connect(self.open_file)

        self.save_action = QAction(icons.icon("floppy-disk"), tr("main_window.action_save"), self)
        self.save_action.setShortcut("Ctrl+S")
        self.save_action.setToolTip(tr("main_window.action_save_tooltip"))
        self.save_action.triggered.connect(self.save_file)

        self.save_as_action = QAction(icons.icon("floppy-disk"), tr("main_window.action_save_as"), self)
        self.save_as_action.setShortcut("Ctrl+Shift+S")
        self.save_as_action.triggered.connect(self.save_file_as)

        self.quit_action = QAction(icons.icon("right-from-bracket"), tr("main_window.action_quit"), self)
        self.quit_action.setShortcut("Ctrl+Q")
        self.quit_action.triggered.connect(self.close)

        self.import_samples_action = QAction(
            icons.icon("file-import"), tr("main_window.action_import_samples"), self
        )
        self.import_samples_action.setShortcut("Ctrl+I")
        self.import_samples_action.setToolTip(tr("main_window.action_import_samples_tooltip"))
        self.import_samples_action.triggered.connect(self._import_samples)

        self.import_as_mono_action = QAction(tr("main_window.action_import_as_mono"), self)
        self.import_as_mono_action.setCheckable(True)
        self.import_as_mono_action.setChecked(True)
        self.import_as_mono_action.toggled.connect(self._on_import_as_mono_toggled)

        self.import_with_plus12db_action = QAction(tr("main_window.action_import_plus12db"), self)
        self.import_with_plus12db_action.setCheckable(True)
        self.import_with_plus12db_action.setChecked(False)
        self.import_with_plus12db_action.toggled.connect(self._on_import_with_plus12db_toggled)

        self.delete_selected_samples_action = QAction(
            icons.icon("trash"), tr("main_window.action_delete_selected_samples"), self
        )
        self.delete_selected_samples_action.triggered.connect(self._delete_selected_samples)

        self.delete_unused_samples_action = QAction(
            icons.icon("trash"), tr("main_window.action_delete_unused_samples"), self
        )
        self.delete_unused_samples_action.triggered.connect(self._delete_unused_samples)

        self.stem_splitter_action = QAction(
            icons.icon("wand-magic-sparkles"), tr("main_window.action_stem_splitter"), self
        )
        self.stem_splitter_action.setToolTip(tr("main_window.action_stem_splitter_tooltip"))
        self.stem_splitter_action.triggered.connect(self._open_stem_splitter)

        self.about_action = QAction(icons.icon("circle-info"), tr("main_window.action_about"), self)
        self.about_action.triggered.connect(self._show_about)

        self.enable_stem_model_action = QAction(tr("main_window.action_enable_stem_model"), self)
        self.enable_stem_model_action.triggered.connect(self._enable_stem_model)

        self.send_debug_data_action = QAction(tr("main_window.action_send_debug_data"), self)
        self.send_debug_data_action.setCheckable(True)
        self.send_debug_data_action.setChecked(
            QSettings().value("send_debug_data", True, type=bool)
        )
        self.send_debug_data_action.toggled.connect(self._on_send_debug_data_toggled)

    def _setup_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu(tr("main_window.menu_file"))
        file_menu.addAction(self.new_action)
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        samples_menu = menubar.addMenu(tr("main_window.menu_samples"))
        samples_menu.addAction(self.import_samples_action)
        samples_menu.addAction(self.import_as_mono_action)
        samples_menu.addAction(self.import_with_plus12db_action)
        samples_menu.addSeparator()
        samples_menu.addAction(self.delete_selected_samples_action)
        samples_menu.addAction(self.delete_unused_samples_action)
        samples_menu.addSeparator()
        samples_menu.addAction(self.stem_splitter_action)

        help_menu = menubar.addMenu(tr("main_window.menu_help"))
        help_menu.addAction(self.about_action)
        help_menu.addSeparator()
        help_menu.addAction(self.enable_stem_model_action)
        help_menu.addAction(self.send_debug_data_action)

    def _setup_toolbar(self):
        toolbar = self.addToolBar(tr("main_window.toolbar_main"))
        toolbar.setObjectName("MainToolBar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_action)
        toolbar.addSeparator()
        toolbar.addAction(self.import_samples_action)
        toolbar.addAction(self.stem_splitter_action)

    def _setup_dock(self):
        self.file_explorer = FileExplorer()
        self.file_explorer.file_open_requested.connect(self._load_esx_file)

        file_explorer_dock = QDockWidget(tr("main_window.dock_file_explorer"), self)
        file_explorer_dock.setObjectName("FileExplorerDock")
        file_explorer_dock.setWidget(self.file_explorer)
        file_explorer_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, file_explorer_dock)

        self.pattern_browser = PatternBrowser()
        self.pattern_browser.pattern_file_activated.connect(self._import_pattern_file)

        pattern_browser_dock = QDockWidget(tr("main_window.dock_pattern_browser"), self)
        pattern_browser_dock.setObjectName("PatternBrowserDock")
        pattern_browser_dock.setWidget(self.pattern_browser)
        pattern_browser_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, pattern_browser_dock)

        # Tabify instead of stacking the two side panels, so the sidebar
        # takes up one compact slot with a tab strip to switch between them.
        self.tabifyDockWidget(file_explorer_dock, pattern_browser_dock)
        file_explorer_dock.raise_()

    def _setup_statusbar(self):
        status = self.statusBar()
        self._status_file_label = QLabel(tr("main_window.no_file_loaded"))
        status.addWidget(self._status_file_label)

    def new_file(self):
        self._load_esx_file(get_blank_template_path())

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("main_window.open_esx_file_title"), "",
            f"{tr('common.esx_files_filter')};;{tr('common.all_files_filter')}"
        )
        if path:
            self._load_esx_file(path)

    def _set_busy(self, busy: bool):
        """Disable actions that would start a conflicting operation while a
        load/save is in flight, and show a busy cursor as extra feedback."""
        for action in (
            self.new_action, self.open_action, self.save_action, self.save_as_action,
            self.import_samples_action, self.stem_splitter_action,
        ):
            action.setEnabled(not busy)
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

    def _load_esx_file(self, path: str):
        self._set_busy(True)
        progress = _make_busy_dialog(self, tr("main_window.loading_esx_file"))

        self._load_thread = LoadThread(path)
        self._load_thread.finished.connect(lambda esx: self._on_file_loaded(esx, path, progress))
        self._load_thread.error.connect(lambda e: self._on_load_error(e, progress))
        self._load_thread.start()

    def _on_file_loaded(self, esx: EsxFile, path: str, progress):
        self.esx_file = esx
        self.current_filepath = path
        set_current_esx_path(path)
        self.setWindowTitle(tr("main_window.window_title_with_file", filename=os.path.basename(path)))
        self._status_file_label.setText(path)
        self._update_tabs()

        progress.close()
        self._set_busy(False)

        if self.send_debug_data_action.isChecked():
            self._send_debug_data(path)

    def _on_load_error(self, error: str, progress):
        progress.close()
        self._set_busy(False)
        QMessageBox.critical(self, tr("common.error_title"), tr("main_window.failed_to_load", error=error))

    def _on_send_debug_data_toggled(self, checked: bool):
        QSettings().setValue("send_debug_data", checked)

    def _send_debug_data(self, path: str):
        self._debug_upload_thread = DebugUploadThread(path)
        self._debug_upload_thread.error.connect(self._on_debug_upload_error)
        self._debug_upload_thread.finished.connect(self._on_debug_upload_finished)
        self._debug_upload_thread.start()

    def _on_debug_upload_finished(self, path: str):
        self.statusBar().showMessage(tr("main_window.debug_data_sent"), 3000)

    def _on_debug_upload_error(self, error: str):
        report_error("debug_upload", Exception(error), self._debug_upload_thread.filepath)
        self.statusBar().showMessage(tr("main_window.debug_upload_failed", error=error), 5000)

    def _update_tabs(self):
        if self.esx_file is None:
            return
        self.tab_info.update_data(self.esx_file)
        self.tab_global.update_data(self.esx_file.global_parameters)
        self.tab_patterns.update_data(self.esx_file)
        self.tab_samples.update_data(self.esx_file)
        self.tab_songs.update_data(self.esx_file)

    def _import_pattern_file(self, path: str):
        if self.esx_file is None:
            QMessageBox.warning(self, tr("common.warning_title"), tr("main_window.no_file_loaded_body"))
            return
        self.tab_widget.setCurrentWidget(self.tab_patterns)
        self.tab_patterns.import_pattern_from_path(path)
        self.tab_samples.update_data(self.esx_file)
        self.tab_info.update_data(self.esx_file)

    def save_file(self):
        if self.esx_file is None:
            QMessageBox.warning(self, tr("common.warning_title"), tr("main_window.no_file_loaded_body"))
            return
        if self.current_filepath:
            self._do_save(self.current_filepath)
        else:
            self.save_file_as()

    def save_file_as(self):
        if self.esx_file is None:
            QMessageBox.warning(self, tr("common.warning_title"), tr("main_window.no_file_loaded_body"))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("main_window.save_esx_file_title"), "",
            f"{tr('common.esx_files_filter')};;{tr('common.all_files_filter')}"
        )
        if path:
            self._do_save(path, is_save_as=True)

    def _do_save(self, path: str, is_save_as: bool = False):
        try:
            # Collect any pending changes from tabs (must happen on the UI
            # thread since it reads widget state)
            self.tab_patterns.apply_changes()
            self.tab_global.apply_changes()
            self.tab_samples.apply_changes()
        except Exception as e:
            report_error("apply_changes", e, self.current_filepath)
            QMessageBox.critical(self, tr("common.error_title"), tr("main_window.failed_to_save", error=e))
            return

        self._set_busy(True)
        progress = _make_busy_dialog(self, tr("main_window.saving_esx_file"))

        self._save_thread = SaveThread(self.esx_file, path)
        self._save_thread.finished.connect(lambda: self._on_file_saved(path, is_save_as, progress))
        self._save_thread.error.connect(lambda e: self._on_save_error(e, progress))
        self._save_thread.start()

    def _on_file_saved(self, path: str, is_save_as: bool, progress):
        progress.close()
        self._set_busy(False)
        if is_save_as:
            self.current_filepath = path
            set_current_esx_path(path)
            self.setWindowTitle(tr("main_window.window_title_with_file", filename=os.path.basename(path)))
        self.statusBar().showMessage(tr("main_window.saved_to", path=path), 5000)
        QMessageBox.information(self, tr("main_window.saved_title"), tr("main_window.saved_body", path=path))

    def _on_save_error(self, error: str, progress):
        progress.close()
        self._set_busy(False)
        QMessageBox.critical(self, tr("common.error_title"), tr("main_window.failed_to_save", error=error))

    def _import_samples(self):
        if self.esx_file is None:
            QMessageBox.warning(self, tr("common.warning_title"), tr("main_window.no_file_loaded_body"))
            return
        self.tab_widget.setCurrentWidget(self.tab_samples)
        self.tab_samples.import_samples()

    def _on_import_as_mono_toggled(self, checked: bool):
        self.tab_samples.import_as_mono = checked

    def _on_import_with_plus12db_toggled(self, checked: bool):
        self.tab_samples.import_with_plus12db = checked

    def _delete_selected_samples(self):
        if self.esx_file is None:
            QMessageBox.warning(self, tr("common.warning_title"), tr("main_window.no_file_loaded_body"))
            return
        self.tab_widget.setCurrentWidget(self.tab_samples)
        self.tab_samples.delete_selected_samples()

    def _delete_unused_samples(self):
        if self.esx_file is None:
            QMessageBox.warning(self, tr("common.warning_title"), tr("main_window.no_file_loaded_body"))
            return
        self.tab_widget.setCurrentWidget(self.tab_samples)
        self.tab_samples.delete_unused_samples()

    def _open_stem_splitter(self):
        if self.esx_file is None:
            QMessageBox.warning(self, tr("common.warning_title"), tr("main_window.no_file_loaded_body"))
            return
        self.tab_widget.setCurrentWidget(self.tab_samples)
        self.tab_samples.open_stem_splitter()

    def _enable_stem_model(self):
        from ui.stem_splitter_dialog import run_consent_and_preload
        run_consent_and_preload(self)

    def _show_about(self):
        QMessageBox.information(
            self, tr("main_window.about_title"), tr("main_window.about_body")
        )
