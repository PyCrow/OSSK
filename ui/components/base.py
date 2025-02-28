from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget, QLabel, QBoxLayout, QFrame, QComboBox, \
    QVBoxLayout, QHBoxLayout, QPushButton

from static_vars import SettingsContainer
from ui.utils import centralize


def common_splitter():
    splitter = QFrame()
    splitter.setObjectName('field_splitter')
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

    def _init_ui(self):
        # Horizontal manage buttons
        button_commit = QPushButton("Apply")
        button_commit.setObjectName('button_apply')
        button_commit.setFixedWidth(100)
        button_commit.clicked[bool].connect(self.confirm.emit)
        button_cancel = QPushButton("Cancel")
        button_cancel.setObjectName('button_cancel')
        button_cancel.setFixedWidth(100)
        button_cancel.clicked[bool].connect(self.close)
        hbox_buttons = QHBoxLayout()
        hbox_buttons.addStretch(0)
        hbox_buttons.addWidget(button_commit)
        hbox_buttons.addWidget(button_cancel)

        # Central widget
        self.central = QVBoxLayout()
        central_widget = QWidget(self)
        central_widget.setLayout(self.central)

        # Hidden vertical box
        main_vbox = QVBoxLayout()
        main_vbox.addWidget(central_widget)
        main_vbox.addLayout(hbox_buttons)
        self.setLayout(main_vbox)


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
