"""On-demand installer for the Stem Splitter's heavy optional dependencies
(torch, demucs). These must never be part of the frozen .exe bundle - see
main.spec's `excludes` - so instead of shipping them, the running app
re-invokes its own executable with a hidden "--pip-worker" argv, which makes
it run pip's own CLI in-process (see run_pip_worker()/main.py) instead of
starting the GUI. That worker installs into a per-user AppData folder
(esx.app_paths.get_stem_deps_dir()), which is then added to sys.path so the
packages import normally for the rest of the running process's lifetime -
no restart needed, and nothing touches the user's system Python.

This same self-re-invocation works identically whether the app is frozen
(PyInstaller) or running from source (`python main.py`), since it never
relies on `-m pip`/a real python.exe being available - only on this app's
own entry point (main.py, or the .exe standing in for it) understanding
"--pip-worker" as a private, undocumented flag."""

import os
import subprocess
import sys

from esx.app_paths import get_stem_deps_dir

PACKAGES = ["torch", "demucs"]

_path_added = False


def deps_dir() -> str:
    return get_stem_deps_dir()


def ensure_on_syspath():
    """Prepends deps_dir() to sys.path if it holds anything, so a previously
    completed install is picked up without re-running it. Safe to call any
    number of times."""
    global _path_added
    if _path_added:
        return
    d = deps_dir()
    if os.path.isdir(d) and d not in sys.path:
        sys.path.insert(0, d)
    _path_added = True


def is_installed() -> bool:
    from audio import stem_separator
    return stem_separator.is_available()


def _worker_command(pip_args: list) -> list:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--pip-worker", *pip_args]
    # Running from source: sys.executable is the real python.exe, which
    # needs an explicit script path to know what to run.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return [sys.executable, os.path.join(root, "main.py"), "--pip-worker", *pip_args]


def run_install(on_line=None):
    """Blocking - spawns the app itself as a pip worker to install torch and
    demucs into deps_dir(), streaming pip's own stdout line-by-line via
    on_line(text) as it happens. Meant to be called from a background
    thread, not the UI thread. Returns (success: bool, error_tail: str)."""
    os.makedirs(deps_dir(), exist_ok=True)
    cmd = _worker_command([
        "install",
        "--target", deps_dir(),
        "--only-binary=:all:",  # no source builds - a real compiler is never available here
        "--no-warn-script-location",
        "--disable-pip-version-check",
        *PACKAGES,
    ])

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, creationflags=creationflags,
        )
    except OSError as e:
        return False, str(e)

    lines = []
    for line in proc.stdout:
        line = line.rstrip("\n")
        lines.append(line)
        if on_line:
            on_line(line)
    proc.wait()

    if proc.returncode != 0:
        return False, "\n".join(lines[-20:])

    ensure_on_syspath()
    return True, ""


def run_pip_worker(argv: list) -> int:
    """Entry point for the "--pip-worker" invocation (see main.py) - runs
    pip's CLI in-process against argv and returns its exit code, without
    starting any part of the GUI."""
    try:
        from pip._internal.cli.main import main as pip_main
    except ImportError:
        print("pip is not available in this build.", file=sys.stderr)
        return 1
    return pip_main(argv)
