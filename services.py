import logging
import subprocess
import tempfile
from logging import INFO, WARNING, ERROR
from queue import Queue
from signal import SIGINT
from time import sleep
from typing import IO

import yt_dlp
from PyQt5.QtCore import pyqtSignal, QMutex

from static_vars import (SoftStoppableThread, ChannelData, StopThreads,
                         DEFAULT, FLAG_LIVE, KEYS, RecordProcess,
                         logging_handler)
from utils import get_channel_dir, logger_handler

# Local logging config
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.addHandler(logging_handler)


class Master(SoftStoppableThread):
    log = pyqtSignal(int, str)
    channelOff = pyqtSignal(str)
    channelLive = pyqtSignal(str)
    nextScanTimer = pyqtSignal(int)

    def __init__(self, threads_lock: QMutex):
        """
        Service Master:
         - run service Slave
         - search for new streams
         - edit Slave's queue
        """
        super(Master, self).__init__()
        self.MUTEX = threads_lock
        self.__start_force_scan = False
        self.channels: dict[str, ChannelData] = {}
        self.__last_status: dict[str, bool] = {}
        self.__scheduled_streams: dict[str, bool] = {}
        self.scanner_sleep_min: int = DEFAULT.SCANNER_SLEEP_MIN
        self.Slave = Slave()
        self.Slave.log[int, str].connect(self._log)

    def _log(self, level: int, text: str):
        self.log[int, str].emit(level, text)

    def remove_channel(self, channel_name: str):
        if channel_name in self.channels:
            del self.channels[channel_name]

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
            self.MUTEX.lock()
            running_downloads = [p.channel
                                 for p in self.Slave.running_downloads]
            self.MUTEX.unlock()

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
        self.proc_term_timeout_sec: int = DEFAULT.PROC_TERM_TIMEOUT_SEC

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
                ret = proc.wait(self.proc_term_timeout_sec)
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
