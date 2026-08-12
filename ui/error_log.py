import traceback
from datetime import datetime

from PyQt6.QtCore import QSettings

from esx.app_paths import get_log_file_path
from ui.debug_upload import send_crash_report

_current_esx_path = None


def set_current_esx_path(path: str | None):
    """Track the ESX file currently open in the main window, so crashes and
    errors raised without direct access to it (e.g. the global exception
    hook) can still be logged against it."""
    global _current_esx_path
    _current_esx_path = path


def get_current_esx_path() -> str | None:
    return _current_esx_path


def report_error(context: str, exc: BaseException, esx_path: str | None = None):
    """Append a timestamped entry (context, the active ESX file, and the
    traceback) to the local error log, and - if the user has opted into
    sending debug data - forward the same report to the local debug API so
    crashes and other failures can be diagnosed against the file that
    triggered them."""
    esx_path = esx_path if esx_path is not None else _current_esx_path
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    entry = (
        f"[{timestamp}] [ESX: {esx_path or '-'}] [{context}]\n"
        f"{tb_text}"
        f"{'-' * 60}\n"
    )
    try:
        with open(get_log_file_path(), "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError:
        pass

    if QSettings().value("send_debug_data", True, type=bool):
        send_crash_report({
            "timestamp": timestamp,
            "esx_file": esx_path,
            "context": context,
            "error_type": type(exc).__name__,
            "message": str(exc),
            "traceback": tb_text,
        })
