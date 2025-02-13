from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QPushButton, \
    QHBoxLayout

from ui.utils import centralize


class AddChannelWidget(QWidget):
    checkChannelExists = pyqtSignal(str)
    commit = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("OSSK | Add channel to track")
        self.setWindowModality(Qt.ApplicationModal)
        self.setFixedSize(400, 120)
        centralize(self)

        self.field_channel = QLineEdit()
        self.field_channel.setPlaceholderText(
            "Enter YouTube channel name")
        self.field_channel.textChanged[str].connect(
            self.checkChannelExists[str].emit)
        self.field_channel.returnPressed.connect(self.commit_and_close)

        self.button_commit = QPushButton("Add")
        self.button_commit.setFixedWidth(100)
        self.button_commit.clicked[bool].connect(self.commit_and_close)
        self.button_cancel = QPushButton("Cancel")
        self.button_cancel.setFixedWidth(100)
        self.button_cancel.clicked[bool].connect(self.close)

        buttons_layout = QHBoxLayout()
        buttons_layout.setAlignment(Qt.AlignRight)
        buttons_layout.addWidget(self.button_commit)
        buttons_layout.addWidget(self.button_cancel)

        vbox = QVBoxLayout()
        vbox.addWidget(self.field_channel)
        vbox.addLayout(buttons_layout)
        self.setLayout(vbox)

    def commit_and_close(self):
        self.commit.emit()
        self.close()

    def show(self):
        super().show()
        self.field_channel.setFocus()
