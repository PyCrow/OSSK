from __future__ import annotations

import logging
from datetime import datetime
from typing import Union

from PyQt5.QtCore import pyqtSignal, pyqtSlot, QModelIndex, Qt, QUrl
from PyQt5.QtGui import (QColor, QLinearGradient, QMouseEvent,
                         QStandardItem, QStandardItemModel, QDesktopServices)
from PyQt5.QtWidgets import (
    QAbstractItemView, QAction, QHBoxLayout,
    QLabel, QLineEdit, QListView, QMenu, QPushButton, QTabWidget,
    QTreeView, QVBoxLayout, QWidget, QMainWindow)

from main_utils import get_channel_dir
from static_vars import (
    logging_handler, AVAILABLE_STREAM_RECORD_QUALITIES, RecordProcess,
    STYLESHEET_PATH, Settings, CHANNEL_URL_TEMPLATE)
from ui.components.base import ConfirmableWidget, Field, ComboBox, BaseWidget
from ui.components.items import ChannelItem, RecordProcessItem
from ui.components.menu import AddChannelWidget, BypassWidget, SettingsWindow
from ui.utils import centralize

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.addHandler(logging_handler)


class Status:

    class Channel:
        OFF = 0
        LIVE = 1
        _color_map = {OFF: QColor(50, 50, 50),
                      LIVE: QColor(0, 180, 0)}

        @staticmethod
        def gradient(status_id: int) -> QLinearGradient:
            color = Status.Channel._color_map[status_id]
            return Status._smooth_gradient(color)

    class Stream:
        OFF = 0
        REC = 1
        FAIL = 2

        _color_map = {OFF: QColor(50, 50, 50),
                      REC: QColor(0, 180, 0),
                      FAIL: QColor(180, 0, 0)}

        @staticmethod
        def foreground(status_id: int) -> QColor:
            return Status.Stream._color_map[status_id]

    class Message:
        DEBUG = 10
        INFO = 20
        WARNING = 30
        ERROR = 40

        _color_map = {DEBUG: QColor(120, 120, 120),
                      INFO: QColor(0, 255, 0),
                      WARNING: QColor(255, 255, 0),
                      ERROR: QColor(255, 0, 0)}

        @staticmethod
        def foreground(level: int) -> QColor:
            return Status.Message._color_map[level]

    @staticmethod
    def _smooth_gradient(qcolor: QColor):
        gradient = QLinearGradient(0, 0, 300, 0)
        gradient.setColorAt(0.0, QColor(25, 25, 25))
        gradient.setColorAt(0.6, QColor(25, 25, 25))
        gradient.setColorAt(1.0, qcolor)
        return gradient


