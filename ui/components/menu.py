from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QVBoxLayout, QLineEdit, QPushButton, QHBoxLayout, \
    QCheckBox, QComboBox

from main_utils import UA
from static_vars import KEYS
from ui.components.base import ConfirmableWidget, Field, common_splitter, \
    SettingsWidget


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


class BypassWidget(SettingsWidget):

    def _init_ui(self):
        self.setWindowTitle("OSSK | Bypass settings")
        self.setFixedSize(450, 160)

        checkbox_use_cookie = QCheckBox()
        self.field_use_cookie = Field("Use cookies", checkbox_use_cookie)

        box_browser = QComboBox()
        box_browser.addItems(UA.browsers)
        self.field_useragent = Field("User-Agent of", box_browser)

        checkbox_use_cookie.stateChanged.connect(box_browser.setEnabled)

        button_apply = QPushButton("Apply")
        button_apply.clicked.connect(self.confirm.emit)

        vbox = QVBoxLayout()
        vbox.addLayout(self.field_use_cookie)
        vbox.addWidget(common_splitter())
        vbox.addLayout(self.field_useragent)
        vbox.addWidget(button_apply)
        self.setLayout(vbox)

    def update_values(self, settings=None):
        if settings is not None:
            self.field_use_cookie.widget.setChecked(settings[KEYS.USE_COOKIES])
            item = self.field_useragent.widget.findText(
                settings[KEYS.BROWSER], Qt.MatchFixedString)
            if item > -1:
                self.field_useragent.widget.setCurrentIndex(item)
        use_cookie = self.field_use_cookie.widget.isChecked()
        self.field_useragent.widget.setEnabled(use_cookie)
