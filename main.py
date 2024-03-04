from __future__ import annotations

import sys
import logging
import subprocess
import tempfile
from copy import deepcopy
from logging import DEBUG, INFO, WARNING, ERROR
from queue import Queue
from signal import SIGINT
from time import sleep
from typing import IO

import yt_dlp
from PyQt5.QtCore import QObject, QMutex, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QApplication

from static_vars import (
    logging_handler,
    KEYS, DEFAULT, FLAG_LIVE,
    SoftStoppableThread, StopThreads,
    ChannelData, RecordProcess, SettingsType)
from ui.view import MainWindow, Status
from ui.dynamic_style import STYLE
from utils import (
    load_settings, save_settings,
    ServiceController,
    get_channel_dir)


# Threads management attributes
THREADS_LOCK = QMutex()

# Local logging config
logger = logging.getLogger()
logger.setLevel(DEBUG)
logger.addHandler(logging_handler)
DEBUG_LEVELS = {DEBUG: 'DEBUG', INFO: 'INFO',
                WARNING: 'WARNING', ERROR: 'ERROR'}


def logger_handler(func):
    def _wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if not isinstance(e, StopThreads):
                logger.exception(
                    "Function {func_name} got exception: {err}".format(
                        func_name=func.__name__, err=e),
                    stack_info=True)
            raise e
    return _wrapper


