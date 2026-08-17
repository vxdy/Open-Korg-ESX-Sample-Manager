from PyQt6.QtCore import QEvent, QPoint, QSortFilterProxyModel, Qt
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QLineEdit, QListView, QVBoxLayout
)

from ui.i18n import tr


class SearchableComboBox(QComboBox):
    """A closed dropdown (not an editable text field - clicking it opens a
    popup, the box itself only ever displays the current selection) whose
    popup carries its own search box above the item list. Typing in that
    search box filters the same scrollable list live; it is never replaced
    by a separate autocomplete popup.

    Items are added as (display_text, data) pairs via add_items_with_data().
    `data` is preserved through filtering (stored as Qt.UserRole on each
    row) so selection and currentData() stay correct regardless of whether
    the list is currently filtered.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(False)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

        self._source_model = QStandardItemModel(self)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._source_model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setModel(self._proxy)

        self._popup = None
        self._search_edit = None
        self._list_view = None

    def add_items_with_data(self, items):
        self._source_model.clear()
        for text, data in items:
            item = QStandardItem(text)
            item.setEditable(False)
            item.setData(data, Qt.ItemDataRole.UserRole)
            self._source_model.appendRow(item)

    def set_current_data(self, data):
        """Select the row holding `data`, independent of any active filter."""
        self._proxy.setFilterFixedString("")
        for row in range(self._source_model.rowCount()):
            if self._source_model.item(row).data(Qt.ItemDataRole.UserRole) == data:
                self.setCurrentIndex(row)
                return
        self.setCurrentIndex(-1)

    def _ensure_popup(self):
        if self._popup is not None:
            return
        self._popup = QFrame(self, Qt.WindowType.Popup)
        self._popup.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self._popup)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(tr("common.search_ellipsis"))
        self._search_edit.textEdited.connect(self._proxy.setFilterFixedString)
        self._search_edit.installEventFilter(self)
        layout.addWidget(self._search_edit)

        self._list_view = QListView()
        self._list_view.setModel(self._proxy)
        self._list_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._list_view.clicked.connect(self._on_item_picked)
        layout.addWidget(self._list_view)

    def showPopup(self):
        self._ensure_popup()
        self._proxy.setFilterFixedString("")
        self._search_edit.clear()

        width = max(self.width(), 260)
        self._popup.resize(width, 280)
        self._popup.move(self.mapToGlobal(QPoint(0, self.height())))

        current_row = self.currentIndex()
        if current_row >= 0:
            idx = self._proxy.index(current_row, 0)
            self._list_view.setCurrentIndex(idx)
            self._list_view.scrollTo(idx, QAbstractItemView.ScrollHint.PositionAtCenter)

        self._popup.show()
        self._search_edit.setFocus()

    def hidePopup(self):
        if self._popup is not None:
            self._popup.hide()

    def _on_item_picked(self, proxy_index):
        data = proxy_index.data(Qt.ItemDataRole.UserRole)
        self.hidePopup()
        self.set_current_data(data)
        self.activated.emit(self.currentIndex())

    def eventFilter(self, obj, event):
        if obj is self._search_edit and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self._list_view.setFocus()
                self._list_view.keyPressEvent(event)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                idx = self._list_view.currentIndex()
                if idx.isValid():
                    self._on_item_picked(idx)
                return True
            if key == Qt.Key.Key_Escape:
                self.hidePopup()
                return True
        return super().eventFilter(obj, event)
