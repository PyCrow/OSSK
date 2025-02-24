from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QVBoxLayout, QLineEdit, QPushButton, QHBoxLayout, \
    QCheckBox, QComboBox

from main_utils import UA
from static_vars import Settings, EMPTY_ITEM
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
        self.field_channel.clear()
        self.field_channel.setFocus()
        super().show()


class BypassWidget(SettingsWidget):

    def _init_ui(self):
        self.setWindowTitle("OSSK | Bypass settings")
        self.setFixedSize(450, 160)

        box_cookies_from_browser = QComboBox()
        box_cookies_from_browser.addItem(EMPTY_ITEM)
        box_cookies_from_browser.addItems(UA.browsers)
        box_cookies_from_browser.currentIndexChanged.connect(
            self._update_fake_useragent_status)
        self.field_cookies_from_browser = Field(
            "Use cookies", box_cookies_from_browser)

        checkbox_fake_useragent = QCheckBox()
        self.field_fake_useragent = Field("Fake useragent",
                                          checkbox_fake_useragent)

        button_apply = QPushButton("Apply")
        button_apply.clicked.connect(self.confirm.emit)

        vbox = QVBoxLayout()
        vbox.addLayout(self.field_cookies_from_browser)
        vbox.addWidget(common_splitter())
        vbox.addLayout(self.field_fake_useragent)
        vbox.addWidget(button_apply)
        self.setLayout(vbox)

    def _update_fake_useragent_status(self):
        self.field_fake_useragent.widget.setEnabled(
            self.field_cookies_from_browser.widget.currentText() != EMPTY_ITEM
        )

    def update_values(self, settings: Settings):
        self.field_fake_useragent.widget.setChecked(settings.fake_useragent)

        cookie_item = self.field_cookies_from_browser.widget.findText(
            settings.cookies_from_browser, Qt.MatchFixedString)
        if cookie_item > -1:
            self.field_cookies_from_browser.widget.setCurrentIndex(cookie_item)

        self._update_fake_useragent_status()
