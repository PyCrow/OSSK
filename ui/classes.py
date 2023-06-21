from __future__ import annotations

from datetime import datetime

from PyQt5.QtCore import pyqtSlot, Qt
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QLinearGradient, \
    QColor, QMouseEvent
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLineEdit, QListView, QAbstractItemView,
    QLabel, QSpinBox, QMenu, QAction, QComboBox, QTabWidget, QTreeView
)

from static_vars import AVAILABLE_STREAM_RECORD_QUALITIES, RecordProcess
from ui.dynamic_style import STYLE
from utils import check_exists_and_callable, is_callable


class ChannelStatus:
    OFF = 0
    QUEUE = 1
    REC = 2
    FAIL = 3


class ChannelItem(QStandardItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.channel: str = ''


class RecordProcessItem(QStandardItem):
    def __init__(self, *args, **kwargs):
        self.pid = None
        super(RecordProcessItem, self).__init__(*args, **kwargs)


def _get_channel_status_color(status_id) -> QLinearGradient:
    colors = {ChannelStatus.OFF: QColor(50, 50, 50),
              ChannelStatus.QUEUE: QColor(180, 180, 0),
              ChannelStatus.REC: QColor(0, 180, 0),
              ChannelStatus.FAIL: QColor(180, 0, 0)}
    color = colors[status_id]
    gradient = QLinearGradient(0, 0, 300, 0)
    gradient.setColorAt(0.0, QColor(25, 25, 25))
    gradient.setColorAt(0.6, QColor(25, 25, 25))
    gradient.setColorAt(1.0, color)
    return gradient


class ListView(QListView):

    def __init__(self):
        super().__init__()
        self._model = QStandardItemModel()
        self.setModel(self._model)
        self.setWordWrap(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

    def add_str_item(self, text: str):
        item = QStandardItem(text)
        item.setEditable(False)
        self._model.appendRow(item)


class ChannelsTree(QTreeView):

    def __init__(self):
        super(ChannelsTree, self).__init__()
        self._model = QStandardItemModel()
        self.setModel(self._model)
        self._root = self._model.invisibleRootItem()
        self.setHeaderHidden(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

        self._map_channel_item: dict[str, ChannelItem] = {}
        self._map_pid_item: dict[str, RecordProcessItem] = {}

        self.selected_item_index: int | None = None
        self.on_click_settings = QAction("Channel settings", self)
        self.on_click_delete = QAction("Delete channel", self)
        self.on_click_open_tab = QAction("Open tab", self)  # TODO: connect
        self.on_click_stop = QAction("Stop process", self)  # TODO: connect

    def add_channel_item(self, channel_name: str, alias: str):
        text = alias if alias else channel_name
        item = ChannelItem(text)
        item.channel = channel_name
        item.setEditable(False)
        self._map_channel_item[channel_name] = item
        self._model.appendRow(item)

    def del_channel_item(self):
        del self._map_channel_item[self._selected_channel().channel]
        self._model.removeRow(self._selected_channel().row())

    def _selected_channel(self) -> ChannelItem:
        return self._model.itemFromIndex(self.selected_item_index)

    def selected_channel_name(self) -> str:
        return self._selected_channel().channel

    def set_channel_alias(self, alias: str):
        self._model.itemFromIndex(self.selected_item_index).setText(alias)

    def add_child_process_item(self, channel_name: str,
                               pid: int, stream_name: str):
        channel_item = self._map_channel_item[channel_name]
        process_item = RecordProcessItem(stream_name)
        process_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        process_item.pid = pid
        self._map_pid_item[channel_name] = process_item
        channel_item.appendRow(process_item)
        self.expand(self._model.indexFromItem(channel_item))

    def del_child_process_item(self):
        # self._map_pid_item[channel_name] = process_item
        ...

    def mousePressEvent(self, e: QMouseEvent):
        self.clearSelection()
        self.selected_item_index = None
        super(ChannelsTree, self).mousePressEvent(e)

    def contextMenuEvent(self, event):
        selected_indexes = self.selectedIndexes()
        if len(selected_indexes) == 1:
            self.selected_item_index = selected_indexes[0]
            selected_item = self._model.itemFromIndex(self.selected_item_index)
            if isinstance(selected_item, ChannelItem):
                self._single_channel_menu().exec(event.globalPos())
            elif isinstance(selected_item, RecordProcessItem):
                self._single_process_menu().exec(event.globalPos())

    def _single_channel_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.addAction(self.on_click_settings)
        menu.addSeparator()
        menu.addAction(self.on_click_delete)
        return menu

    def _single_process_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.addAction(self.on_click_open_tab)
        menu.addSeparator()
        menu.addAction(self.on_click_stop)
        return menu

    def set_stream_status(self, ch_index: int, status_id: int):
        """ Sets channel's row color """
        # TODO: make it with a dynamic_style or any other way
        color = _get_channel_status_color(status_id)
        self._model.item(ch_index).setBackground(color)


class LogTabWidget(QTabWidget):
    def __init__(self):
        super(LogTabWidget, self).__init__()
        self._init_ui()
        self._map_pid_widget: dict[int, LogWidget] = {}

    def _init_ui(self):
        self.setMovable(True)

        # Add closability
        self.setTabsClosable(True)
        self.tabCloseRequested[int].connect(self.close_tab)

        self.common = LogWidget()
        self.addTab(self.common, "Common")

    def add_new_process_tab(self, stream_name: str, pid: int):
        self._map_pid_widget[pid] = LogWidget()
        self.addTab(self._map_pid_widget[pid], stream_name)

    @pyqtSlot(int)
    def close_tab(self, tab_index: int):
        if tab_index == self.indexOf(self.common):
            return
        self.removeTab(tab_index)

    def proc_log(self, pid: int, message: str):
        self._map_pid_widget[pid].add_message(message)


class LogWidget(ListView):
    _items_limit = 500

    @property
    def time(self):
        now = datetime.now()
        return now.strftime("%H:%M:%S")

    def __init__(self, process: RecordProcess | None = None):
        super().__init__()
        self.process = process

    def add_message(self, text):
        message = f"{self.time} {text}"
        self.add_str_item(message)
        if self._model.rowCount() > self._items_limit:
            self._model.removeRow(0)
        self.scrollToBottom()


class SettingsWindow(QWidget):
    def __init__(self):
        super(SettingsWindow, self).__init__()
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("StreamSaver | Settings")
        self.setWindowModality(Qt.ApplicationModal)

        self.setMinimumWidth(400)
        self.setMaximumWidth(750)
        self.setMinimumHeight(300)
        self.setMaximumHeight(500)
        self.resize(500, 360)

        self.field_ffmpeg = QLineEdit(parent=self)
        self.field_ffmpeg.setPlaceholderText(
            "Enter path to ffmpeg")
        self.field_ffmpeg.textChanged[str].connect(self._check_ffmpeg)
        self.field_ffmpeg.setToolTip(
            "Checks:\n"
            "1. Is the specified path available as a file.\n"
            "2. Is the specified file can be called.\n"
            "The field is highlighted in red if the path file is"
            " not available."
        )

        self.field_ytdlp = QLineEdit(parent=self)
        self.field_ytdlp.setPlaceholderText(
            "Enter command or path to yt-dlp")
        self.field_ytdlp.textChanged[str].connect(self._check_ytdlp)
        self.field_ytdlp.setToolTip(
            "Checks:\n"
            "1. Is called as a command.\n"
            "2. Is the specified path available as a file.\n"
            "3. Is the specified file can be called.\n"
            "The field is highlighted in red if the path file is"
            " not available."
        )

        self.box_max_downloads = QSpinBox(self)
        self.box_max_downloads.setToolTip(
            "Range from 1 to 50.\n"
            "It is not recommended to set a value greater than 12 or 0.\n"
            "0 - no restrictions."
        )
        self.box_max_downloads.setRange(0, 50)
        self.box_max_downloads.valueChanged[int].connect(
            self._check_max_downloads)

        self.box_scanner_sleep = QSpinBox(self)
        self.box_scanner_sleep.setToolTip(
            "Waiting time between channel scans (minutes).\n"
            "Range from 1 to 60.\n"
            "It is not recommended to set it to less than 5 minutes, so\n"
            " that YouTube does not consider the scan as a DoS attack."
        )
        self.box_scanner_sleep.setRange(1, 60)
        self.box_scanner_sleep.valueChanged[int].connect(
            self._check_scanner_sleep)

        self.button_apply = QPushButton("Accept", self)

        vbox = QVBoxLayout()
        vbox.addWidget(QLabel("Path to ffmpeg"))
        vbox.addWidget(self.field_ffmpeg)
        vbox.addStretch(1)
        vbox.addWidget(QLabel("Command or path to yt-dlp"))
        vbox.addWidget(self.field_ytdlp)
        vbox.addStretch(1)
        vbox.addWidget(QLabel("Maximum number of synchronous downloads"))
        vbox.addWidget(self.box_max_downloads)
        vbox.addStretch(1)
        vbox.addWidget(QLabel("Time between scans (minutes)"))
        vbox.addWidget(self.box_scanner_sleep)
        vbox.addStretch(2)
        vbox.addWidget(self.button_apply)

        self.setLayout(vbox)

    @pyqtSlot(int)
    def _check_max_downloads(self, value: int):
        status = STYLE.SPIN_WARNING if value not in range(1, 13) \
            else STYLE.SPIN_VALID
        self.box_max_downloads.setStyleSheet(status)

    @pyqtSlot(str)
    def _check_ffmpeg(self, ffmpeg_path: str):
        suc = check_exists_and_callable(ffmpeg_path)
        status = STYLE.LINE_INVALID if not suc else STYLE.LINE_VALID
        self.field_ffmpeg.setStyleSheet(status)

    @pyqtSlot(str)
    def _check_ytdlp(self, ytdlp_path: str):
        suc = is_callable(ytdlp_path)
        status = STYLE.LINE_INVALID if not suc else STYLE.LINE_VALID
        self.field_ytdlp.setStyleSheet(status)

    @pyqtSlot(int)
    def _check_scanner_sleep(self, value: int):
        status = STYLE.SPIN_WARNING if value < 5 else STYLE.SPIN_VALID
        self.box_scanner_sleep.setStyleSheet(status)


class ChannelSettingsWindow(QWidget):
    def __init__(self):
        super(ChannelSettingsWindow, self).__init__()
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("StreamSaver | Channel settings")
        self.setWindowModality(Qt.ApplicationModal)

        self.setMinimumWidth(300)
        self.setMaximumWidth(500)
        self.setMinimumHeight(300)
        self.setMaximumHeight(500)
        self.resize(400, 300)

        self.label_channel = QLabel(self)

        self.line_alias = QLineEdit()
        self.line_alias.setPlaceholderText(
            "Enter readable alias for the channel")

        self.box_svq = QComboBox()
        self.box_svq.addItems(list(AVAILABLE_STREAM_RECORD_QUALITIES.keys()))

        self.button_apply = QPushButton("Accept", self)

        vbox = QVBoxLayout()
        vbox.addWidget(self.label_channel, alignment=Qt.AlignHCenter)
        vbox.addStretch(1)
        vbox.addWidget(QLabel("Channel alias"))
        vbox.addWidget(self.line_alias)
        vbox.addStretch(1)
        vbox.addWidget(QLabel("Stream video quality"))
        vbox.addWidget(self.box_svq)
        vbox.addStretch(2)
        vbox.addWidget(self.button_apply)

        self.setLayout(vbox)

    def update_data(self, channel_name: str, alias: str, svq: str):
        self.label_channel.setText(channel_name)
        self.line_alias.setText(alias)
        index_svq = self.box_svq.findText(svq)
        self.box_svq.setCurrentIndex(index_svq)

    def get_data(self) -> tuple[str, str, str]:
        ch_name = self.label_channel.text()
        alias = self.line_alias.text()
        svq = self.box_svq.currentText()
        self.close()
        return ch_name, alias, svq
