import os

from PyQt6.QtCore import QStandardPaths


def _app_data_base() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".open-electribe-editor")
    return base


def get_patterns_dir() -> str:
    """Return the AppData folder where exported patterns (.esxpat) live,
    creating it if it doesn't exist yet. Relies on QApplication's
    organization/application name having been set (see main.py)."""
    patterns_dir = os.path.join(_app_data_base(), "Patterns")
    os.makedirs(patterns_dir, exist_ok=True)
    return patterns_dir


def get_log_file_path() -> str:
    """Return the path of the log file that crashes and other errors are
    appended to, creating its containing folder if needed."""
    log_dir = os.path.join(_app_data_base(), "Logs")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "error.log")