class Controller(QObject):
    def __init__(self):
        super(Controller, self).__init__()
        self._channels: dict[str, ChannelData] = {}

        # Initiate UI and services, update views settings
        self.Window = MainWindow()
        self.Master = Master()

        self.settings = self._load_settings(update_everywhere=False)
        self.Window.init_settings(self.settings)
        self.Master.channels = deepcopy(self._channels)

        self._srv_thread: QThread | None = None
        self._srv_controller: ServiceController | None = None

        # Connecting signals
        self._connect_ui_signals()
        self._connect_services_signals()

        # Updating services settings
        self._update_threads_settings(self.settings)

        self.Window.show()

    def _connect_ui_signals(self):
        # Settings
        self.Window.saveSettings.connect(self._save_settings)

        # Channel management
        self.Window.checkExistsChannel[str].connect(self.highlight_on_exists)
        self.Window.addChannel[str].connect(self.add_channel)
        self.Window.delChannel[str].connect(self.del_channel)
        self.Window.openChannelSettings[str].connect(
            self.open_channel_settings)
        self.Window.applyChannelSettings[tuple].connect(
            self.apply_channel_settings)

        # Service management
        self.Window.runServices.connect(self.run_services)
        self.Window.stop_button.clicked.connect(self.set_stop_services)

        # Process
        self.Window.stopProcess[int].connect(self.stop_single_process)

    def _connect_services_signals(self):
        # New message signals
        self.Master.log[int, str].connect(self.add_log_message)
        self.Master.Slave.procLog[int, str].connect(
            self.Window.log_tabs.proc_log)

        # Channel status signals
        self.Master.channelOff[str].connect(self._channel_off)
        self.Master.channelLive[str].connect(self._channel_live)

        # Next scan timer signal
        self.Master.nextScanTimer[int].connect(
            self.Window.update_next_scan_timer)

        # Stream status signals
        self.Master.Slave.streamRec[str, int, str].connect(self._stream_rec)
        self.Master.Slave.streamFinished[int].connect(self._stream_finished)
        self.Master.Slave.streamFailed[int].connect(self._stream_fail)

    def _load_settings(
            self, update_everywhere: bool = True
    ) -> SettingsType | None:
        """
        Loading settings

        :param update_everywhere: Update services and view by loaded settings
        """
        suc, settings, message = load_settings()
        if not suc:
            self.add_log_message(ERROR, message)
        elif message:
            self.add_log_message(DEBUG, message)

        # Getting channels from settings and saving them
        self._channels = settings[KEYS.CHANNELS]

        # Update Master, Slave and views
        if update_everywhere:
            self._update_settings_everywhere(settings)
        else:
            return settings

    @pyqtSlot(dict)
    def _save_settings(self, settings: SettingsType = None):
        """
        Preparing and saving settings data
        """
        if settings is not None:
            self.settings.update(settings)

        suc, message = save_settings(self.settings)
        if not suc:
            self.add_log_message(ERROR, message)
        elif message:
            self.add_log_message(DEBUG, message)

        # Update services and views
        self._update_settings_everywhere(self.settings)

    def _update_settings_everywhere(self, settings: SettingsType):
        self._update_threads_settings(settings)
        self._update_views_settings(settings)

    def _update_threads_settings(self, settings: SettingsType):
        # There is no need to make settings deep copy.
        # All transferring data values are immutable.
        # TODO: add check for settings data is immutable.
        THREADS_LOCK.lock()
        self.Master.scanner_sleep_min = settings[KEYS.SCANNER_SLEEP]
        self.Master.Slave.records_path = settings[KEYS.RECORDS_DIR]
        self.Master.Slave.path_to_ffmpeg = settings[KEYS.FFMPEG]
        self.Master.Slave.ytdlp_command = settings[KEYS.YTDLP]
        self.Master.Slave.max_downloads = settings[KEYS.MAX_DOWNLOADS]
        self.Master.Slave.proc_term_timeout = settings[KEYS.PROC_TERM_TIMOUT]
        THREADS_LOCK.unlock()
        self.add_log_message(DEBUG, "Service settings updated.")

    def _update_views_settings(self, settings: SettingsType):
        # There is no need to make settings deep copy.
        # The View should not change settings data.
        self.Window.set_common_settings_values(settings)

    @pyqtSlot(str, str)
    def run_services(self, ffmpeg_path: str, ytdlp_command: str):
        """
        Run checks for ffmpeg and yt-dlp in another thread.
        """
        # Initialize
        self._srv_thread = QThread()
        self._srv_controller = ServiceController(ffmpeg_path, ytdlp_command)
        self._srv_controller.moveToThread(self._srv_thread)

        # Connect signals
        self._srv_thread.started.connect(self._srv_controller.run)
        self._srv_controller.finished[bool, str].connect(self._real_run_master)
        self._srv_controller.finished.connect(self._srv_thread.quit)
        self._srv_controller.finished.connect(self._srv_controller.deleteLater)
        self._srv_thread.finished.connect(self._srv_thread.deleteLater)

        self._srv_thread.start()

    @pyqtSlot(bool, str)
    def _real_run_master(self, suc: bool, message: str):
        """
        Checks thread output and services, then start services.

        :param suc: Is ffmpeg and yt-dlp checks finished successfully
        :param message: Error message
        """
        if not suc:
            self.add_log_message(WARNING, message)

        if self.Master.isRunning() and self.Master.Slave.isRunning():
            self.Master.set_start_force_scan()
            return

        self.Master.start()

    @pyqtSlot()
    def set_stop_services(self):
        THREADS_LOCK.lock()
        self.Master.soft_stop()
        self.Master.Slave.soft_stop()
        THREADS_LOCK.unlock()

    @pyqtSlot(int)
    def stop_single_process(self, pid: int):
        THREADS_LOCK.lock()
        self.Master.Slave.pids_to_stop.append(pid)
        THREADS_LOCK.unlock()

    @pyqtSlot(int, str)
    def add_log_message(self, level: int, text: str):
        logger.log(level, text)
        message = f"[{DEBUG_LEVELS[level]}] {text}"
        self.Window.log_tabs.add_common_message(message, level)

    @pyqtSlot(str)
    def add_channel(self, channel_name: str):
        """ Add a channel to the monitored list """
        if not channel_name or channel_name in self._channels:
            return
        channel_data = ChannelData(channel_name)
        self._channels[channel_name] = channel_data

        # Saving settings
        self._save_settings()

        # Update Master
        THREADS_LOCK.lock()
        self.Master.channels[channel_name] = deepcopy(channel_data)
        THREADS_LOCK.unlock()

        # Update UI
        self.Window.widget_channels_tree.add_channel_item(
            channel_name, channel_data.alias)
        self.Window.field_add_channels.clear()

    @pyqtSlot(str)
    def del_channel(self, channel_name: str):
        """ Delete selected channel from the monitored list """
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

        # Update Master channel dict
        THREADS_LOCK.lock()
        if channel_name in self.Master.channels:
            del self.Master.channels[channel_name]
        THREADS_LOCK.unlock()

        # Update UI
        self.Window.widget_channels_tree.del_channel_item()

    @pyqtSlot(str)
    def highlight_on_exists(self, ch_name: str):
        status = STYLE.LINE_INVALID if ch_name in self._channels \
            else STYLE.LINE_VALID
        self.Window.field_add_channels.setStyleSheet(status)

    @pyqtSlot(str)
    def open_channel_settings(self, channel_name: str):
        if channel_name not in self._channels:
            return
        self.Window.channel_settings_window.update_data(
            channel_name,
            self._channels[channel_name].alias,
            self._channels[channel_name].svq_view()
        )
        self.Window.channel_settings_window.show()

    @pyqtSlot(tuple)
    def apply_channel_settings(self, channel_settings: tuple[str, str, str]):
        ch_name, alias, svq = channel_settings
        self._channels[ch_name].alias = alias
        self._channels[ch_name].svq = svq
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


