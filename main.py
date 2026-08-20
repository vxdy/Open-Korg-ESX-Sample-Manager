import sys
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog
from ui.main_window import MainWindow
from ui.start_dialog import StartDialog
from ui.theme import DARK_STYLESHEET
from ui.error_log import report_error, get_current_esx_path
from ui.i18n import tr, load_saved_language, set_language
from esx.app_paths import get_patterns_dir, get_debug_esx_path


def _install_excepthook():
    def handle_exception(exc_type, exc_value, exc_tb):
        traceback.print_exception(exc_type, exc_value, exc_tb)
        report_error("uncaught", exc_value, get_current_esx_path())
        QMessageBox.critical(
            None, tr("main.unexpected_error_title"),
            tr("main.unexpected_error_body", error=exc_value)
        )

    sys.excepthook = handle_exception


if __name__ == "__main__":
    # Private, undocumented entry point the app re-invokes itself with to
    # install the Stem Splitter's optional torch/demucs dependencies on
    # demand (see audio/stem_deps.py) - runs pip in-process and exits
    # without ever touching Qt, so it works the same whether this is a
    # frozen .exe or a source checkout.
    if len(sys.argv) > 1 and sys.argv[1] == "--pip-worker":
        from audio.stem_deps import run_pip_worker
        sys.exit(run_pip_worker(sys.argv[2:]))

    app = QApplication(sys.argv)
    app.setApplicationName("Open Electribe Editor")
    app.setOrganizationName("open-electribe-editor")
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLESHEET)

    # Chosen once at startup (persisted choice, or a guess from the OS
    # locale) - see ui/i18n.py's module docstring for why language changes
    # need a restart rather than applying live.
    set_language(load_saved_language())

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
