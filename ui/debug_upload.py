import json
import os
import threading
import urllib.request

from PyQt6.QtCore import QThread, pyqtSignal

DEBUG_API_URL = "http://127.0.0.1:8765/debug-upload"
DEBUG_CRASH_API_URL = "http://127.0.0.1:8765/debug-crash"


class DebugUploadThread(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, filepath: str, api_url: str = DEBUG_API_URL):
        super().__init__()
        self.filepath = filepath
        self.api_url = api_url

    def run(self):
        try:
            with open(self.filepath, "rb") as f:
                data = f.read()

            request = urllib.request.Request(
                self.api_url,
                data=data,
                method="POST",
                headers={
                    "Content-Type": "application/octet-stream",
                    "X-Filename": os.path.basename(self.filepath),
                },
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                response.read()
            self.finished.emit(self.filepath)
        except Exception as e:
            self.error.emit(str(e))


def send_crash_report(payload: dict, api_url: str = DEBUG_CRASH_API_URL):
    """Fire-and-forget upload of a crash/error report (see esx.error_log) to
    the local debug API. Runs on a plain daemon thread rather than a QThread
    since it may be called from worker threads or the global exception hook,
    none of which have a Qt event loop to deliver a result signal on -
    failures are swallowed since there is nothing sensible to report them to."""

    def _send():
        try:
            data = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                api_url,
                data=data,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                response.read()
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True).start()
