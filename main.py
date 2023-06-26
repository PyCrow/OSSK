from __future__ import annotations

import sys
import logging
from logging import DEBUG, INFO, WARNING, ERROR
from queue import Queue
from signal import SIGINT
from time import sleep
from typing import IO
import subprocess
import tempfile

import yt_dlp
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot, QMutex
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QLabel
)

from static_vars import (
    logging_handler,
    KEY_FFMPEG, KEY_YTDLP, KEY_CHANNELS, KEY_MAX_DOWNLOADS,
    KEY_SCANNER_SLEEP_SEC,
    DEFAULT_MAX_DOWNLOADS, DEFAULT_SCANNER_SLEEP_SEC,
    KEY_CHANNEL_NAME, KEY_CHANNEL_SVQ,
    ChannelData, StopThreads, RecordProcess,
    STYLESHEET_PATH, FLAG_LIVE)
from ui.classes import ChannelsTree, LogTabWidget, Status, \
    SettingsWindow, ChannelSettingsWindow
from ui.dynamic_style import STYLE
from utils import (
    get_settings, save_settings,
    is_callable, check_exists_and_callable,
    get_channel_dir,
)

PATH_TO_FFMPEG = ''
YTDLP_COMMAND = 'python -m yt_dlp'

# Threads management attributes
GLOBAL_STOP = False
THREADS_LOCK = QMutex()

# Local logging config
logger = logging.getLogger()
logger.addHandler(logging_handler)
DEBUG_LEVELS = {DEBUG: 'DEBUG', INFO: 'INFO',
                WARNING: 'WARNING', ERROR: 'ERROR'}


class ThreadSafeList(list):
    def __contains__(self, _obj) -> bool:
        THREADS_LOCK.lock()
        ret = super(ThreadSafeList, self).__contains__(_obj)
        THREADS_LOCK.unlock()
        return ret

    def __len__(self) -> int:
        THREADS_LOCK.lock()
        ret = super(ThreadSafeList, self).__len__()
        THREADS_LOCK.unlock()
        return ret

    def append(self, _obj) -> None:
        THREADS_LOCK.lock()
        super(ThreadSafeList, self).append(_obj)
        THREADS_LOCK.unlock()

    def pop(self, _index: int = ...):
        THREADS_LOCK.lock()
        ret = super(ThreadSafeList, self).pop(_index)
        THREADS_LOCK.unlock()
        return ret


def logger_handler(func):
    def _wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if not isinstance(e, StopThreads):
                logger.exception("Function {func_name} got exception: {err}"
                                 .format(func_name=func.__name__, err=e),
                                 stack_info=True)
            raise e

    return _wrapper


def set_stop_threads():
    global GLOBAL_STOP
    GLOBAL_STOP = True


def raise_on_stop_threads(func=None):
    def _check():
        global GLOBAL_STOP
        if GLOBAL_STOP:
            raise StopThreads

    if func is None:
        _check()
        return

    def _wrapper(*args, **kwargs):
        _check()
        ret = func(*args, **kwargs)
        _check()
        return ret

    return _wrapper


