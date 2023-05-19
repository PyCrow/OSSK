from __future__ import annotations

import logging
from datetime import datetime

from PyQt5.QtCore import pyqtSignal, pyqtSlot, QModelIndex, Qt
from PyQt5.QtGui import (QColor, QLinearGradient, QMouseEvent,
                         QStandardItem, QStandardItemModel)
from PyQt5.QtWidgets import (QAbstractItemView, QAction, QCheckBox, QComboBox,
                             QHBoxLayout, QLabel, QLineEdit, QListView, QMenu,
                             QPushButton, QSpinBox, QTabWidget, QTreeView,
                             QVBoxLayout, QWidget)

from static_vars import (logging_handler, AVAILABLE_STREAM_RECORD_QUALITIES,
                         KEYS, RecordProcess, STYLESHEET_PATH)
from ui.dynamic_style import STYLE
from utils import check_exists_and_callable, is_callable


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


class ChannelItem(QStandardItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.channel: str = ''


class RecordProcessItem(QStandardItem):
    def __init__(self, *args, **kwargs):
        self.pid: int | None = None
        self.finished: bool = False
        super(RecordProcessItem, self).__init__(*args, **kwargs)


class MainWindow(QWidget):
    def __init__(self):
        super(MainWindow, self).__init__()
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("StreamSaver")
        self.resize(980, 600)

        # Settings window
        self.settings_window = SettingsWindow()
        button_settings = QPushButton("Настройки")
        button_settings.clicked.connect(self.settings_window.show)

        self.field_add_channels = QLineEdit()
        self.field_add_channels.setPlaceholderText("Введите название канала")

        self.button_add_channel = QPushButton("Добавить")

        hbox_channels_tree_header = QHBoxLayout()
        hbox_channels_tree_header.addWidget(QLabel("Отслеживаемые каналы"))
        hbox_channels_tree_header.addWidget(self.button_add_channel)

        self.label_next_scan_timer = QLabel("Время до сканирования")

        self.widget_channels_tree = ChannelsTree()

        left_vbox = QVBoxLayout()
        left_vbox.addWidget(button_settings)
        left_vbox.addWidget(self.field_add_channels)
        left_vbox.addLayout(hbox_channels_tree_header)
        left_vbox.addWidget(self.label_next_scan_timer,
                            alignment=Qt.AlignHCenter)
        left_vbox.addWidget(self.widget_channels_tree)

        self.log_tabs = LogTabWidget()
        self.widget_channels_tree.s_open_tab_by_pid[int, str].connect(
            self.log_tabs.open_tab_by_pid)
        self.widget_channels_tree.s_close_tab_by_pid[int].connect(
            self.log_tabs.process_hide)

        main_hbox = QHBoxLayout()
        main_hbox.addLayout(left_vbox, 1)
        main_hbox.addWidget(self.log_tabs, 2)

        self.start_button = QPushButton("Начать")
        self.stop_button = QPushButton("Остановить всё")
        hbox_master_buttons = QHBoxLayout()
        hbox_master_buttons.addWidget(self.start_button)
        hbox_master_buttons.addWidget(self.stop_button)

        main_box = QVBoxLayout()
        main_box.addLayout(main_hbox)
        main_box.addLayout(hbox_master_buttons)

        self.setLayout(main_box)

        # Style loading
        style = STYLESHEET_PATH.read_text()
        self.setStyleSheet(style)
        self.settings_window.setStyleSheet(style)

        # Channel settings window
        self.channel_settings_window = ChannelSettingsWindow()
        self.channel_settings_window.setStyleSheet(style)

    def get_common_settings_values(self) -> dict[str, str | int | list[dict]]:
        ffmpeg_path = self.settings_window.field_ffmpeg.text()
        ytdlp_command = self.settings_window.field_ytdlp.text()
        max_downloads = self.settings_window.box_max_downloads.value()
        scanner_sleep_sec = self.settings_window.box_scanner_sleep.value()
        proc_term_timeout = self.settings_window.box_proc_term_timeout.value()
        hide_suc_fin_proc = self.settings_window.box_hide_suc_fin_proc\
            .isChecked()
        return {
            KEYS.FFMPEG: ffmpeg_path,
            KEYS.YTDLP: ytdlp_command,
            KEYS.MAX_DOWNLOADS: max_downloads,
            KEYS.SCANNER_SLEEP: scanner_sleep_sec,
            KEYS.PROC_TERM_TIMOUT: proc_term_timeout,
            KEYS.HIDE_SUC_FIN_PROC: hide_suc_fin_proc,
        }

    def set_common_settings_values(self,
                                   settings: dict[str, str | int | bool]):
        self.settings_window.field_ffmpeg.setText(settings[KEYS.FFMPEG])
        self.settings_window.field_ytdlp.setText(settings[KEYS.YTDLP])
        self.settings_window.box_max_downloads.setValue(
            settings[KEYS.MAX_DOWNLOADS])
        self.settings_window.box_scanner_sleep.setValue(
            settings[KEYS.SCANNER_SLEEP])
        self.settings_window.box_proc_term_timeout.setValue(
            settings[KEYS.PROC_TERM_TIMOUT])
        self.settings_window.box_hide_suc_fin_proc.setChecked(
            settings[KEYS.HIDE_SUC_FIN_PROC])
        self.widget_channels_tree.hide_suc_fin_proc = \
            settings[KEYS.HIDE_SUC_FIN_PROC]

    @pyqtSlot(int)
    def update_next_scan_timer(self, seconds: int):
        self.label_next_scan_timer.setText(
            f"Сканирование через: {seconds} секунд")


class ListView(QListView):

    def __init__(self):
        super().__init__()
        self._model = QStandardItemModel()
        self.setModel(self._model)
        self.setWordWrap(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)


class ChannelsTree(QTreeView):
    s_open_tab_by_pid = pyqtSignal(int, str)
    s_close_tab_by_pid = pyqtSignal(int)

    def __init__(self):
        super(ChannelsTree, self).__init__()
        self.hide_suc_fin_proc = False
        self.selected_item_index: QModelIndex | None = None
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

        self.on_click_channel_settings = QAction("Настройки канала", self)
        self.on_click_delete_channel = QAction("Удалить канал", self)
        self._on_click_open_tab = QAction("Открыть вкладку", self)
        self._on_click_open_tab.triggered.connect(self._send_open_tab_by_pid)
        self.on_click_stop = QAction("Остановить процесс", self)
        self._on_click_hide_process = QAction("Скрыть процесс", self)
        self._on_click_hide_process.triggered.connect(
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
        menu.addAction(self.on_click_channel_settings)
        menu.addSeparator()
        menu.addAction(self.on_click_delete_channel)
        return menu

    def _single_process_menu(self, process_finished: bool) -> QMenu:
        menu = QMenu(self)
        menu.addAction(self._on_click_open_tab)
        menu.addSeparator()
        if not process_finished:
            menu.addAction(self.on_click_stop)
        else:
            menu.addAction(self._on_click_hide_process)
        return menu

    # Selected item functions
    def _selected_item(self) -> ChannelItem | RecordProcessItem:
        return self._model.itemFromIndex(self.selected_item_index)

    def selected_channel_name(self) -> str:
        """
        Triggering by own on_click_delete_channel through the controller
        """
        return self._selected_item().channel

    def selected_process_id(self) -> int:
        """
        Triggering by own on_click_stop through the controller
        """
        return self._selected_item().pid

    def _send_open_tab_by_pid(self):
        process_item = self._selected_item()
        stream_name = process_item.text()
        self.s_open_tab_by_pid[int, str].emit(process_item.pid, stream_name)

    # Process management
    def add_child_process_item(self, channel_name: str,
                               pid: int, stream_name: str):
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
            logger.error("Процесс не может быть скрыт: "
                         "процесс ещё не завершён.")
            return
        channel_item = process_item.parent()
        channel_item.removeRow(process_item.row())
        del self._map_pid_item[process_item.pid]
        self.s_close_tab_by_pid[int].emit(process_item.pid)

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
        self.addTab(self._common_tab, "Журнал")

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

    def __init__(self, process: RecordProcess | None = None):
        super().__init__()
        self.setMinimumWidth(460)
        self.setMinimumHeight(200)
        self.process = process

    def add_message(self, text: str, level: int | None = None):
        message = f"{self.time} {text}"
        item = QStandardItem(message)
        item.setEditable(False)
        if level is not None:
            item.setForeground(Status.Message.foreground(level))

        self._model.appendRow(item)
        if self._model.rowCount() > self._items_limit:
            self._model.removeRow(0)

        self.scrollToBottom()


class SettingsWindow(QWidget):
    def __init__(self):
        super(SettingsWindow, self).__init__()
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("StreamSaver | Настройки")
        self.setWindowModality(Qt.ApplicationModal)

        self.setMinimumSize(500, 360)
        self.setMaximumSize(550, 460)
        self.resize(500, 360)

        # Field: Path to ffmpeg
        label_ffmpeg = QLabel("Путь до ffmpeg")
        self.field_ffmpeg = QLineEdit(parent=self)
        self.field_ffmpeg.setPlaceholderText(
            "Введите путь до ffmpeg")
        self.field_ffmpeg.textChanged[str].connect(self._check_ffmpeg)
        self.field_ffmpeg.setToolTip(
            "Проверяет:\n"
            "1. Доступен ли указанный путь как файл.\n"
            "2. Вызывается ли указанный файл.\n"
            "Поле подсвечивается красным, если файл пути\n"
            " недоступен.")
        hbox_ffmpeg = QVBoxLayout()
        hbox_ffmpeg.addWidget(label_ffmpeg)
        hbox_ffmpeg.addWidget(self.field_ffmpeg)

        # Field: Command or path to yt-dlp
        label_ytdlp = QLabel("Команда или путь до yt-dlp")
        self.field_ytdlp = QLineEdit(parent=self)
        self.field_ytdlp.setPlaceholderText(
            "Введите команду или путь до yt-dlp")
        self.field_ytdlp.textChanged[str].connect(self._check_ytdlp)
        self.field_ytdlp.setToolTip(
            "Проверяет:\n"
            "1. Вызывается как команда.\n"
            "2. Доступен ли указанный путь как файл.\n"
            "3. Вызывается ли указанный файл.\n"
            "Поле подсвечивается красным, если файл пути\n"
            " недоступен.")
        hbox_ytdlp = QVBoxLayout()
        hbox_ytdlp.addWidget(label_ytdlp)
        hbox_ytdlp.addWidget(self.field_ytdlp)

        # Field: Max downloads
        label_max_downloads = QLabel("Максимальное кол-во"
                                     " одновременных загрузок")
        self.box_max_downloads = QSpinBox(self)
        self.box_max_downloads.setRange(0, 50)
        self.box_max_downloads.valueChanged[int].connect(
            self._check_max_downloads)
        self.box_max_downloads.setToolTip(
            "От 1 до 50.\n"
            "Не рекомендуется ставить значение больше 12 или 0.\n"
            "0 - без ограничений.")
        hbox_max_downloads = QHBoxLayout()
        hbox_max_downloads.addWidget(label_max_downloads)
        hbox_max_downloads.addWidget(self.box_max_downloads,
                                     alignment=Qt.AlignRight)

        # Field: Time between scans
        label_scanner_sleep = QLabel("Время между сканированиями (в минутах)")
        self.box_scanner_sleep = QSpinBox(self)
        self.box_scanner_sleep.setRange(1, 60)
        self.box_scanner_sleep.valueChanged[int].connect(
            self._check_scanner_sleep)
        self.box_scanner_sleep.setToolTip(
            "Время ожидания между сканированиями каналов (в минутах).\n"
            "От 1 до 60.\n"
            "Не рекомендуется ставить меньше 5 минут, чтобы\n"
            " YouTube не счёл сканирование за DoS атаку.")
        hbox_scanner_sleep = QHBoxLayout()
        hbox_scanner_sleep.addWidget(label_scanner_sleep)
        hbox_scanner_sleep.addWidget(self.box_scanner_sleep,
                                     alignment=Qt.AlignRight)

        # Field: Process termination timeout
        label_proc_term_timeout = QLabel("Таймер завершения процесса")
        self.box_proc_term_timeout = QSpinBox(self)
        self.box_proc_term_timeout.setRange(0, 3600)
        self.box_proc_term_timeout.valueChanged[int].connect(
            self._check_proc_term_timeout)
        self.box_proc_term_timeout.setToolTip(
            "Время ожидания завершения процесса (в секундах).\n"
            "От 0 (не ждать) до 3600 (час).\n"
            "По-умолчанию - 600.\n"
            "Когда время закончится, процесс будет убит.\n"
            "Не рекомендуется устанавливать значение меньше 20\n"
            " секунд, поскольку объединение видео- и аудио-дорожек\n"
            " долгих записей может занять много времени.")
        hbox_proc_term_timeout = QHBoxLayout()
        hbox_proc_term_timeout.addWidget(label_proc_term_timeout)
        hbox_proc_term_timeout.addWidget(self.box_proc_term_timeout,
                                         alignment=Qt.AlignRight)

        # Field: Hide successfully finished processes
        label_hide_suc_fin_proc = QLabel("Скрывать успешно "
                                         "завершённые процессы")
        self.box_hide_suc_fin_proc = QCheckBox()
        self.box_hide_suc_fin_proc.setToolTip(
            "Успешно завершённые процессы будут скрыты.")
        hbox_hide_suc_fin_proc = QHBoxLayout()
        hbox_hide_suc_fin_proc.addWidget(label_hide_suc_fin_proc)
        hbox_hide_suc_fin_proc.addWidget(self.box_hide_suc_fin_proc,
                                         alignment=Qt.AlignRight)

        self.button_apply = QPushButton("Применить", self)

        vbox = QVBoxLayout()
        vbox.addLayout(hbox_ffmpeg)
        vbox.addStretch(1)
        vbox.addLayout(hbox_ytdlp)
        vbox.addStretch(1)
        vbox.addLayout(hbox_max_downloads)
        vbox.addStretch(1)
        vbox.addLayout(hbox_scanner_sleep)
        vbox.addStretch(1)
        vbox.addLayout(hbox_proc_term_timeout)
        vbox.addStretch(1)
        vbox.addLayout(hbox_hide_suc_fin_proc)
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

    @pyqtSlot(int)
    def _check_proc_term_timeout(self, value: int):
        status = STYLE.SPIN_WARNING if value < 20 else STYLE.SPIN_VALID
        self.box_proc_term_timeout.setStyleSheet(status)


class ChannelSettingsWindow(QWidget):
    def __init__(self):
        super(ChannelSettingsWindow, self).__init__()
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("StreamSaver | Настройки канала")
        self.setWindowModality(Qt.ApplicationModal)

        self.setMinimumWidth(300)
        self.setMaximumWidth(500)
        self.setMinimumHeight(300)
        self.setMaximumHeight(500)
        self.resize(400, 300)

        self.label_channel = QLabel(self)

        self.line_alias = QLineEdit()
        self.line_alias.setPlaceholderText(
            "Введите псевдоним для канала")

        self.box_svq = QComboBox()
        self.box_svq.addItems(list(AVAILABLE_STREAM_RECORD_QUALITIES.keys()))

        self.button_apply = QPushButton("Принять", self)

        vbox = QVBoxLayout()
        vbox.addWidget(self.label_channel, alignment=Qt.AlignHCenter)
        vbox.addStretch(1)
        vbox.addWidget(QLabel("Псевдоним"))
        vbox.addWidget(self.line_alias)
        vbox.addStretch(1)
        vbox.addWidget(QLabel("Качество записи видео-потока"))
        vbox.addWidget(self.box_svq)
        vbox.addStretch(2)
        vbox.addWidget(self.button_apply)

        self.setLayout(vbox)

    def update_data(self, channel_name: str, alias: str, svq: str):
        """
        Triggering by ChannelsTree.on_click_channel_settings
        through the controller.
        """
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