class MainWindow(QMainWindow):
    saveSettings = pyqtSignal(Settings)
    runServices = pyqtSignal(str, str)
    stopServices = pyqtSignal()
    stopProcess = pyqtSignal(int)

    checkExistsChannel = pyqtSignal(str)
    addChannel = pyqtSignal(str)
    delChannel = pyqtSignal(str)
    openChannelSettings = pyqtSignal(str)
    applyChannelSettings = pyqtSignal(tuple)

    def __init__(self, settings: Settings):
        super(MainWindow, self).__init__()
        self._master_works = False
        self._slave_works = False
        self.settings: Union[Settings, None] = None
        self._init_ui()
        self._init_menu()
        self._update_manage_buttons_status()
        self.init_settings(settings)

    def _init_menu(self):
        bar = self.menuBar()

        main_menu = QMenu("File", self)
        action_add_channel = QAction("Add channel to track", self)
        action_add_channel.triggered.connect(self.add_channel_widget.show)
        main_menu.addAction(action_add_channel)
        bar.addMenu(main_menu)

        settings_menu = QMenu("Settings", self)
        general_settings = QAction("General", self)
        general_settings.triggered.connect(self.settings_window.show)
        bypass_settings = QAction("Bypass", self)
        bypass_settings.triggered.connect(self.bypass_settings.show)
        settings_menu.addAction(general_settings)
        settings_menu.addAction(bypass_settings)
        bar.addMenu(settings_menu)

    def _init_ui(self):
        self.setWindowTitle("OSSK")
        self.resize(860, 660)
        centralize(self)

        # Style loading
        style = STYLESHEET_PATH.read_text()
        self.setStyleSheet(style)

        # Main menu widgets
        self.add_channel_widget = AddChannelWidget()
        self.add_channel_widget.checkChannelExists.connect(
            self.checkExistsChannel.emit)
        self.add_channel_widget.confirm.connect(self._send_add_channel)
        self.add_channel_widget.setStyleSheet(style)

        # Settings window
        self.settings_window = SettingsWindow()
        self.settings_window.confirm.connect(self._send_save_settings)
        self.settings_window.setStyleSheet(style)

        self.bypass_settings = BypassWidget()
        self.bypass_settings.confirm.connect(self._send_save_settings)
        self.bypass_settings.setStyleSheet(style)

        self.status_bar = self.statusBar()

        self.widget_channels_tree = ChannelsTree()
        self.widget_channels_tree.action_stop.triggered.connect(
            self._send_stop_process)
        self.widget_channels_tree.action_channel_settings.triggered.connect(
            self._send_open_channel_settings)
        self.widget_channels_tree.action_open_channel_dir.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(
                get_channel_dir(
                    self.widget_channels_tree.selected_channel_name(),
                    self.settings.records_dir,
                )
            )))
        )
        self.widget_channels_tree.action_delete_channel.triggered.connect(
            self._send_del_channel)

        self._button_start = QPushButton()
        self._button_start.setObjectName("start")
        self._button_start.setToolTip("Start scanning and downloading")
        self._button_start.clicked[bool].connect(self._send_start_services)
        self._button_stop = QPushButton()
        self._button_stop.setObjectName("stop")
        self._button_stop.setToolTip("Stop scanning and downloading")
        self._button_stop.clicked.connect(self._send_stop_services)

        hbox_channels_header = QHBoxLayout()
        hbox_channels_header.addWidget(QLabel("Monitored channels"),
                                       stretch=1, alignment=Qt.AlignLeft)
        hbox_channels_header.addWidget(self._button_start)
        hbox_channels_header.addWidget(self._button_stop)

        channels_tree = QVBoxLayout()
        channels_tree.addLayout(hbox_channels_header)
        channels_tree.addWidget(self.widget_channels_tree)

        self.log_tabs = LogTabWidget()
        self.widget_channels_tree.openTabByPid[int, str].connect(
            self.log_tabs.open_tab_by_pid)
        self.widget_channels_tree.closeTabByPid[int].connect(
            self.log_tabs.process_hide)

        main_hbox = QVBoxLayout()
        main_hbox.addLayout(channels_tree, 2)
        main_hbox.addWidget(self.log_tabs, 3)

        central_widget = QWidget(self)
        central_widget.setLayout(main_hbox)
        self.setCentralWidget(central_widget)

        # Channel settings window
        self.channel_settings_window = ChannelSettingsWindow()
        self.channel_settings_window.setStyleSheet(style)
        self.channel_settings_window.confirm.connect(
            self._apply_channel_settings)

    def init_settings(self, settings: Settings):
        """ One-time run """
        self._set_channels(settings)
        self.update_settings(settings)

    def update_settings(self, settings: Settings):
        """ Update all UI values except channels """
        self.settings = settings
        self.set_common_settings_values()

    def _set_channels(self, settings: Settings):
        for channel_name, channel_data in settings.channels.items():
            self.widget_channels_tree.add_channel_item(
                channel_name,
                channel_data.alias,
            )

    def get_common_settings_values(self) -> Settings:
        self.settings.records_dir = \
            self.settings_window.field_records_dir.text()
        self.settings.ffmpeg = \
            self.settings_window.field_ffmpeg_file.text()
        self.settings.ytdlp = \
            self.settings_window.line_ytdlp.text()
        self.settings.max_downloads = \
            self.settings_window.box_max_downloads.value()
        self.settings.scanner_sleep_min = \
            self.settings_window.box_scanner_sleep.value()
        self.settings.proc_term_timeout_sec = \
            self.settings_window.box_proc_term_timeout.value()
        self.settings.hide_suc_fin_proc = \
            self.settings_window.box_hide_suc_fin_proc.isChecked()
        self.settings.fake_useragent = \
            self.bypass_settings.field_fake_useragent.widget.isChecked()
        self.settings.cookies_from_browser = (
            self.bypass_settings.field_cookies_from_browser.widget
            .currentText().lower()
        )
        return self.settings

    def set_common_settings_values(self):
        self.settings_window.update_values(self.settings)
        self.bypass_settings.update_values(self.settings)
        self.widget_channels_tree.hide_suc_fin_proc = \
            self.settings.hide_suc_fin_proc

    def _send_save_settings(self):
        settings = self.get_common_settings_values()
        self.saveSettings[Settings].emit(settings)

    def _update_manage_buttons_status(self):
        if self._master_works or self._slave_works:
            self._button_start.setEnabled(False)
            self._button_stop.setEnabled(True)
        else:
            self._button_start.setEnabled(True)
            self._button_stop.setEnabled(False)

    # OUTGOING SIGNALS
    @pyqtSlot()
    def _send_start_services(self):
        """ [OUT] """
        ffmpeg_path = self.settings_window.field_ffmpeg_file.text()
        ytdlp_command = self.settings_window.line_ytdlp.text()
        self._button_start.setEnabled(False)
        self._button_stop.setEnabled(False)
        self.runServices[str, str].emit(ffmpeg_path, ytdlp_command)

    @pyqtSlot()
    def _send_stop_services(self):
        """ [OUT] """
        self._button_start.setEnabled(False)
        self._button_stop.setEnabled(False)
        self.stopServices.emit()

    @pyqtSlot()
    def _send_stop_process(self):
        """ [OUT] """
        pid = self.widget_channels_tree.selected_process_id()
        self.stopProcess[int].emit(pid)

    @pyqtSlot()
    def _send_add_channel(self):
        """ [OUT] """
        channel_name = self.add_channel_widget.field_channel.text()
        self.addChannel[str].emit(channel_name)

    @pyqtSlot()
    def _send_del_channel(self):
        """ [OUT] """
        channel_name = self.widget_channels_tree.selected_channel_name()
        self.delChannel[str].emit(channel_name)

    @pyqtSlot()
    def _send_open_channel_settings(self):
        """ [OUT] """
        channel_name = self.widget_channels_tree.selected_channel_name()
        self.openChannelSettings[str].emit(channel_name)

    @pyqtSlot()
    def _apply_channel_settings(self):
        """ [OUT] """
        channel_setting = self.channel_settings_window.get_data()
        self.applyChannelSettings[tuple].emit(channel_setting)

    # INCOMING SIGNALS
    @pyqtSlot(int)
    def update_scan_timer(self, seconds: int):
        """ [IN] """
        self.status_bar.showMessage(f"Next scan in: {seconds} seconds", 3000)

    @pyqtSlot(bool)
    def update_master_enabled(self, enabled: bool):
        self._master_works = enabled
        self._update_manage_buttons_status()

    @pyqtSlot(bool)
    def update_slave_enabled(self, enabled: bool):
        self._slave_works = enabled
        self._update_manage_buttons_status()


