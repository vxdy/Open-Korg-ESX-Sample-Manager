
ACCENT = "#4fb6ff"
ACCENT_HOVER = "#6cc4ff"
ACCENT_PRESSED = "#2e94dd"

BG_WINDOW = "#1e1f22"
BG_PANEL = "#26282c"
BG_FIELD = "#2b2d31"
BG_FIELD_HOVER = "#313338"
BORDER = "#3a3d42"
BORDER_LIGHT = "#4a4d54"
TEXT = "#e6e6e8"
TEXT_DIM = "#9aa0a8"
TEXT_DISABLED = "#65686e"
SELECTION = "#3a5d80"

DARK_STYLESHEET = f"""
* {{
    outline: none;
}}

QWidget {{
    background-color: {BG_WINDOW};
    color: {TEXT};
    font-size: 13px;
    selection-background-color: {ACCENT};
    selection-color: #0b0c0d;
}}

QMainWindow {{
    background-color: {BG_WINDOW};
}}

QMainWindow::separator {{
    background: {BORDER};
    width: 2px;
    height: 2px;
}}

/* --- Menu bar & menus --- */
QMenuBar {{
    background-color: {BG_PANEL};
    border-bottom: 1px solid {BORDER};
    padding: 2px 4px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 5px 10px;
    border-radius: 4px;
}}
QMenuBar::item:selected {{
    background: {BG_FIELD_HOVER};
}}
QMenu {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {ACCENT};
    color: #0b0c0d;
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 4px 6px;
}}

/* --- Toolbar --- */
QToolBar {{
    background-color: {BG_PANEL};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 4px;
    spacing: 4px;
}}
QToolBar::separator {{
    background: {BORDER};
    width: 1px;
    margin: 4px 6px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 5px 8px;
    color: {TEXT};
}}
QToolButton:hover {{
    background-color: {BG_FIELD_HOVER};
    border-color: {BORDER_LIGHT};
}}
QToolButton:pressed {{
    background-color: {SELECTION};
}}

QStatusBar {{
    background-color: {BG_PANEL};
    border-top: 1px solid {BORDER};
    color: {TEXT_DIM};
}}

/* --- Tabs --- */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    top: -1px;
    background-color: {BG_PANEL};
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_DIM};
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}
QTabBar::tab:hover {{
    color: {TEXT};
    background: {BG_FIELD_HOVER};
}}
QTabBar::tab:selected {{
    color: {TEXT};
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    border-bottom: none;
}}

/* --- Group boxes --- */
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 14px;
    padding: 12px 8px 8px 8px;
    font-weight: 600;
    background-color: {BG_PANEL};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 6px;
    color: {ACCENT};
}}

/* --- Buttons --- */
QPushButton {{
    background-color: {BG_FIELD};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 5px;
    padding: 6px 14px;
    color: {TEXT};
}}
QPushButton:hover {{
    background-color: {BG_FIELD_HOVER};
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background-color: {SELECTION};
}}
QPushButton:disabled {{
    color: {TEXT_DISABLED};
    border-color: {BORDER};
}}
QPushButton:default {{
    border-color: {ACCENT};
}}

/* --- Inputs --- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {BG_FIELD};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 4px;
    padding: 4px 6px;
    color: {TEXT};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {TEXT_DISABLED};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_FIELD};
    border: 1px solid {BORDER_LIGHT};
    selection-background-color: {ACCENT};
    selection-color: #0b0c0d;
    outline: none;
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 14px;
    background: {BG_FIELD_HOVER};
    border-left: 1px solid {BORDER};
}}

QCheckBox {{
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {BORDER_LIGHT};
    border-radius: 3px;
    background-color: {BG_FIELD};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

QLabel {{
    background: transparent;
}}

/* --- Tables & trees --- */
QTableView, QTableWidget, QTreeView, QListView {{
    background-color: {BG_FIELD};
    alternate-background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 4px;
    gridline-color: {BORDER};
}}
QTableView::item, QTableWidget::item, QTreeView::item {{
    padding: 3px 4px;
}}
QTableView::item:selected, QTableWidget::item:selected, QTreeView::item:selected {{
    background-color: {SELECTION};
    color: {TEXT};
}}
QHeaderView::section {{
    background-color: {BG_PANEL};
    color: {TEXT_DIM};
    padding: 6px;
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    font-weight: 600;
}}
QTableCornerButton::section {{
    background-color: {BG_PANEL};
    border: none;
    border-bottom: 1px solid {BORDER};
}}

/* --- Docks --- */
QDockWidget {{
    color: {TEXT};
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}
QDockWidget::title {{
    background-color: {BG_PANEL};
    padding: 7px 8px;
    border-bottom: 1px solid {BORDER};
    font-weight: 600;
    color: {TEXT_DIM};
}}

/* --- Splitters --- */
QSplitter::handle {{
    background-color: {BG_WINDOW};
}}
QSplitter::handle:horizontal {{
    width: 4px;
}}
QSplitter::handle:vertical {{
    height: 4px;
}}
QSplitter::handle:hover {{
    background-color: {ACCENT};
}}

/* --- Scrollbars --- */
QScrollBar:vertical {{
    background: {BG_WINDOW};
    width: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_LIGHT};
    border-radius: 5px;
    min-height: 24px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {BG_WINDOW};
    height: 12px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER_LIGHT};
    border-radius: 5px;
    min-width: 24px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {ACCENT};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* --- Dialogs & message boxes --- */
QDialog {{
    background-color: {BG_WINDOW};
}}
QMessageBox {{
    background-color: {BG_WINDOW};
}}
QProgressDialog {{
    background-color: {BG_WINDOW};
}}
QProgressBar {{
    background-color: {BG_FIELD};
    border: 1px solid {BORDER};
    border-radius: 4px;
    text-align: center;
    color: {TEXT};
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 3px;
}}

QToolTip {{
    background-color: {BG_PANEL};
    color: {TEXT};
    border: 1px solid {BORDER_LIGHT};
    padding: 4px 6px;
}}
"""
