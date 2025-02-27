from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget, QLabel, QBoxLayout, QFrame, QComboBox

from static_vars import SettingsContainer
from ui.utils import centralize


def common_splitter():
    splitter = QFrame()
    splitter.setObjectName('splitter')
    splitter.setFrameStyle(QFrame.HLine | QFrame.Plain)
    return splitter


class BaseWidget(QWidget):
    """ Centralize, '_init_ui' """

    def __init__(self, *args, **kwargs):
        super(BaseWidget, self).__init__(*args, **kwargs)
        centralize(self)
        self._init_ui()

    def _init_ui(self):
        raise NotImplementedError


class ConfirmableWidget(BaseWidget):
    confirm = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWindowModality(Qt.ApplicationModal)
        self.confirm.connect(self.close)


class SettingsWidget(ConfirmableWidget, SettingsContainer):
    ...


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


class ComboBox(QComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.view().parentWidget().setStyleSheet(
            'alternate-background-color: #000;'
        )
    def showPopup(self):
        self.view().setMinimumWidth(self.view().sizeHintForColumn(0)+40)
        super().showPopup()