class Master(SoftStoppableThread):
    log = pyqtSignal(int, str)
    channelOff = pyqtSignal(str)
    channelLive = pyqtSignal(str)
    nextScanTimer = pyqtSignal(int)

    def __init__(self):
        """
        Service Master:
         - run service Slave
         - search for new streams
         - edit Slave's queue
        """
        super(Master, self).__init__()
        self.__start_force_scan = False
        self.channels: dict[str, ChannelData] = {}
        self.__last_status: dict[str, bool] = {}
        self.__scheduled_streams: dict[str, bool] = {}
        self.scanner_sleep_min: int = DEFAULT.SCANNER_SLEEP
        self.Slave = Slave()
        self.Slave.log[int, str].connect(self._log)

    def _log(self, level: int, text: str):
        self.log[int, str].emit(level, text)

    def set_start_force_scan(self):
        self.__start_force_scan = True

    def run(self) -> None:
        super(Master, self).run()
        self._log(INFO, "Scanning channels started.")
        self.Slave.start()

        try:
            while True:
                for channel_name in list(self.channels.keys()):
                    self._check_for_stream(channel_name)
                    self._raise_on_stop()
                self.__start_force_scan = False
                self._raise_on_stop()

                self.wait_and_check()
        except StopThreads:
            pass
        self._log(INFO, "Scanning channels stopped.")

    def wait_and_check(self):
        """ Waiting with a check to stop """
        # Convert minutes to seconds
        c = self.scanner_sleep_min * 60
        while c != 0 and not self.__start_force_scan:
            self.nextScanTimer[int].emit(c)
            sleep(1)
            self._raise_on_stop()
            c -= 1
        self.nextScanTimer[int].emit(c)

    def channel_status_changed(self, channel_name: str, status: bool):
        if (channel_name in self.__last_status
                and self.__last_status[channel_name] == status):
            return False
        self.__last_status[channel_name] = status
        return True

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
                self.channelOff[str].emit(channel_name)
                return
            except yt_dlp.utils.DownloadError as e:
                # Check for live flag and last status
                if (
                        FLAG_LIVE in str(e)
                        and self.__scheduled_streams.get(
                            channel_name, False) is False
                ):
                    warn = str(e)
                    leftover = warn[warn.find(FLAG_LIVE) + len(FLAG_LIVE):]
                    self._log(WARNING,
                              f"{channel_name} stream in {leftover}.")
                    self.__scheduled_streams[channel_name] = True
                self.channelOff[str].emit(channel_name)
                return
            except Exception as e:
                logger.exception(e)
                self._log(ERROR, f"<yt-dlp>: {str(e)}")
                self.channelOff[str].emit(channel_name)
                return

        # Check channel stream is on
        if info_dict.get("is_live"):
            if self.channel_status_changed(channel_name, True):
                self._log(INFO, f"Channel {channel_name} is online.")
                self.channelLive[str].emit(channel_name)

            # Check if Slave is ready
            THREADS_LOCK.lock()
            running_downloads = [p.channel
                                 for p in self.Slave.running_downloads]
            THREADS_LOCK.unlock()

            # TODO: make sending data more thread-safe
            if channel_name not in running_downloads:
                stream_data = {
                    KEYS.CHANNEL_NAME: channel_name,
                    KEYS.CHANNEL_SVQ: self.channels[channel_name].svq,
                    'url': info_dict['webpage_url'],
                    'title': info_dict['title'],
                }
                self.Slave.queue.put(stream_data, block=True)
                self._log(INFO, f"Recording {channel_name} added to queue.")

        elif self.channel_status_changed(channel_name, False):
            self._log(INFO, f"Channel {channel_name} is offline.")
            self.channelOff[str].emit(channel_name)


