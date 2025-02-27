from PyQt5.QtCore import pyqtSignal, Qt, QUrl, pyqtSlot
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QVBoxLayout, QLineEdit, QPushButton, QHBoxLayout, \
    QCheckBox, QLabel, QBoxLayout, QSpinBox, QFileDialog, QDialog

from main_utils import check_dir_exists, check_exists_and_callable, is_callable
from static_vars import EMPTY_ITEM
from ui.components.base import ConfirmableWidget, Field, common_splitter, \
    SettingsWidget, ComboBox
from ui.dynamic_style import STYLE
from ui.utils import get_supported_browsers


class AddChannelWidget(ConfirmableWidget):
    checkChannelExists = pyqtSignal(str)

    def _init_ui(self):
        self.setWindowTitle("OSSK | Add channel to track")
        self.setFixedSize(400, 120)

        self.field_channel = QLineEdit()
        self.field_channel.setPlaceholderText("Enter YouTube channel name")
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


class SettingsWindow(SettingsWidget):

    def _init_ui(self):
        self.setWindowTitle("OSSK | General settings")
        self.setFixedSize(750, 500)

        # Field: Records directory
        self.field_records_dir = QLineEdit()
        self.field_records_dir.setPlaceholderText(
            "Enter path to records directory")
        self.field_records_dir.textChanged[str].connect(
            self._check_records_dir)
        self.field_records_dir.setToolTip(
            "Checks is the specified path available as a directory.\n"
            "The field is highlighted in red if the path is\n"
            " not available.")
        button_open_rec_dir = QPushButton("Open")
        button_open_rec_dir.clicked[bool].connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(self.field_records_dir.text())
            )
        )
        button_select_ffmpeg_file = QPushButton("Select")
        button_select_ffmpeg_file.clicked[bool].connect(
            self._records_dir_selector)
        records_dir_layout = QHBoxLayout()
        records_dir_layout.addWidget(self.field_records_dir)
        records_dir_layout.addWidget(button_open_rec_dir)
        records_dir_layout.addWidget(button_select_ffmpeg_file)
        records_layout = QVBoxLayout()
        records_layout.addWidget(QLabel("Records directory"))
        records_layout.addLayout(records_dir_layout)

        # Field: Path to ffmpeg
        self.field_ffmpeg_file = QLineEdit()
        self.field_ffmpeg_file.setPlaceholderText("Enter path to ffmpeg")
        self.field_ffmpeg_file.textChanged[str].connect(self._check_ffmpeg)
        self.field_ffmpeg_file.setToolTip(
            "Checks:\n"
            "1. Is the specified path available as a file.\n"
            "2. Is the specified file can be called.\n"
            "The field is highlighted in red if the path file is\n"
            " not available.")
        button_select_ffmpeg_file = QPushButton("Select")
        button_select_ffmpeg_file.clicked[bool].connect(self._ffmpeg_selector)
        hbox_ffmpeg = QHBoxLayout()
        hbox_ffmpeg.addWidget(self.field_ffmpeg_file)
        hbox_ffmpeg.addWidget(button_select_ffmpeg_file)
        ffmpeg_layout = QVBoxLayout()
        ffmpeg_layout.addWidget(QLabel("Path to ffmpeg"))
        ffmpeg_layout.addLayout(hbox_ffmpeg)

        # Field: Command or path to yt-dlp
        self.line_ytdlp = QLineEdit()
        self.line_ytdlp.setPlaceholderText(
            "Enter command or path to yt-dlp")
        self.line_ytdlp.setToolTip(
            "Checks:\n"
            "1. Is called as a command.\n"
            "2. Is the specified path available as a file.\n"
            "3. Is the specified file can be called.\n"
            "The field is highlighted in red if the path file is\n"
            " not available.")
        field_ytdlp = Field("Command or path to yt-dlp",
                            self.line_ytdlp,
                            orientation=QBoxLayout.Direction.TopToBottom)

        # Field: Max downloads
        self.box_max_downloads = QSpinBox(self)
        self.box_max_downloads.setRange(0, 50)
        self.box_max_downloads.valueChanged[int].connect(
            self._check_max_downloads)
        self.box_max_downloads.setToolTip(
            "Range from 1 to 50.\n"
            "It is not recommended to set a value greater than 12 or 0.\n"
            "0 - no restrictions.")
        field_max_downloads = Field("Maximum number of synchronous downloads",
                                    self.box_max_downloads)

        # Field: Time between scans
        self.box_scanner_sleep = QSpinBox(self)
        self.box_scanner_sleep.setRange(1, 60)
        self.box_scanner_sleep.valueChanged[int].connect(
            self._check_scanner_sleep)
        self.box_scanner_sleep.setToolTip(
            "Waiting time between channel scans (minutes).\n"
            "Range from 1 to 60.\n"
            "It is not recommended to set it to less than 5 minutes, so\n"
            " that YouTube does not consider the scan as a DoS attack.")
        field_scanner_sleep = Field("Time between scans (minutes)",
                                    self.box_scanner_sleep)

        # Field: Process termination timeout
        self.box_proc_term_timeout = QSpinBox(self)
        self.box_proc_term_timeout.setRange(0, 3600)
        self.box_proc_term_timeout.valueChanged[int].connect(
            self._check_proc_term_timeout)
        self.box_proc_term_timeout.setToolTip(
            "Waiting time for process finished (seconds).\n"
            "Range from 0 (don't wait) to 3600 (hour).\n"
            "Default value - 600.\n"
            "When the time runs out, the process will be killed.\n"
            "It is not recommended to set it to less than 20 seconds,\n"
            " since it can take a long time to merge video and audio\n"
            " tracks of long recordings.")
        field_proc_term_timeout = Field("Process termination timeout (sec)",
                                        self.box_proc_term_timeout)

        # Field: Hide successfully finished processes
        self.box_hide_suc_fin_proc = QCheckBox()
        self.box_hide_suc_fin_proc.setToolTip(
            "Successfully finished processes will be hidden.")
        field_hide_suc_fin_proc = Field("Hide successfully finished processes",
                                        self.box_hide_suc_fin_proc)

        self.button_apply = QPushButton("Apply", self)
        self.button_apply.clicked.connect(self._post_validation)

        vbox = QVBoxLayout()
        vbox.addLayout(records_layout)
        vbox.addWidget(common_splitter())
        vbox.addLayout(ffmpeg_layout)
        vbox.addWidget(common_splitter())
        vbox.addLayout(field_ytdlp)
        vbox.addWidget(common_splitter())
        vbox.addLayout(field_max_downloads)
        vbox.addWidget(common_splitter())
        vbox.addLayout(field_scanner_sleep)
        vbox.addWidget(common_splitter())
        vbox.addLayout(field_proc_term_timeout)
        vbox.addWidget(common_splitter())
        vbox.addLayout(field_hide_suc_fin_proc)
        vbox.addSpacing(20)
        vbox.addWidget(self.button_apply)

        self.setLayout(vbox)

    def update_values(self, settings: 'Settings'):
        if settings is not None:
            self.field_records_dir.setText(settings.records_dir)
            self.field_ffmpeg_file.setText(settings.ffmpeg)
            self.line_ytdlp.setText(settings.ytdlp)
            self.box_max_downloads.setValue(settings.max_downloads)
            self.box_scanner_sleep.setValue(settings.scanner_sleep_min)
            self.box_proc_term_timeout.setValue(
                settings.proc_term_timeout_sec)
            self.box_hide_suc_fin_proc.setChecked(
                settings.hide_suc_fin_proc)

    def _records_dir_selector(self):
        d = QFileDialog(
            caption="Select records directory",
            directory=self.field_records_dir.text())
        d.setFileMode(QFileDialog.Directory)
        d.setOption(QFileDialog.ShowDirsOnly)
        d.setViewMode(QFileDialog.Detail)
        if d.exec_() == QDialog.Accepted:
            self.field_records_dir.setText(d.selectedFiles()[0])

    def _ffmpeg_selector(self):
        d = QFileDialog(
            caption="Select ffmpeg file",
            directory=self.field_ffmpeg_file.text())
        d.setFileMode(QFileDialog.ExistingFile)
        d.setViewMode(QFileDialog.Detail)
        if d.exec_() == QDialog.Accepted:
            self.field_ffmpeg_file.setText(d.selectedFiles()[0])

    @pyqtSlot(int)
    def _check_max_downloads(self, value: int):
        status = STYLE.SPIN_WARNING if value not in range(1, 13) \
            else STYLE.SPIN_VALID
        self.box_max_downloads.setStyleSheet(status)

    @pyqtSlot(str)
    def _check_records_dir(self, records_dir: str):
        suc = check_dir_exists(records_dir)
        status = STYLE.LINE_INVALID if not suc else STYLE.LINE_VALID
        self.field_records_dir.setStyleSheet(status)

    @pyqtSlot(str)
    def _check_ffmpeg(self, ffmpeg_path: str):
        suc = check_exists_and_callable(ffmpeg_path)
        status = STYLE.LINE_INVALID if not suc else STYLE.LINE_VALID
        self.field_ffmpeg_file.setStyleSheet(status)

    def _check_ytdlp(self):
        ytdlp_path = self.line_ytdlp.text()
        suc = is_callable(ytdlp_path)
        status = STYLE.LINE_INVALID if not suc else STYLE.LINE_VALID
        self.line_ytdlp.setStyleSheet(status)
        return suc

    @pyqtSlot(int)
    def _check_scanner_sleep(self, value: int):
        status = STYLE.SPIN_WARNING if value < 5 else STYLE.SPIN_VALID
        self.box_scanner_sleep.setStyleSheet(status)

    @pyqtSlot(int)
    def _check_proc_term_timeout(self, value: int):
        status = STYLE.SPIN_WARNING if value < 20 else STYLE.SPIN_VALID
        self.box_proc_term_timeout.setStyleSheet(status)

    def _post_validation(self):
        if self._check_ytdlp():
            self.confirm.emit()


class BypassWidget(SettingsWidget):

    def _init_ui(self):
        self.setWindowTitle("OSSK | Bypass settings")
        self.setFixedSize(500, 160)

        box_cookies_from_browser = ComboBox()
        box_cookies_from_browser.addItem(EMPTY_ITEM)
        box_cookies_from_browser.addItems(get_supported_browsers())
        box_cookies_from_browser.currentIndexChanged.connect(
            self._update_fake_useragent_status)
        self.field_cookies_from_browser = Field(
            "Use cookies (must be installed)", box_cookies_from_browser)

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

    def update_values(self, settings: 'Settings'):
        self.field_fake_useragent.widget.setChecked(settings.fake_useragent)

        cookie_item = self.field_cookies_from_browser.widget.findText(
            settings.cookies_from_browser, Qt.MatchFixedString)
        if cookie_item > -1:
            self.field_cookies_from_browser.widget.setCurrentIndex(cookie_item)

        self._update_fake_useragent_status()
