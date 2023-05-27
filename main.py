from __future__ import annotations

import sys
from pathlib import Path
import logging
from logging import INFO, WARNING, ERROR
from queue import Queue
from time import sleep
import subprocess

import yt_dlp
from PyQt5.QtCore import QThread, QFile, QTextStream, pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QLabel)

from ui.classes import ListChannels, LogWidget, ChannelStatus
from utils import (
    check_ffmpeg, get_list_channels, write_new_channel, remove_channel,
    get_valid_filename, datetime_now, get_channel_dir, get_ffmpeg_path)


UNKNOWN = '<UNKNOWN>'

CURRENT_PATH = Path().resolve()
RECORDS_PATH = CURRENT_PATH.joinpath('records')
LOG_FILE = CURRENT_PATH.joinpath('media_checker.log')
PATH_TO_FFMPEG = 'ffmpeg'

handler = logging.FileHandler(LOG_FILE)
handler.setLevel(logging.INFO)
handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s', "%Y-%m-%d %H:%M:%S"))
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)
DEBUG_LEVELS = {10: 'DEBUG', 20: 'INFO', 30: 'WARNING', 40: 'ERROR'}

STOP_THREADS = False


class StopThreads(Exception):
    pass


class RecordProcess(subprocess.Popen):
    def __init__(self, *args, **kwargs) -> None:
        self.channel = UNKNOWN
        super().__init__(*args, **kwargs)


def exception_handler(func):
    def _wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.exception(f"Function {func.__name__} got exception: {e}",
                             stack_info=True)
            raise e
    return _wrapper


def stop_threads():
    global STOP_THREADS
    STOP_THREADS = True


def raise_on_stop_threads(func):
    def _wrapper(*args, **kwargs):
        global STOP_THREADS
        if STOP_THREADS:
            raise StopThreads
        ret = func(*args, **kwargs)
        if STOP_THREADS:
            raise StopThreads
        return ret

    return _wrapper