class Slave(SoftStoppableThread):
    # TODO: add memory check
    log = pyqtSignal(int, str)
    procLog = pyqtSignal(int, str)
    streamRec = pyqtSignal(str, int, str)
    streamFinished = pyqtSignal(int)
    streamFailed = pyqtSignal(int)

    def __init__(self):
        """
        Service Slave
        """
        super().__init__()
        self.queue: Queue[dict[str, str]] = Queue(-1)
        self.running_downloads: list[RecordProcess] = []
        self.pids_to_stop: list[int] = []
        self.temp_logs: dict[int, IO] = {}
        self.last_log_byte: dict[int, int] = {}

        self.records_path: str = DEFAULT.RECORDS_DIR
        self.path_to_ffmpeg: str = DEFAULT.FFMPEG
        self.ytdlp_command: str = DEFAULT.YTDLP
        self.max_downloads: int = DEFAULT.MAX_DOWNLOADS
        self.proc_term_timeout: int = DEFAULT.PROC_TERM_TIMOUT

    def _log(self, level: int, text: str):
        self.log[int, str].emit(level, text)

    def run(self):
        super(Slave, self).run()
        self._log(INFO, "Recorder started.")

        try:
            while True:
                self.check_running_downloads()
                self._raise_on_stop()
                while self.ready_to_download() and not self.queue.empty():
                    stream_data = self.queue.get()
                    self.record_stream(stream_data)
                self.check_pids_to_stop()
                self._raise_on_stop()
        except StopThreads:
            self.stop_downloads()
        self._log(INFO, "Recorder stopped.")

    def get_names_of_active_channels(self):
        return [proc.channel for proc in self.running_downloads]

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
                self.streamFinished[int].emit(proc.pid)
                self._log(INFO, f"Recording {proc.channel} finished.")
            else:
                self.streamFailed[int].emit(proc.pid)
                self._log(ERROR, f"Recording {proc.channel}"
                                 f" stopped with an error code: {ret_code}!")
            self.handle_process_finished(proc)

        self.running_downloads = list_running

    def ready_to_download(self) -> bool:
        # Unlimited downloads if 'max_downloads' set to 0
        if self.max_downloads == 0:
            return True
        if len(self.running_downloads) < self.max_downloads:
            return True
        return False

    @logger_handler
    def record_stream(self, stream_data: dict[str, str | tuple]):
        """ Starts stream recording """

        channel_name: str = stream_data[KEYS.CHANNEL_NAME]
        stream_url: str = stream_data['url']
        records_quality: tuple = stream_data[KEYS.CHANNEL_SVQ]
        stream_title: str = stream_data['title']

        channel_dir = str(get_channel_dir(self.records_path, channel_name))
        file_name = '%(title)s.%(ext)s'

        temp_log = tempfile.TemporaryFile(mode='w+b')

        self._log(INFO, f"Recording {channel_name} started.")

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
            '--socket-timeout', '10',
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

        proc = RecordProcess(cmd, stdout=temp_log, stderr=temp_log,
                             channel=channel_name)
        self.last_log_byte[proc.pid] = 0
        self.temp_logs[proc.pid] = temp_log
        self.running_downloads.append(proc)

        self.streamRec[str, int, str].emit(
            channel_name, proc.pid, stream_title)

    def check_pids_to_stop(self):
        if not self.pids_to_stop:
            return
        for proc in self.running_downloads:
            if proc.pid in self.pids_to_stop:
                self.pids_to_stop.remove(proc.pid)
                self.send_process_stop(proc)

    def send_process_stop(self, proc: RecordProcess):
        self._log(INFO, f"Stopping process {proc.pid}...")
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
        self._log(INFO, "Stopping records.")

        for proc in self.running_downloads:
            self.send_process_stop(proc)

        for proc in self.running_downloads:
            try:
                ret = proc.wait(self.proc_term_timeout)
                if ret == 0:
                    self.streamFinished[int].emit(proc.pid)
                else:
                    self.streamFailed[int].emit(proc.pid)
                    self._log(ERROR, f"Recording {proc.channel} stopped"
                                     f" with an error code: {ret}!")
            except subprocess.TimeoutExpired:
                proc.kill()
                self.streamFailed[int].emit(proc.pid)
                self._log(ERROR, "Recording[{}] of channel {} has been"
                                 " killed!".format(proc.pid, proc.channel))
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
        self.procLog[int, str].emit(proc.pid,
                                    line.decode('utf-8', errors='ignore'))

    def handle_process_finished(self, proc: RecordProcess):
        self.handle_process_output(proc)
        self.temp_logs[proc.pid].close()
        del self.temp_logs[proc.pid]
        del self.last_log_byte[proc.pid]


if __name__ == '__main__':
    controller = None
    try:
        app = QApplication(sys.argv)
        controller = Controller()

        sys.exit(app.exec_())
    except Exception as e_:
        print(e_)
        logger.critical(e_, exc_info=True)
    finally:
        if controller is not None:
            controller.set_stop_services()
