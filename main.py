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
from PyQt5.QtCore import QObject, QMutex, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QApplication

from static_vars import (
    logging_handler,
    KEYS, DEFAULT,
    ChannelData, StopThreads, RecordProcess,
    FLAG_LIVE)
from ui.view import MainWindow, Status
from ui.dynamic_style import STYLE
from utils import (
    get_settings, save_settings,
    is_callable, check_exists_and_callable,
    get_channel_dir,
)


# Threads management attributes
GLOBAL_STOP = False
THREADS_LOCK = QMutex()

# Local logging config
logger = logging.getLogger()
logger.setLevel(DEBUG)
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


class Controller(QObject):
    def __init__(self):
        super(Controller, self).__init__()
        self._channels: dict[str, ChannelData] = {}

        self.Window = MainWindow()
        self.Master = Master(self._channels)

        self._connect_ui_signals()
        self._connect_model_signals()

        self._load_settings()

        self.Window.show()

    def _connect_ui_signals(self):
        # Settings
        self.Window.settings_window.button_apply.clicked.connect(
            self._save_settings)

        # Channel management
        self.Window.field_add_channels.textChanged[str].connect(
            self.highlight_on_exists)
        self.Window.button_add_channel.clicked.connect(self.add_channel)

        # Management buttons
        self.Window.start_button.clicked.connect(self.run_master)
        self.Window.stop_button.clicked.connect(set_stop_threads)

        # Channel tree
        self.Window.widget_channels_tree.on_click_channel_settings.triggered. \
            connect(self.open_channel_settings)
        self.Window.widget_channels_tree.on_click_delete_channel.triggered. \
            connect(self.del_channel)
        self.Window.widget_channels_tree.on_click_stop.triggered. \
            connect(self.stop_single_process)

        # Channel settings
        self.Window.channel_settings_window.button_apply.clicked.connect(
            self.clicked_apply_channel_settings)

    def _connect_model_signals(self):
        # New message signals
        self.Master.s_log[int, str].connect(self.add_log_message)
        self.Master.Slave.s_proc_log[int, str].connect(
            self.Window.log_tabs.proc_log)

        # Channel status signals
        self.Master.s_channel_off[str].connect(self._channel_off)
        self.Master.s_channel_live[str].connect(self._channel_live)

        # Next scan timer signal
        self.Master.s_next_scan_timer[int].connect(
            self.Window.update_next_scan_timer)

        # Stream status signals
        self.Master.Slave.s_stream_rec[str, int, str].connect(self._stream_rec)
        self.Master.Slave.s_stream_finished[int].connect(self._stream_finished)
        self.Master.Slave.s_stream_fail[int].connect(self._stream_fail)

    def _load_settings(self):
        """ Loading configuration """
        succ, config = get_settings()
        if not succ:
            self.add_log_message(ERROR, "Settings loading error!")
            return

        # Getting channels from config, saving them and adding to GUI
        for channel_data in config.get(KEYS.CHANNELS, {}):
            channel_name = channel_data[KEYS.CHANNEL_NAME]
            self._channels[channel_name] = ChannelData.j_load(channel_data)
            self.Window.widget_channels_tree.add_channel_item(
                channel_name,
                self._channels[channel_name].alias,
            )

        config[KEYS.FFMPEG] = config.get(KEYS.FFMPEG, DEFAULT.FFMPEG)
        config[KEYS.YTDLP] = config.get(KEYS.YTDLP, DEFAULT.YTDLP)
        config[KEYS.MAX_DOWNLOADS] = config.get(KEYS.MAX_DOWNLOADS,
                                                DEFAULT.MAX_DOWNLOADS)
        config[KEYS.SCANNER_SLEEP] = config.get(KEYS.SCANNER_SLEEP,
                                                DEFAULT.SCANNER_SLEEP)
        config[KEYS.PROC_TERM_TIMOUT] = config.get(KEYS.PROC_TERM_TIMOUT,
                                                   DEFAULT.PROC_TERM_TIMOUT)
        config[KEYS.HIDE_SUC_FIN_PROC] = config.get(KEYS.HIDE_SUC_FIN_PROC,
                                                    DEFAULT.HIDE_SUC_FIN_PROC)

        # Update Master, Slave and views
        self._update_settings_everywhere(config)

    @pyqtSlot()
    def _save_settings(self):
        """
        Saving configuration
        1. Collecting settings from UI
        2. Preparing settings data to save
        3. Saving settings
        """
        # Collecting common settings values
        settings = self.Window.get_common_settings_values()
        # Set static ffmpeg path if field is empty
        settings[KEYS.FFMPEG] = settings[KEYS.FFMPEG] or DEFAULT.FFMPEG
        # Set static ytdlp run command if field is empty
        settings[KEYS.YTDLP] = settings[KEYS.YTDLP] or DEFAULT.YTDLP
        # Convert minutes to seconds
        settings[KEYS.SCANNER_SLEEP] = settings[KEYS.SCANNER_SLEEP] * 60
        # Channels classes to list of dicts
        settings[KEYS.CHANNELS] = [i.j_dump() for i in self._channels.values()]

        suc = save_settings(settings)
        if not suc:
            self.add_log_message(ERROR, "Settings saving error!")

        # Update Master, Slave and views
        self._update_settings_everywhere(settings)

        self.add_log_message(DEBUG, "Settings updated.")

    def _update_settings_everywhere(
            self,
            settings: dict[str, str | int | list[dict] | bool]
    ):
        self._update_threads(settings)
        self._update_views(settings)

    def _update_threads(
            self,
            settings: dict[str, str | int | list[dict] | bool]
    ):
        THREADS_LOCK.lock()
        self.Master.scanner_sleep_sec = settings[KEYS.SCANNER_SLEEP]
        self.Master.Slave.max_downloads = settings[KEYS.MAX_DOWNLOADS]
        self.Master.Slave.path_to_ffmpeg = settings[KEYS.FFMPEG]
        self.Master.Slave.ytdlp_command = settings[KEYS.YTDLP]
        self.Master.Slave.proc_term_timeout = settings[KEYS.PROC_TERM_TIMOUT]
        THREADS_LOCK.unlock()

    def _update_views(
            self,
            settings: dict[str, str | int | list[dict] | bool]
    ):
        self.Window.set_common_settings_values(settings)

    @pyqtSlot()
    def run_master(self):
        ytdlp_command = self.Window.settings_window.field_ytdlp.text()
        if not is_callable(ytdlp_command):
            self.add_log_message(WARNING, "yt-dlp not found.")
            return

        ffmpeg_path = self.Window.settings_window.field_ffmpeg.text()
        if not check_exists_and_callable(ffmpeg_path):
            self.add_log_message(WARNING, "ffmpeg not found.")
            return

        if self.Master.isRunning() and self.Master.Slave.isRunning():
            self.Master.set_start_force_scan()
            return

        global GLOBAL_STOP
        GLOBAL_STOP = False

        self.Master.start()

    @pyqtSlot()
    def stop_single_process(self):
        pid = self.Window.widget_channels_tree.selected_process_id()
        THREADS_LOCK.lock()
        self.Master.Slave.pids_to_stop.append(pid)
        THREADS_LOCK.unlock()

    @pyqtSlot(int, str)
    def add_log_message(self, level: int, text: str):
        logger.log(level, text)
        message = f"[{DEBUG_LEVELS[level]}] {text}"
        self.Window.log_tabs.add_common_message(message, level)

    @pyqtSlot()
    def add_channel(self):
        """ Add a channel to the scan list """
        channel_name = self.Window.field_add_channels.text()
        if not channel_name or channel_name in self._channels:
            return
        channel_data = ChannelData(channel_name)
        self._channels[channel_name] = channel_data
        self._save_settings()
        THREADS_LOCK.lock()
        self.Master.channels[channel_name] = channel_data
        THREADS_LOCK.unlock()
        self.Window.widget_channels_tree.add_channel_item(
            channel_name, channel_data.alias)
        self.Window.field_add_channels.clear()

    @pyqtSlot()
    def del_channel(self):
        """ Delete a channel from the scan list """
        channel_name = self.Window.widget_channels_tree.selected_channel_name()
        if channel_name not in self._channels:
            return

        THREADS_LOCK.lock()
        active_channels = self.Master.Slave.get_names_of_active_channels()
        THREADS_LOCK.unlock()
        if channel_name in active_channels:
            self.add_log_message(
                WARNING,
                f"Cannot delete channel \"{channel_name}\": "
                "There are active downloads from this channel.")
            return

        del self._channels[channel_name]
        self._save_settings()
        THREADS_LOCK.lock()
        if channel_name in self.Master.channels:
            del self.Master.channels[channel_name]
        THREADS_LOCK.unlock()
        self.Window.widget_channels_tree.del_channel_item()

    @pyqtSlot(str)
    def highlight_on_exists(self, ch_name: str):
        status = STYLE.LINE_INVALID if ch_name in self._channels \
            else STYLE.LINE_VALID
        self.Window.field_add_channels.setStyleSheet(status)

    @pyqtSlot()
    def open_channel_settings(self):
        channel_name = self.Window.widget_channels_tree.selected_channel_name()
        if channel_name not in self._channels:
            return
        self.Window.channel_settings_window.update_data(
            channel_name,
            self._channels[channel_name].alias,
            self._channels[channel_name].clean_svq()
        )
        self.Window.channel_settings_window.show()

    @pyqtSlot()
    def clicked_apply_channel_settings(self):
        ch_name, alias, svq = self.Window.channel_settings_window.get_data()
        self._channels[ch_name].alias = alias
        self._channels[ch_name].set_svq(svq)
        self._save_settings()
        channel_row_text = alias if alias else ch_name
        self.Window.widget_channels_tree.set_channel_alias(channel_row_text)

    @pyqtSlot(str)
    def _channel_off(self, ch_name: str):
        ch_index = list(self._channels.keys()).index(ch_name)
        self.Window.widget_channels_tree.set_channel_status(
            ch_index, Status.Channel.OFF)

    @pyqtSlot(str)
    def _channel_live(self, ch_name: str):
        ch_index = list(self._channels.keys()).index(ch_name)
        self.Window.widget_channels_tree.set_channel_status(
            ch_index, Status.Channel.LIVE)

    @pyqtSlot(str, int, str)
    def _stream_rec(self, ch_name: str, pid: int, stream_name: str):
        self.Window.log_tabs.stream_rec(pid)
        self.Window.widget_channels_tree.add_child_process_item(
            ch_name, pid, stream_name)

    @pyqtSlot(int)
    def _stream_finished(self, pid: int):
        self.Window.log_tabs.stream_finished(pid)
        self.Window.widget_channels_tree.stream_finished(pid)

    @pyqtSlot(int)
    def _stream_fail(self, pid: int):
        self.Window.log_tabs.stream_failed(pid)
        self.Window.widget_channels_tree.stream_failed(pid)


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
    s_next_scan_timer = pyqtSignal(int)

    def __init__(self, channels: dict[str, ChannelData]):
        super(Master, self).__init__()
        self._start_force_scan = False
        self.channels: dict[str, ChannelData] = channels
        self.last_status: dict[str, bool] = {}
        self.scheduled_streams: dict[str, bool] = {}
        self.scanner_sleep_sec: int = DEFAULT.SCANNER_SLEEP
        self.Slave = Slave()
        self.Slave.s_log[int, str].connect(self.log)

    def log(self, level: int, text: str):
        self.s_log[int, str].emit(level, text)

    def set_start_force_scan(self):
        self._start_force_scan = True

    def run(self) -> None:
        self.log(INFO, "Scanning channels started.")
        self.Slave.start()

        try:
            while True:
                raise_on_stop_threads()
                for channel_name in list(self.channels.keys()):
                    self._check_for_stream(channel_name)
                self._start_force_scan = False
                raise_on_stop_threads()

                self.wait_and_check()
        except StopThreads:
            pass
        self.log(INFO, "Scanning channels stopped.")

    def wait_and_check(self):
        """ Waiting with a check to stop """
        c = self.scanner_sleep_sec
        while c != 0 and not self._start_force_scan:
            self.s_next_scan_timer[int].emit(c)
            sleep(1)
            raise_on_stop_threads()
            c -= 1
        self.s_next_scan_timer[int].emit(c)

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
                    KEYS.CHANNEL_NAME: channel_name,
                    KEYS.CHANNEL_SVQ: self.channels[channel_name].get_svq(),
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
        self.queue: Queue[dict[str, str]] = Queue(-1)
        self.running_downloads: list[RecordProcess] = []
        self.pids_to_stop: list[int] = []
        self.temp_logs: dict[int, IO] = {}
        self.last_log_byte: dict[int, int] = {}

        self.path_to_ffmpeg: str = DEFAULT.FFMPEG
        self.ytdlp_command: str = DEFAULT.YTDLP
        self.max_downloads: int = DEFAULT.MAX_DOWNLOADS
        self.proc_term_timeout: int = DEFAULT.PROC_TERM_TIMOUT

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

    def get_names_of_active_channels(self):
        return [proc.channel for proc in self.running_downloads]

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
                                f"stopped with an error code: {ret_code}!")
            self.handle_process_finished(proc)

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

        channel_name: str = stream_data[KEYS.CHANNEL_NAME]
        stream_url: str = stream_data['url']
        records_quality: tuple = stream_data[KEYS.CHANNEL_SVQ]
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
            # Downloading from the beginning
            '--live-from-start',
            # Merge all downloaded parts into two
            # tracks (video and audio) during download
            '--no-part',
            # Update sockets when failed
            '--socket-timeout', '5',
            '--retries', '10',
            '--retry-sleep', '5',
            # No progress bar
            '--no-progress',
            # Record quality
            *records_quality,
            # Merge into one mp4 or mkv file
            '--merge-output-format', 'mp4/mkv',
            # Reducing the chance of file corruption
            # if download is interrupted
            '--hls-use-mpegts',
        ]

        proc = RecordProcess(cmd, stdout=temp_log, stderr=temp_log)
        proc.channel = channel_name
        self.last_log_byte[proc.pid] = 0
        self.temp_logs[proc.pid] = temp_log
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
                ret = proc.wait(self.proc_term_timeout)
                if ret == 0:
                    self.s_stream_finished[int].emit(proc.pid)
                else:
                    self.s_stream_fail[int].emit(proc.pid)
                    self.log(ERROR, "Error while stopping channel {} record :("
                             .format(proc.channel))
            except subprocess.TimeoutExpired:
                proc.kill()
                self.s_stream_fail[int].emit(proc.pid)
                self.log(ERROR,
                         "Recording[{}] of channel {} has been killed!".format(
                             proc.pid, proc.channel))
            finally:
                self.handle_process_finished(proc)
        self.running_downloads = []

    def handle_process_output(self, proc: RecordProcess):
        last_byte = self.last_log_byte[proc.pid]
        self.temp_logs[proc.pid].seek(last_byte)
        line = self.temp_logs[proc.pid].readline()
        if line == b'':
            return
        self.last_log_byte[proc.pid] = last_byte + len(line)
        self.s_proc_log[int, str].emit(proc.pid,
                                       line.decode('utf-8', errors='ignore'))

    def handle_process_finished(self, proc: RecordProcess):
        self.handle_process_output(proc)
        self.temp_logs[proc.pid].close()
        del self.temp_logs[proc.pid]
        del self.last_log_byte[proc.pid]


if __name__ == '__main__':
    try:
        app = QApplication(sys.argv)
        controller = Controller()

        sys.exit(app.exec_())
    except Exception as e_:
        logger.critical(e_, exc_info=True)
    finally:
        GLOBAL_STOP = True