class MainWindow(QWidget):
    def __init__(self):
        super(MainWindow, self).__init__()
        self._channels: list[str] = get_list_channels()
        self.Master = Master(self._channels)
        self.Master.signal_log.connect(self.add_log_message)  # noqa
        self.Master.signal_stream_in_queue.connect(self._stream_in_queue)  # noqa
        self.Master.Slave.signal_stream_recording.connect(self._stream_recording)  # noqa
        self.Master.Slave.signal_stream_finished.connect(self._stream_finished)  # noqa
        self.Master.Slave.signal_stream_failed.connect(self._stream_failed)  # noqa

        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("StreamSaver")
        self.resize(800, 600)

        self._field_new_channel = QLineEdit()
        self._field_new_channel.setPlaceholderText("Введите название канала")

        button_add_channel = QPushButton("Добавить канал")
        button_add_channel.clicked.connect(self.add_channel)  # noqa
        button_del_channel = QPushButton("Удалить канал")
        button_del_channel.clicked.connect(self.del_channel)  # noqa
        hbox_channel_buttons = QHBoxLayout()
        hbox_channel_buttons.addWidget(button_add_channel)
        hbox_channel_buttons.addWidget(button_del_channel)

        label_channels = QLabel("Отслеживаемые каналы")

        self._widget_list_channels = ListChannels()
        self._widget_list_channels.add_str_items(self._channels)

        vbox_channels_list = QVBoxLayout()
        vbox_channels_list.addWidget(self._field_new_channel)
        vbox_channels_list.addLayout(hbox_channel_buttons)
        vbox_channels_list.addWidget(label_channels, alignment=Qt.AlignHCenter)
        vbox_channels_list.addWidget(self._widget_list_channels)

        self._field_ffmpeg = QLineEdit(get_ffmpeg_path())
        self._field_ffmpeg.setPlaceholderText("Введите путь до ffmpeg")

        label_log = QLabel("Журнал событий")
        self._widget_log = LogWidget()
        vbox_log = QVBoxLayout()
        vbox_log.addWidget(self._field_ffmpeg)
        vbox_log.addWidget(label_log, alignment=Qt.AlignHCenter)
        vbox_log.addWidget(self._widget_log)

        main_hbox = QHBoxLayout()
        main_hbox.addLayout(vbox_channels_list, 1)
        main_hbox.addLayout(vbox_log, 2)

        self.start_button = QPushButton("Старт")
        self.start_button.clicked.connect(self.run_master)  # noqa
        self.stop_button = QPushButton("Остановить всё")
        self.stop_button.clicked.connect(stop_threads)  # noqa
        hbox_master_buttons = QHBoxLayout()
        hbox_master_buttons.addWidget(self.start_button)
        hbox_master_buttons.addWidget(self.stop_button)

        main_box = QVBoxLayout()
        main_box.addLayout(main_hbox)
        main_box.addLayout(hbox_master_buttons)

        self.setLayout(main_box)

        # Загрузка стиля
        rc = QFile(r'ui/stylesheet.qss')
        rc.open(QFile.ReadOnly | QFile.Text)
        stream = QTextStream(rc)
        self.setStyleSheet(stream.readAll())

    def run_master(self):
        ffmpeg_path = self._field_ffmpeg.text()
        if not check_ffmpeg(ffmpeg_path):
            self.add_log_message(WARNING, "FFmpeg не найден.")
            return

        if self.Master.isRunning():
            return

        global STOP_THREADS
        STOP_THREADS = False

        self.Master.start()

    def add_log_message(self, lvl: int, text: str):
        self._widget_log.add_message(f"[{DEBUG_LEVELS[lvl]}] {text}")
        logger.log(lvl, text)

    def add_channel(self):
        channel_name = self._field_new_channel.text()
        self._channels.append(channel_name)
        write_new_channel(channel_name)
        if channel_name not in self.Master.channels:
            self.Master.channels.append(channel_name)
        self._widget_list_channels.add_str_item(channel_name)

    def del_channel(self):
        selected_item = self._widget_list_channels.currentIndex()
        channel_name = str(selected_item.data())
        self._channels.remove(channel_name)
        remove_channel(channel_name)
        if channel_name in self.Master.channels:
            self.Master.channels.remove(channel_name)
        self._widget_list_channels.del_item_by_index(selected_item.row())

    def _stream_in_queue(self, ch_name):
        ch_index = self._channels.index(ch_name)
        self._widget_list_channels.set_stream_status(ch_index,
                                                     ChannelStatus.QUEUE)

    def _stream_recording(self, ch_name):
        ch_index = self._channels.index(ch_name)
        self._widget_list_channels.set_stream_status(ch_index,
                                                     ChannelStatus.REC)

    def _stream_finished(self, ch_name):
        ch_index = self._channels.index(ch_name)
        self._widget_list_channels.set_stream_status(ch_index,
                                                     ChannelStatus.NONE)

    def _stream_failed(self, ch_name):
        ch_index = self._channels.index(ch_name)
        self._widget_list_channels.set_stream_status(ch_index,
                                                     ChannelStatus.FAIL)


class Master(QThread):
    """
    Master:
     - run Slave
     - search for new streams
     - edit Slave's queue
    """

    signal_log = pyqtSignal(int, str)
    signal_stream_in_queue = pyqtSignal(str)

    def __init__(self, channels):
        super(Master, self).__init__()
        self.channels: list[str] = channels
        self.status: dict[str, bool] = {}
        self.Slave = Slave()
        self.Slave.signal_log.connect(self.log)  # noqa

    def log(self, level: int, text: str):
        self.signal_log.emit(level, text)    # noqa

    def run(self) -> None:
        self.log(INFO, "Проверка каналов запущена.")
        self._run_slave()

        try:
            while True:
                for channel_name in self.channels:
                    self._check_for_stream(channel_name)
                sleep(10)
        except StopThreads:
            self.log(INFO, "Проверка каналов приостановлена.")

    def _run_slave(self):
        self.Slave.start()

    def channel_status_changed(self, channel_name: str, is_online: bool):
        if (channel_name in self.status
                and self.status[channel_name] == is_online):
            return False
        self.status[channel_name] = is_online
        return True

    @raise_on_stop_threads
    @exception_handler
    def _check_for_stream(self, channel_name):
        url = f'https://www.youtube.com/c/{channel_name}/live'

        ytdl_options = {
            'quiet': True,
            'default_search': 'ytsearch',
        }

        with yt_dlp.YoutubeDL(ytdl_options) as ydl:
            try:
                info_dict = ydl.extract_info(
                    url, download=False,
                    extra_info={'quiet': True, 'verbose': False})
            except Exception as e:
                if '404' not in str(e) and channel_name not in str(e):
                    self.log(ERROR, f"<yt-dlp>: {str(e)}")
                return

        # Check channel stream is on
        if info_dict.get("is_live"):
            if self.channel_status_changed(channel_name, True):
                self.log(INFO, f"Канал {channel_name} в сети.")

            stream_title = info_dict.get('title')
            stream_data = {
                'channel_name': channel_name,
                'title': stream_title,
                'url': info_dict.get('url')  # m3u8
            }

            # Проверка готов ли Загрузчик
            # TODO: check stream_data not in self.Slave.queue
            if channel_name not in self.Slave.active_dowloading_channels:
                self.log(INFO, f"Запись канала {channel_name}"
                               " добавлена в очередь.")
                self.signal_stream_in_queue.emit(channel_name)  # noqa
                self.Slave.queue.put(stream_data, block=True)
        elif self.channel_status_changed(channel_name, False):
            self.log(INFO, f"Канал {channel_name} не в сети.")