class MainWindow(QWidget):
    def __init__(self):
        super(MainWindow, self).__init__()
        self._channels: dict[str, ChannelData] = {}

        self._init_ui()
        self._load_config()

        self.Master = Master(self._channels)
        self.Master.s_log[int, str].connect(self.add_log_message)
        self.Master.s_channel_off[str].connect(self._channel_off)
        self.Master.s_channel_live[str].connect(self._channel_live)
        self.Master.Slave.s_proc_log[int, str].connect(self.log_tabs.proc_log)
        self.Master.Slave.s_stream_rec[str, int, str].connect(self._stream_rec)
        self.Master.Slave.s_stream_finished[int].connect(self._stream_finished)
        self.Master.Slave.s_stream_fail[int].connect(self._stream_fail)

    def _load_config(self):
        """ Loading configuration """
        succ, config = get_settings()
        if not succ:
            self.add_log_message(ERROR, "Settings loading error!")
            return

        # Getting channels from config, saving them and adding to GUI
        for channel_data in config.get(KEY_CHANNELS, {}):
            channel_name = channel_data[KEY_CHANNEL_NAME]
            self._channels[channel_name] = ChannelData.j_load(channel_data)
            self.widget_channels_tree.add_channel_item(
                channel_name,
                self._channels[channel_name].alias,
            )

        # (ffmpeg path will be checked on field "textChanged" signal)
        ffmpeg_value = config.get(KEY_FFMPEG, PATH_TO_FFMPEG)
        ytdlp_value = config.get(KEY_YTDLP, YTDLP_COMMAND)
        max_downloads = config.get(KEY_MAX_DOWNLOADS, DEFAULT_MAX_DOWNLOADS)
        scanner_sleep = config.get(KEY_SCANNER_SLEEP_SEC,
                                   DEFAULT_SCANNER_SLEEP_SEC)
        self.settings_window.field_ffmpeg.setText(ffmpeg_value)
        self.settings_window.field_ytdlp.setText(ytdlp_value)
        self.settings_window.box_max_downloads.setValue(max_downloads)
        self.settings_window.box_scanner_sleep.setValue(scanner_sleep // 60)

    @pyqtSlot()
    def _save_config(self):
        """ Saving configuration """
        ffmpeg_path = (self.settings_window.field_ffmpeg.text()
                       or PATH_TO_FFMPEG)
        ytdlp_command = (self.settings_window.field_ytdlp.text()
                         or YTDLP_COMMAND)
        max_downloads = self.settings_window.box_max_downloads.value()
        scanner_sleep_sec = self.settings_window.box_scanner_sleep.value() * 60

        suc = save_settings({
            KEY_FFMPEG: ffmpeg_path,
            KEY_YTDLP: ytdlp_command,
            KEY_MAX_DOWNLOADS: max_downloads,
            KEY_SCANNER_SLEEP_SEC: scanner_sleep_sec,
            KEY_CHANNELS: [i.j_dump() for i in self._channels.values()],
        })
        if not suc:
            self.add_log_message(ERROR, "Settings saving error!")

        # Edit configuration when scanning and recording in progress
        THREADS_LOCK.lock()
        self.Master.scanner_sleep_sec = scanner_sleep_sec
        self.Master.Slave.max_downloads = max_downloads
        self.Master.Slave.ytdlp_command = ytdlp_command
        THREADS_LOCK.unlock()

        self.add_log_message(INFO, "Threads settings updated.")

    def _init_ui(self):
        self.setWindowTitle("StreamSaver")
        self.resize(980, 600)

        # Settings window
        self.settings_window = SettingsWindow()
        self.settings_window.button_apply.clicked.connect(self._save_config)
        button_settings = QPushButton('Settings')
        button_settings.clicked[bool].connect(self.settings_window.show)

        self._field_add_channels = QLineEdit()
        self._field_add_channels.setPlaceholderText("Enter channel name")
        self._field_add_channels.textChanged[str].connect(
            self.highlight_on_exists)

        button_add_channel = QPushButton("Add")
        button_add_channel.clicked[bool].connect(self.add_channel)

        hbox_channels_list_header = QHBoxLayout()
        hbox_channels_list_header.addWidget(QLabel("Monitored channels"))
        hbox_channels_list_header.addWidget(button_add_channel)

        self.widget_channels_tree = ChannelsTree()
        self.widget_channels_tree.on_click_channel_settings.triggered.connect(
            self.open_channel_settings)
        self.widget_channels_tree.on_click_delete_channel.triggered.connect(
            self.del_channel)
        self.widget_channels_tree.on_click_stop.triggered.connect(
            self.stop_single_process)

        left_vbox = QVBoxLayout()
        left_vbox.addWidget(button_settings)
        left_vbox.addWidget(self._field_add_channels)
        left_vbox.addLayout(hbox_channels_list_header)
        left_vbox.addWidget(self.widget_channels_tree)

        self.log_tabs = LogTabWidget()

        main_hbox = QHBoxLayout()
        main_hbox.addLayout(left_vbox, 1)
        main_hbox.addWidget(self.log_tabs, 2)

        self.start_button = QPushButton("Start")
        self.start_button.clicked[bool].connect(self.run_master)
        self.stop_button = QPushButton("Stop all")
        self.stop_button.clicked[bool].connect(set_stop_threads)
        hbox_master_buttons = QHBoxLayout()
        hbox_master_buttons.addWidget(self.start_button)
        hbox_master_buttons.addWidget(self.stop_button)

        main_box = QVBoxLayout()
        main_box.addLayout(main_hbox)
        main_box.addLayout(hbox_master_buttons)

        self.setLayout(main_box)

        # Загрузка стиля
        style = STYLESHEET_PATH.read_text()
        self.setStyleSheet(style)
        self.settings_window.setStyleSheet(style)

        # Channel settings window
        self.channel_settings_window = ChannelSettingsWindow()
        self.channel_settings_window.button_apply.clicked.connect(
            self.clicked_apply_channel_settings)
        self.channel_settings_window.setStyleSheet(style)

    @pyqtSlot()
    def run_master(self):
        ytdlp_command = self.settings_window.field_ytdlp.text()
        if not is_callable(ytdlp_command):
            self.add_log_message(WARNING, "yt-dlp not found.")
            return

        ffmpeg_path = self.settings_window.field_ffmpeg.text()
        if not check_exists_and_callable(ffmpeg_path):
            self.add_log_message(WARNING, "ffmpeg not found.")
            return

        if self.Master.isRunning():
            return

        global GLOBAL_STOP
        GLOBAL_STOP = False

        self.Master.Slave.ytdlp_command = ytdlp_command
        self.Master.Slave.path_to_ffmpeg = ffmpeg_path
        self.Master.start()

    @pyqtSlot()
    def stop_single_process(self):
        pid = self.widget_channels_tree.selected_process_id()
        THREADS_LOCK.lock()
        self.Master.Slave.pids_to_stop.append(pid)
        THREADS_LOCK.unlock()

    @pyqtSlot(int, str)
    def add_log_message(self, level: int, text: str):
        logger.log(level, text)
        self.log_tabs.add_common_message(f"[{DEBUG_LEVELS[level]}] {text}")

    @pyqtSlot()
    def add_channel(self):
        """ Add a channel to the scan list """
        channel_name = self._field_add_channels.text()
        if not channel_name or channel_name in self._channels:
            return
        channel_data = ChannelData(channel_name)
        self._channels[channel_name] = channel_data
        self._save_config()
        THREADS_LOCK.lock()
        self.Master.channels[channel_name] = channel_data
        THREADS_LOCK.unlock()
        self.widget_channels_tree.add_channel_item(
            channel_name, channel_data.alias)
        self._field_add_channels.clear()

    @pyqtSlot()
    def del_channel(self):
        """ Delete a channel from the scan list """
        channel_name = self.widget_channels_tree.selected_channel_name()
        if channel_name not in self._channels:
            return
        del self._channels[channel_name]
        self._save_config()
        THREADS_LOCK.lock()
        if channel_name in self.Master.channels:
            del self.Master.channels[channel_name]
        THREADS_LOCK.unlock()
        self.widget_channels_tree.del_channel_item()

    @pyqtSlot(str)
    def highlight_on_exists(self, ch_name: str):
        status = STYLE.LINE_INVALID if ch_name in self._channels \
            else STYLE.LINE_VALID
        self._field_add_channels.setStyleSheet(status)

    @pyqtSlot()
    def open_channel_settings(self):
        channel_name = self.widget_channels_tree.selected_channel_name()
        if channel_name not in self._channels:
            return
        self.channel_settings_window.update_data(
            channel_name,
            self._channels[channel_name].alias,
            self._channels[channel_name].clean_svq()
        )
        self.channel_settings_window.show()

    @pyqtSlot()
    def clicked_apply_channel_settings(self):
        channel_name, alias, svq = self.channel_settings_window.get_data()
        self._channels[channel_name].alias = alias
        self._channels[channel_name].set_svq(svq)
        self._save_config()
        channel_row_text = alias if alias else channel_name
        self.widget_channels_tree.set_channel_alias(channel_row_text)

    @pyqtSlot(str)
    def _channel_off(self, ch_name: str):
        ch_index = list(self._channels.keys()).index(ch_name)
        self.widget_channels_tree.set_channel_status(ch_index,
                                                     Status.Channel.OFF)

    @pyqtSlot(str)
    def _channel_live(self, ch_name: str):
        ch_index = list(self._channels.keys()).index(ch_name)
        self.widget_channels_tree.set_channel_status(ch_index,
                                                     Status.Channel.LIVE)

    @pyqtSlot(str, int, str)
    def _stream_rec(self, ch_name: str, pid: int, stream_name: str):
        self.log_tabs.stream_rec(stream_name, pid)
        self.widget_channels_tree.add_child_process_item(ch_name, pid,
                                                         stream_name)

    @pyqtSlot(int)
    def _stream_finished(self, pid: int):
        self.log_tabs.stream_finished(pid)
        self.widget_channels_tree.stream_finished(pid)

    @pyqtSlot(int)
    def _stream_fail(self, pid: int):
        self.log_tabs.stream_failed(pid)
        self.widget_channels_tree.stream_failed(pid)


class Master(QThread):
    """
    Master:
     - run Slave
     - search for new streams
     - edit Slave's queue
    """

    s_log = pyqtSignal(int, str)
    s_channel_off = pyqtSignal(str)
    s_channel_live = pyqtSignal(str)

    def __init__(self, channels: dict[str, ChannelData]):
        super(Master, self).__init__()
        self.channels: dict[str, ChannelData] = channels
        self.last_status: dict[str, bool] = {}
        self.scheduled_streams: dict[str, bool] = {}
        self.scanner_sleep_sec: int = DEFAULT_SCANNER_SLEEP_SEC * 60
        self.Slave = Slave()
        self.Slave.s_log[int, str].connect(self.log)

    def log(self, level: int, text: str):
        self.s_log[int, str].emit(level, text)

    def run(self) -> None:
        self.log(INFO, "Scanning channels started.")
        self.Slave.start()

        try:
            while True:
                raise_on_stop_threads()
                for channel_name in list(self.channels.keys()):
                    self._check_for_stream(channel_name)
                raise_on_stop_threads()

                self.wait_and_check()
        except StopThreads:
            pass
        self.log(INFO, "Scanning channels stopped.")

    def wait_and_check(self):
        """ Waiting with a check to stop """
        c = self.scanner_sleep_sec
        while c != 0:
            sleep(1)
            raise_on_stop_threads()
            c -= 1

    def channel_status_changed(self, channel_name: str, status: bool):
        if (channel_name in self.last_status
                and self.last_status[channel_name] == status):
            return False
        self.last_status[channel_name] = status
        return True

    @raise_on_stop_threads
    @logger_handler
    def _check_for_stream(self, channel_name: str):
        url = f'https://www.youtube.com/@{channel_name}/live'
        ytdl_options = {'quiet': True, 'default_search': 'ytsearch'}

        with yt_dlp.YoutubeDL(ytdl_options) as ydl:
            try:
                info_dict: dict = ydl.extract_info(
                    url, download=False,
                    extra_info={'quiet': True, 'verbose': False})
            except yt_dlp.utils.UserNotLive:
                self.s_channel_off[str].emit(channel_name)
                return
            except yt_dlp.utils.DownloadError as e:
                # Check for live flag and last status
                if (FLAG_LIVE in str(e)
                        and self.scheduled_streams.get(channel_name,
                                                       False) is False):
                    warn = str(e)
                    leftover = warn[warn.find(FLAG_LIVE) + len(FLAG_LIVE):]
                    self.log(WARNING,
                             f"{channel_name} stream in {leftover}.")
                    self.scheduled_streams[channel_name] = True
                self.s_channel_off[str].emit(channel_name)
                return
            except Exception as e:
                logger.exception(e)
                self.log(ERROR, f"<yt-dlp>: {str(e)}")
                self.s_channel_off[str].emit(channel_name)
                return

        # Check channel stream is on
        if info_dict.get("is_live"):
            if self.channel_status_changed(channel_name, True):
                self.log(INFO, f"Channel {channel_name} is online.")
                self.s_channel_live[str].emit(channel_name)

            # Check if Slave is ready
            THREADS_LOCK.lock()
            running_downloads = [p.channel
                                 for p in self.Slave.running_downloads]
            THREADS_LOCK.unlock()

            # TODO: make sending data more thread-safe
            if channel_name not in running_downloads:
                stream_data = {
                    KEY_CHANNEL_NAME: channel_name,
                    KEY_CHANNEL_SVQ: self.channels[channel_name].get_svq(),
                    'url': info_dict['webpage_url'],
                    'title': info_dict['title'],
                }
                self.Slave.queue.put(stream_data, block=True)
                self.log(INFO, f"Recording {channel_name} added to queue.")

        elif self.channel_status_changed(channel_name, False):
            self.log(INFO, f"Channel {channel_name} is offline.")
            self.s_channel_off[str].emit(channel_name)


class Slave(QThread):
    # TODO: add memory check
    s_log = pyqtSignal(int, str)
    s_proc_log = pyqtSignal(int, str)
    s_stream_rec = pyqtSignal(str, int, str)
    s_stream_finished = pyqtSignal(int)
    s_stream_fail = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.ytdlp_command = YTDLP_COMMAND
        self.path_to_ffmpeg = PATH_TO_FFMPEG
        self.active_downloading_channels: list[str] = []
        self.queue: Queue[dict[str, str]] = Queue(-1)
        self.max_downloads: int = DEFAULT_MAX_DOWNLOADS
        self.running_downloads: list[RecordProcess] = []
        self.pids_to_stop: list[int] = []
        self.temp_logs: dict[int, IO] = {}
        self.last_log_byte: dict[int, int] = {}

    def log(self, level: int, text: str):
        self.s_log[int, str].emit(level, text)

    def run(self):
        self.log(INFO, "Recorder started.")

        try:
            while True:
                self.check_running_downloads()
                if self.ready_to_download() and not self.queue.empty():
                    stream_data = self.queue.get()
                    self.record_stream(stream_data)
                self.check_for_stop()
        except StopThreads:
            self.stop_downloads()
        self.log(INFO, "Recorder stopped.")

    @raise_on_stop_threads
    def check_running_downloads(self):

        list_running = []

        for proc in self.running_downloads:
            ret_code = proc.poll()

            # Pass if process is not finished yet
            if ret_code is None:
                self.handle_process_output(proc)
                list_running.append(proc)
                continue
            # Handling finished process
            if ret_code == 0:
                self.s_stream_finished[int].emit(proc.pid)
                self.log(INFO, f"Recording {proc.channel} finished.")
            else:
                self.s_stream_fail[int].emit(proc.pid)
                self.log(ERROR, f"Recording {proc.channel} "
                                "stopped with an error code!")
            self.handle_process_finished(proc)
            self.active_downloading_channels.remove(proc.channel)

        self.running_downloads = list_running

    def ready_to_download(self) -> bool:
        if self.max_downloads == 0:
            return True
        if len(self.running_downloads) < self.max_downloads:
            return True
        return False

    @raise_on_stop_threads
    @logger_handler
    def record_stream(self, stream_data: dict[str, str | tuple]):
        """ Starts stream recording """

        channel_name: str = stream_data[KEY_CHANNEL_NAME]
        stream_url: str = stream_data['url']
        records_quality: tuple = stream_data[KEY_CHANNEL_SVQ]
        stream_title: str = stream_data['title']

        channel_dir = str(get_channel_dir(channel_name))
        file_name = '%(title)s.%(ext)s'

        temp_log = tempfile.TemporaryFile(mode='w+b')

        self.log(INFO, f"Recording {channel_name} started.")

        cmd = self.ytdlp_command.split() + [
            stream_url,
            '-P', channel_dir,
            '-o', file_name,
            '--ffmpeg-location', self.path_to_ffmpeg,
            # Загружать с самого начала
            '--live-from-start',
            # Сразу в один файл
            '--no-part',
            # Обновить сокет при падении
            '--socket-timeout', '5',
            '--retries', '10',
            '--retry-sleep', '5',
            # Без прогресс-бара
            '--no-progress',
            # Качество записи
            *records_quality,
            # Объединить в один файл mp4 или mkv
            '--merge-output-format', 'mp4/mkv',
            # Снизить шанс поломки при форсивной остановке
            '--hls-use-mpegts',
        ]

        proc = RecordProcess(cmd, stdout=temp_log, stderr=temp_log)
        proc.channel = channel_name
        self.last_log_byte[proc.pid] = 0
        self.temp_logs[proc.pid] = temp_log
        self.active_downloading_channels.append(channel_name)
        self.running_downloads.append(proc)

        self.s_stream_rec[str, int, str].emit(
            channel_name, proc.pid, stream_title)

    def check_for_stop(self):
        if not self.pids_to_stop:
            return
        for proc in self.running_downloads:
            if proc.pid in self.pids_to_stop:
                self.pids_to_stop.remove(proc.pid)
                self.send_process_stop(proc)

    def send_process_stop(self, proc: RecordProcess):
        self.log(INFO, f"Stopping process {proc.pid}...")
        try:
            # Fixme:
            #  ValueError raises when Windows couldn't indentify SIGINT
            proc.send_signal(SIGINT)
        except ValueError:
            pass

    @logger_handler
    def stop_downloads(self):
        """ Stop all downloads """
        if not self.running_downloads:
            return
        self.log(INFO, "Stopping records.")

        for proc in self.running_downloads:
            self.send_process_stop(proc)

        for proc in self.running_downloads:
            try:
                ret = proc.wait(12)  # TODO: add value editing to settings
                if ret == 0:
                    self.s_stream_finished[int].emit(proc.pid)
                else:
                    self.s_stream_fail[int].emit(proc.pid)
                    self.log(ERROR, "Error while stopping channel {} record :("
                             .format(proc.channel))
            except subprocess.TimeoutExpired:
                proc.kill()
                self.s_stream_fail[int].emit(proc.pid)
                self.log(WARNING,
                         "Recording[{}] of channel {} has been killed!".format(
                             proc.pid, proc.channel))
            finally:
                self.handle_process_finished(proc)
        self.running_downloads = []
        self.active_downloading_channels = []

    def handle_process_output(self, proc: RecordProcess):
        last_byte = self.last_log_byte[proc.pid]
        self.temp_logs[proc.pid].seek(last_byte)
        line = self.temp_logs[proc.pid].readline()
        if line == b'':
            return
        self.last_log_byte[proc.pid] = last_byte + len(line)
        self.s_proc_log[int, str].emit(proc.pid, line.decode('utf-8'))

    def handle_process_finished(self, proc: RecordProcess):
        self.handle_process_output(proc)
        self.temp_logs[proc.pid].close()
        del self.temp_logs[proc.pid]
        del self.last_log_byte[proc.pid]


if __name__ == '__main__':
    try:
        app = QApplication(sys.argv)
        window = MainWindow()
        window.show()

        sys.exit(app.exec_())
    except Exception as e_:
        logger.exception(e_)
    finally:
        GLOBAL_STOP = True
