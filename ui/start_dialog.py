from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog
)
from PyQt6.QtCore import Qt, QSize

from esx.app_paths import get_blank_template_path
from ui import icons


class StartDialog(QDialog):
    """Shown at application startup so the user can either start from the
    blank .esx template or open an existing file, before the main window
    with its tabs (which need a loaded file) appears."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Open Electribe Editor")
        self.setModal(True)
        self.setFixedWidth(420)
        self.selected_path: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("Open Electribe Editor")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)

        subtitle = QLabel("Start with a blank file or open an existing one.")
        subtitle.setStyleSheet("color: #9aa0a8;")
        layout.addWidget(subtitle)

        buttons = QVBoxLayout()
        buttons.setSpacing(8)

        new_button = QPushButton(icons.icon("file"), "  New Blank File")
        new_button.setIconSize(QSize(18, 18))
        new_button.setMinimumHeight(44)
        new_button.clicked.connect(self._start_blank)
        buttons.addWidget(new_button)

        open_button = QPushButton(icons.icon("folder-open"), "  Open File...")
        open_button.setIconSize(QSize(18, 18))
        open_button.setMinimumHeight(44)
        open_button.clicked.connect(self._start_open)
        buttons.addWidget(open_button)

        layout.addLayout(buttons)

    def _start_blank(self):
        self.selected_path = get_blank_template_path()
        self.accept()

    def _start_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open ESX File", "",
            "ESX Files (*.esx);;All Files (*)"
        )
        if path:
            self.selected_path = path
            self.accept()