class Slave(QThread):

    signal_log = pyqtSignal(int, str)
    signal_stream_recording = pyqtSignal(str)
    signal_stream_finished = pyqtSignal(str)
    signal_stream_failed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.active_dowloading_channels: list[str] = []
        self.queue: Queue[dict[str, str]] = Queue(-1)
        self.max_downloads: int = 2
        self.running_downloads: list[RecordProcess] = []

    def log(self, level: int, text: str):
        self.signal_log.emit(level, text)  # noqa

    def run(self):
        self.log(INFO, "Загрузчик запущен.")

        try:
            while True:
                self.check_running_downloads()
                if self.ready_to_download() and not self.queue.empty():
                    stream_data = self.queue.get()
                    self.record_stream(stream_data)
                sleep(10)
        except StopThreads:
            self.log(INFO, "Останавливаю загрузки.")
            self.stop_downloads()
            self.log(INFO, "Загрузчик остановлен.")

    @raise_on_stop_threads
    def check_running_downloads(self):

        finished = [p for p in self.running_downloads if p.poll() is not None]

        for proc in finished:
            ret_code = proc.poll()

            if ret_code == 0:
                self.signal_stream_finished.emit(proc.channel)  # noqa
                self.log(INFO, f"Загрузка[{proc.pid}] завершена успешно.")
            else:
                self.signal_stream_failed.emit(proc.channel)  # noqa
                self.log(ERROR, f"Загрузка[{proc.pid}] завершилась с ошибкой: "
                                f"{ret_code}")

                if proc.stdout:
                    self.log(ERROR, f"Процесс[{proc.pid}] вывод:")
                    for i in proc.stdout.readlines():
                        self.log(ERROR, ">>> " + i)
                if proc.stderr:
                    self.log(ERROR, f"Процесс[{proc.pid}] ошибка:")
                    for i in proc.stderr.readlines():
                        self.log(ERROR, ">>> " + i)

        self.running_downloads = [p for p in self.running_downloads
                                  if p.poll() is None]

    def ready_to_download(self) -> bool:
        if len(self.running_downloads) < self.max_downloads:
            return True
        return False

    @raise_on_stop_threads
    @exception_handler
    def record_stream(self, stream_data: dict[str, str]):
        """ Starts stream recording """

        channel_name = stream_data.get('channel_name', UNKNOWN)
        stream_title = get_valid_filename(stream_data.get('title', UNKNOWN))
        stream_url = stream_data.get('url')  # m3u8

        channel_dir = get_channel_dir(RECORDS_PATH, channel_name)
        filename = f'{datetime_now()}_{stream_title}.mp4'
        file_path = str(channel_dir.joinpath(filename))
        self.log(INFO, f"Начата запись канала {channel_name}.")

        cmd = [PATH_TO_FFMPEG, '-i', stream_url, '-codec', 'copy', file_path]
        proc = RecordProcess(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True)
        proc.channel = channel_name
        self.active_dowloading_channels.append(channel_name)
        self.running_downloads.append(proc)

        self.signal_stream_recording.emit(channel_name)  # noqa

    def stop_downloads(self):
        """ Stop all downloads """
        for proc in self.running_downloads:
            try:
                proc.terminate()
                if proc.poll() is None:
                    self.log(INFO, f"Завершение процесса {proc.pid}...")
                proc.wait(12)
            except subprocess.TimeoutExpired:
                proc.kill()
                self.log(INFO, f"Пришлось убить процесс {proc.pid} :(")


if __name__ == '__main__':
    try:
        app = QApplication(sys.argv)
        window = MainWindow()
        window.show()

        sys.exit(app.exec_())
    except Exception as e:
        logger.exception(e)
    finally:
        STOP_THREADS = True
