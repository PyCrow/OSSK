from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel

from ui.utils import centralize


class BaseWidget(QWidget):

    def __init__(self, *args, **kwargs):
        super(BaseWidget, self).__init__(*args, **kwargs)
        self.setWindowModality(Qt.ApplicationModal)
        centralize(self)
        self._init_ui()

    def _init_ui(self):
        raise NotImplementedError


class ConfirmableWidget(BaseWidget):
    confirm = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.confirm.connect(self.close)


class Field(QHBoxLayout):

    def __init__(self, field_name: str, widget):
        super(Field, self).__init__()
        self.widget = widget
        self.addWidget(QLabel(field_name), alignment=Qt.AlignLeft)
        self.addWidget(widget, alignment=Qt.AlignRight)
