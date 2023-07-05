import logging
from pathlib import Path
from subprocess import Popen
from typing import Union

from PyQt5.QtCore import QThread

UNKNOWN = '<UNKNOWN>'

CURRENT_PATH = Path().resolve()
LOG_FILE = CURRENT_PATH.joinpath('stream_saver.log')
SETTINGS_FILE = CURRENT_PATH.joinpath('settings')
STYLESHEET_PATH = CURRENT_PATH.joinpath('ui').joinpath('stylesheet.qss')

FLAG_LIVE = 'live event will begin in '

# Logging config
logging_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
logging_handler.setLevel(logging.DEBUG)
logging_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s', "%Y-%m-%d %H:%M:%S"))


class KEYS:
    RECORDS_DIR = 'records_dir'
    FFMPEG = 'ffmpeg'
    YTDLP = 'ytdlp'
    MAX_DOWNLOADS = 'max_downloads'
    SCANNER_SLEEP = 'scanner_sleep'
    PROC_TERM_TIMOUT = 'proc_term_timeout'
    HIDE_SUC_FIN_PROC = 'hide_suc_fin_proc'
    CHANNELS = 'channels'

    CHANNEL_NAME = 'name'
    CHANNEL_ALIAS = 'alias'
    CHANNEL_SVQ = 'svq'


class DEFAULT:
    RECORDS_DIR = str(CURRENT_PATH.joinpath('records'))
    FFMPEG = 'ffmpeg'
    YTDLP = 'python -m yt_dlp'
    MAX_DOWNLOADS = 2
    SCANNER_SLEEP = 5
    PROC_TERM_TIMOUT = 600
    HIDE_SUC_FIN_PROC = False

    CHANNEL_ALIAS = ''
    CHANNEL_SVQ = 'best'


AVAILABLE_STREAM_RECORD_QUALITIES = {
    'best': ('-f', 'bestvideo*+bestaudio/best'),
    '1080': ('-S', 'res:1080'),
    '720': ('-S', 'res:720'),
    '480': ('-S', 'res:480'),
}


# Define classes
class ChannelData:
    """
    Channel data
     - name
     - alias (editable)
     - svq (stream video quality)
    """
    def __init__(self, name: str):
        """
        :param name: channel YouTube ID
        (https://www.youtube.com/@channel_id).
        Channel GUI alias can be changed in channel settings.
        """
        self.name: str = name
        self.alias: str = DEFAULT.CHANNEL_ALIAS
        self.__svq: str = DEFAULT.CHANNEL_SVQ

    @property
    def svq(self):
        return AVAILABLE_STREAM_RECORD_QUALITIES[self.__svq]

    @svq.setter
    def svq(self, svq: str):
        self.__svq = svq

    def svq_view(self):
        return str(self.__svq)

    def j_dump(self) -> dict:
        return {
            KEYS.CHANNEL_NAME: self.name,
            KEYS.CHANNEL_ALIAS: self.alias,
            KEYS.CHANNEL_SVQ: self.__svq,
        }

    @staticmethod
    def j_load(data: dict):
        channel = ChannelData(data.get(KEYS.CHANNEL_NAME, UNKNOWN))
        channel.alias = data.get(KEYS.CHANNEL_ALIAS, DEFAULT.CHANNEL_ALIAS)
        channel.svq = data.get(KEYS.CHANNEL_SVQ, DEFAULT.CHANNEL_SVQ)
        return channel


class StopThreads(Exception):
    pass


class SoftStoppableThread(QThread):
    """
    Has:
     1. Variable 'stop' for management
     2. Function 'raise_on_stop' to raise StopThreads
    """
    def __init__(self):
        self.__stop = False
        super().__init__()

    def run(self) -> None:
        self.__stop = False

    def soft_stop(self):
        """
        Set 'stop' = True
        """
        self.__stop = True

    def _raise_on_stop(self):
        """
        Raise StopThreads if 'stop' == True
        """
        if self.__stop:
            raise StopThreads


class RecordProcess(Popen):
    def __init__(self, *args, **kwargs) -> None:
        self.channel: str = UNKNOWN
        super().__init__(*args, **kwargs)


ChannelsDataType = dict[str, ChannelData]
SettingsType = dict[str, Union[bool, int, str, ChannelsDataType]]
UISettingsType = dict[str, Union[bool, int, str]]
