from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QVBoxLayout, QLineEdit, QPushButton, QHBoxLayout, \
    QCheckBox

from ui.components.base import ConfirmableWidget, Field


class AddChannelWidget(ConfirmableWidget):
    checkChannelExists = pyqtSignal(str)

    def _init_ui(self):
        self.setWindowTitle("OSSK | Add channel to track")
        self.setFixedSize(400, 120)

        self.field_channel = QLineEdit()
        self.field_channel.setPlaceholderText(
            "Enter YouTube channel name")
        self.field_channel.textChanged[str].connect(
            self.checkChannelExists[str].emit)
        self.field_channel.returnPressed.connect(self.confirm.emit)

        button_commit = QPushButton("Apply")
        button_commit.setFixedWidth(100)
        button_commit.clicked[bool].connect(self.confirm.emit)
        button_cancel = QPushButton("Cancel")
        button_cancel.setFixedWidth(100)
        button_cancel.clicked[bool].connect(self.close)

        buttons_layout = QHBoxLayout()
        buttons_layout.setAlignment(Qt.AlignRight)
        buttons_layout.addWidget(button_commit)
        buttons_layout.addWidget(button_cancel)

        vbox = QVBoxLayout()
        vbox.addWidget(self.field_channel)
        vbox.addLayout(buttons_layout)
        self.setLayout(vbox)

    def show(self):
        super().show()
        self.field_channel.setFocus()


class BypassWidget(ConfirmableWidget):

    def _init_ui(self):
        self.setWindowTitle("OSSK | Bypass settings")
        self.setFixedSize(400, 120)

        self.checkbox_use_cookie = Field("Use cookies", QCheckBox())

        button_apply = QPushButton("Apply")
        button_apply.clicked.connect(self.confirm.emit)

        vbox = QVBoxLayout()
        vbox.addLayout(self.checkbox_use_cookie)
        vbox.addWidget(button_apply)
        self.setLayout(vbox)