class ListView(QListView):

    def __init__(self):
        super().__init__()
        self._model = QStandardItemModel()
        self.setModel(self._model)
        self.setWordWrap(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

    def mousePressEvent(self, e: QMouseEvent):
        self.clearSelection()
        super(ListView, self).mousePressEvent(e)


class ChannelsTree(QTreeView):
    openTabByPid = pyqtSignal(int, str)
    closeTabByPid = pyqtSignal(int)

    def __init__(self):
        super(ChannelsTree, self).__init__()
        self.hide_suc_fin_proc = False
        self.selected_item_index: Union[QModelIndex, None] = None
        self._init_ui()

    def _init_ui(self):
        self.setMinimumWidth(250)
        self.setMinimumHeight(135)

        self._model = QStandardItemModel()
        self.setModel(self._model)
        self._root = self._model.invisibleRootItem()
        self.setHeaderHidden(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

        self._map_channel_item: dict[str, ChannelItem] = {}
        self._map_pid_item: dict[int, RecordProcessItem] = {}

        # Channel actions
        self.action_channel_settings = QAction("Channel settings", self)
        self.action_open_channel_dir = QAction("Open channel folder", self)
        self.action_delete_channel = QAction("Delete channel", self)
        # Process actions
        self._action_open_tab = QAction("Open tab", self)
        self.action_stop = QAction("Stop process", self)
        self._action_hide_process = QAction("Hide", self)

        # Connect actions
        self._action_open_tab.triggered[bool].connect(
            self._send_open_tab_by_pid)
        self._action_hide_process.triggered[bool].connect(
            self._del_finished_process_item)

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
                self._single_process_menu(
                    selected_item.finished
                ).exec(event.globalPos())

    # Channel management
    def add_channel_item(self, channel_name: str, alias: str):
        text = alias if alias else channel_name
        item = ChannelItem(text)
        item.channel = channel_name
        item.setEditable(False)
        self._map_channel_item[channel_name] = item
        self._model.appendRow(item)

    def del_channel_item(self):
        selected_channel_item = self._selected_item()
        del self._map_channel_item[selected_channel_item.channel]
        self._model.removeRow(selected_channel_item.row())

    def set_channel_alias(self, alias: str):
        self._model.itemFromIndex(self.selected_item_index).setText(alias)

    def set_channel_status(self, ch_index: int, status_id: int):
        """ Sets channel's row color """
        # TODO: make it with a dynamic_style or any other way
        color = Status.Channel.gradient(status_id)
        self._model.item(ch_index).setBackground(color)

    # Context menus
    def _single_channel_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.addAction(self.action_channel_settings)
        menu.addAction(self.action_open_channel_dir)
        menu.addSeparator()
        menu.addAction(self.action_delete_channel)
        return menu

    def _single_process_menu(self, process_finished: bool) -> QMenu:
        menu = QMenu(self)
        menu.addAction(self._action_open_tab)
        menu.addSeparator()
        if not process_finished:
            menu.addAction(self.action_stop)
        else:
            menu.addAction(self._action_hide_process)
        return menu

    # Selected item functions
    def _selected_item(self) -> Union[ChannelItem, RecordProcessItem]:
        return self._model.itemFromIndex(self.selected_item_index)

    def selected_channel_name(self) -> str:
        """
        Triggering by own action_delete_channel through the controller
        """
        return self._selected_item().channel

    def selected_process_id(self) -> int:
        """
        Triggering by own action_stop through the controller
        """
        return self._selected_item().pid

    def _send_open_tab_by_pid(self):
        process_item = self._selected_item()
        stream_name = process_item.text()
        self.openTabByPid[int, str].emit(process_item.pid, stream_name)

    # Process management
    def add_child_process_item(
            self,
            channel_name: str,
            pid: int,
            stream_name: str
    ):
        channel_item = self._map_channel_item[channel_name]
        process_item = RecordProcessItem(stream_name)
        process_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        process_item.pid = pid
        self._map_pid_item[pid] = process_item
        channel_item.appendRow(process_item)
        self.expand(self._model.indexFromItem(channel_item))

    @pyqtSlot()
    def _del_finished_process_item(self):
        process_item = self._selected_item()
        if not process_item.finished:
            logger.error("Process cannot be hidden: process not finished yet")
            return
        channel_item = process_item.parent()
        channel_item.removeRow(process_item.row())
        del self._map_pid_item[process_item.pid]
        self.closeTabByPid[int].emit(process_item.pid)

    def stream_finished(self, pid: int):
        process_item = self._map_pid_item[pid]

        if self.hide_suc_fin_proc:
            channel_item = process_item.parent()
            channel_item.removeRow(process_item.row())
            del self._map_pid_item[process_item.pid]
        else:
            process_item.finished = True
            color = Status.Stream.foreground(Status.Stream.OFF)
            process_item.setForeground(color)

    def stream_failed(self, pid: int):
        self._map_pid_item[pid].finished = True
        color = Status.Stream.foreground(Status.Stream.FAIL)
        self._map_pid_item[pid].setForeground(color)


class LogTabWidget(QTabWidget):
    def __init__(self):
        super(LogTabWidget, self).__init__()
        self._init_ui()
        self._map_pid_logwidget: dict[int, LogWidget] = {}

    def _init_ui(self):
        self.setMovable(True)

        # Add clos-ability
        self.setTabsClosable(True)
        self.tabCloseRequested[int].connect(self._close_tab)

        self._common_tab = LogWidget()
        self.addTab(self._common_tab, "Common")

    def add_common_message(self, text: str, level: int):
        """
        Print message to tab "Common"

        :param text: Message text
        :param level: Message level (to set font color)
        """
        self._common_tab.add_message(text, level)

    def open_tab_by_pid(self, pid: int, stream_title: str):
        tab_index = self.addTab(self._map_pid_logwidget[pid], stream_title)
        self.setCurrentIndex(tab_index)

    @pyqtSlot(int)
    def _close_tab(self, tab_index: int):
        """
        Close tab except "Common" tab

        :param tab_index: Tab index
        """
        if tab_index == self.indexOf(self._common_tab):
            return
        self.removeTab(tab_index)

    def _close_tab_by_pid(self, pid: int):
        """
        Close tab by pid

        :param pid: Process ID
        """
        tab_index = self.indexOf(self._map_pid_logwidget[pid])
        self._close_tab(tab_index)

    @pyqtSlot(int, str)
    def proc_log(self, pid: int, message: str):
        """
        Print process message

        :param pid: Process ID
        :param message: Process message
        """
        self._map_pid_logwidget[pid].add_message(message)

    def stream_rec(self, pid: int):
        """
        Add new log widget, but do not open it.

        :param pid: Process ID
        """
        self._map_pid_logwidget[pid] = LogWidget()

    def process_hide(self, pid: int):
        """
        Close tab, delete log-widget

        :param pid: Process ID
        """
        self._close_tab_by_pid(pid)
        del self._map_pid_logwidget[pid]

    def stream_finished(self, pid: int):
        """
        Close tab

        :param pid: Process ID
        """
        self._close_tab_by_pid(pid)

    def stream_failed(self, pid: int):
        """
        Close tab

        :param pid: Process ID
        """
        self._close_tab_by_pid(pid)


class LogWidget(ListView):
    _items_limit = 500

    @property
    def time(self):
        now = datetime.now()
        return now.strftime("%H:%M:%S")

    def __init__(self, process: Union[RecordProcess, None] = None):
        super().__init__()
        self.setMinimumWidth(460)
        self.setMinimumHeight(200)
        self.process = process

    def add_message(self, text: str, level: Union[int, None] = None):
        message = f"{self.time} {text}"
        item = QStandardItem(message)
        item.setEditable(False)
        if level is not None:
            item.setForeground(Status.Message.foreground(level))

        self._model.appendRow(item)
        if self._model.rowCount() > self._items_limit:
            self._model.removeRow(0)

        self.scrollToBottom()


class ChannelSettingsWindow(ConfirmableWidget):

    def _init_ui(self):
        self.setWindowTitle("OSSK | Channel settings")

        self.setFixedSize(500, 220)

        self.label_channel = QLabel(self)
        self.label_channel.setTextFormat(Qt.RichText)
        self.label_channel.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.label_channel.setOpenExternalLinks(True)

        line_alias = QLineEdit()
        line_alias.setFixedWidth(240)
        line_alias.setPlaceholderText("Сhanges display name")
        self.field_alias = Field("Channel alias", line_alias)

        box_svq = ComboBox()
        box_svq.addItems(list(AVAILABLE_STREAM_RECORD_QUALITIES.keys()))
        self.field_svq = Field("Stream video quality", box_svq)

        button_apply = QPushButton("Apply", self)
        button_apply.clicked.connect(self.confirm.emit)

        vbox = QVBoxLayout()
        vbox.addWidget(self.label_channel, alignment=Qt.AlignHCenter)
        vbox.addStretch(1)
        vbox.addLayout(self.field_alias)
        vbox.addStretch(1)
        vbox.addLayout(self.field_svq)
        vbox.addStretch(2)
        vbox.addWidget(button_apply)

        self.setLayout(vbox)

    def update_data(self, channel_name: str, alias: str, svq: str):
        """
        Triggering by ChannelsTree.action_channel_settings
        through the controller.
        """
        label_url = CHANNEL_URL_TEMPLATE.format(channel_name)
        self.label_channel.setText(
            f'<a href="{label_url}" style="color: #0f0">{label_url}</a>'
        )
        self.field_alias.widget.setText(alias)
        index_svq = self.field_svq.widget.findText(svq)
        self.field_svq.widget.setCurrentIndex(index_svq)

    def get_data(self) -> tuple[str, str, str]:
        ch_name = self.label_channel.text()
        alias = self.field_alias.widget.text()
        svq = self.field_svq.widget.currentText()
        return ch_name, alias, svq
