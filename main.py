import sys
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog
from ui.main_window import MainWindow
from ui.start_dialog import StartDialog
from ui.theme import DARK_STYLESHEET
from ui.error_log import report_error, get_current_esx_path
from esx.app_paths import get_patterns_dir, get_debug_esx_path


def _install_excepthook():
    def handle_exception(exc_type, exc_value, exc_tb):
        traceback.print_exception(exc_type, exc_value, exc_tb)
        report_error("uncaught", exc_value, get_current_esx_path())
        QMessageBox.critical(
            None, "Unexpected Error",
            f"An unexpected error occurred and has been logged:\n\n{exc_value}"
        )

    sys.excepthook = handle_exception


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Open Electribe Editor")
    app.setOrganizationName("open-electribe-editor")
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLESHEET)

    _install_excepthook()

    get_patterns_dir()  # ensure the AppData patterns folder exists

    debug_esx_path = get_debug_esx_path()
    if debug_esx_path is None:
        start_dialog = StartDialog()
        if start_dialog.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)
        selected_path = start_dialog.selected_path
    else:
        selected_path = debug_esx_path

    window = MainWindow()
    window.show()
    window._load_esx_file(selected_path)

    sys.exit(app.exec())
