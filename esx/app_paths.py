import os
import shutil
import sys
from datetime import datetime

from PyQt6.QtCore import QStandardPaths


def get_blank_template_path() -> str:
    """Return the path to the bundled blank .esx template used to start a
    new file. Resolves relative to the frozen exe when packaged (PyInstaller
    _MEIPASS), otherwise relative to the project root."""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "template", "Blank.esx")


def get_debug_esx_path() -> str | None:
    """Return the path of the first .esx file found in the project's
    "debug" folder, if any. Used to auto-load a file at startup during
    development, bypassing the start dialog. Returns None if the folder
    doesn't exist or contains no .esx file."""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    debug_dir = os.path.join(base, "debug")
    if not os.path.isdir(debug_dir):
        return None
    for name in sorted(os.listdir(debug_dir)):
        if name.lower().endswith(".esx"):
            return os.path.join(debug_dir, name)
    return None


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


def get_backups_dir() -> str:
    """Return the AppData folder where versioned backups of loaded .esx
    files are stored, creating it if it doesn't exist yet. Sits alongside
    get_patterns_dir()'s "Patterns" folder in the same AppData location."""
    backups_dir = os.path.join(_app_data_base(), "Backups")
    os.makedirs(backups_dir, exist_ok=True)
    return backups_dir


def create_backup(filepath: str) -> str:
    """Copy filepath into the Backups folder under a timestamped name, so
    repeated loads of the same (or differently-named) file build up a
    versioned history instead of overwriting each other. Returns the
    backup's path."""
    basename = os.path.splitext(os.path.basename(filepath))[0]
    ext = os.path.splitext(filepath)[1] or ".esx"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    backup_path = os.path.join(get_backups_dir(), f"{basename}_{timestamp}{ext}")
    counter = 1
    while os.path.exists(backup_path):
        backup_path = os.path.join(get_backups_dir(), f"{basename}_{timestamp}_{counter}{ext}")
        counter += 1

    shutil.copy2(filepath, backup_path)
    return backup_path


def get_log_file_path() -> str:
    """Return the path of the log file that crashes and other errors are
    appended to, creating its containing folder if needed."""
    log_dir = os.path.join(_app_data_base(), "Logs")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "error.log")


def get_stem_deps_dir() -> str:
    """Return the AppData folder the Stem Splitter installs its optional
    torch/demucs dependencies into on demand, creating it if needed. These
    packages are never part of the frozen .exe bundle (see main.spec's
    excludes and audio/stem_deps.py) - they're pip-installed here the first
    time the feature is actually used."""
    deps_dir = os.path.join(_app_data_base(), "StemDeps")
    os.makedirs(deps_dir, exist_ok=True)
    return deps_dir
