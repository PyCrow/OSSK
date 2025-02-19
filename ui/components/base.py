from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget, QLabel, QBoxLayout, QFrame

from static_vars import SettingsType
from ui.utils import centralize


def common_splitter():
    splitter = QFrame()
    splitter.setObjectName('splitter')
    splitter.setFrameStyle(QFrame.HLine | QFrame.Plain)
    return splitter


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


class SettingsWidget(ConfirmableWidget):

    def update_values(self, setting: SettingsType = None):
        raise NotImplementedError


class Field(QBoxLayout):

    def __init__(
            self,
            field_name: str,
            widget,
            orientation=QBoxLayout.Direction.LeftToRight,
    ):
        super(Field, self).__init__(orientation)
        self.widget = widget
        self.addWidget(QLabel(field_name), alignment=Qt.AlignLeft)
        if orientation == QBoxLayout.Direction.LeftToRight:
            self.addWidget(widget, alignment=Qt.AlignRight)
        else:
            self.addWidget(widget)
