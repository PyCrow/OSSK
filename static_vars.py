import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from subprocess import Popen
from typing import TypedDict

from PyQt5.QtCore import QThread
from pydantic import Field
from pydantic_settings import BaseSettings

UNKNOWN = '<UNKNOWN>'

CURRENT_PATH = Path().resolve()
LOG_FILE = CURRENT_PATH.joinpath('ossk.log')
SETTINGS_FILE = CURRENT_PATH.joinpath('config.env')
STYLESHEET_PATH = CURRENT_PATH.joinpath('ui').joinpath('stylesheet.qss')

FLAG_LIVE = 'live event will begin in '

# Logging config
logging_handler = RotatingFileHandler(LOG_FILE, maxBytes=1024*1024*10,
                                      backupCount=2, encoding='utf-8')
logging_handler.setLevel(logging.DEBUG)
logging_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s', "%Y-%m-%d %H:%M:%S"))


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging_handler)


class SettingsDumper(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ChannelData):
            return obj.dump()
        return json.JSONEncoder.default(self, obj)


class SettingsLoader(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(
            self, object_hook=self.object_hook, *args, **kwargs)
    def object_hook(self, dct: dict):
        if 'channels' in dct:
            for ch_name in dct['channels'].keys():
                dct['channels'][ch_name] = \
                    ChannelData.load(dct['channels'][ch_name])
        return dct


class Settings(BaseSettings):

    records_dir: str = Field(
        default=str(CURRENT_PATH.joinpath('records')),
    )

    ffmpeg: str = Field(
        default='ffmpeg',
    )

    ytdlp: str = Field(
        default='python -m yt_dlp',
    )

    max_downloads: int = Field(
        default=2,
        ge=1,
        le=50,
    )

    scanner_sleep_min: int = Field(
        default=5,
        ge=1,
        le=60
    )

    proc_term_timeout_sec: int = Field(
        default=600,
        ge=0,
        le=3600,
    )

    hide_suc_fin_proc: bool = Field(
        default=False,
    )

    channels: dict = Field(
        default={},
    )

    use_cookies: bool = Field(
        default=True,
    )

    browser: str = Field(
        default='firefox',
    )

    @classmethod
    def load(cls) -> tuple[bool, "Settings"]:
        suc = True
        try:
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE, 'r') as conf_file:
                    settings = json.load(conf_file, cls=SettingsLoader)
                    return suc, cls(**settings)
            else:
                inst = cls()
                inst.save()
                return suc, inst
        except Exception as e:
            suc = False
            logger.error(e)
        return suc, cls()

    def save(self):
        suc = True
        settings = self.model_dump()
        try:
            with open(SETTINGS_FILE, 'w') as conf_file:
                json.dump(settings, conf_file, cls=SettingsDumper, indent=4)
        except Exception as e:
            suc = True
            logger.error(e)
        finally:
            return suc


class KEYS:
    RECORDS_DIR = 'records_dir'
    FFMPEG = 'ffmpeg'
    YTDLP = 'ytdlp'
    MAX_DOWNLOADS = 'max_downloads'
    SCANNER_SLEEP_MIN = 'scanner_sleep'
    PROC_TERM_TIMEOUT_SEC = 'proc_term_timeout_sec'
    HIDE_SUC_FIN_PROC = 'hide_suc_fin_proc'
    CHANNELS = 'channels'
    USE_COOKIES = 'use_cookies'
    BROWSER = 'browser'

    CHANNEL_NAME = 'name'
    CHANNEL_ALIAS = 'alias'
    CHANNEL_SVQ = 'svq'


class DEFAULT:
    RECORDS_DIR = str(CURRENT_PATH.joinpath('records'))
    FFMPEG = 'ffmpeg'
    YTDLP = 'python -m yt_dlp'
    MAX_DOWNLOADS = 2
    SCANNER_SLEEP_MIN = 5
    PROC_TERM_TIMEOUT_SEC = 600
    HIDE_SUC_FIN_PROC = False
    USE_COOKIES = False
    BROWSER = 'firefox'

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

    def dump(self) -> dict:
        return {
            KEYS.CHANNEL_ALIAS: self.alias,
            KEYS.CHANNEL_SVQ: self.__svq,
        }

    @staticmethod
    def load(data: dict):
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
        self.channel: str = kwargs.pop('channel')
        super().__init__(*args, **kwargs)


class ChannelDataType(TypedDict):
    name: str
    alias: str
    svq: str


class SettingsType(TypedDict):
    records_dir: str
    ffmpeg: str
    ytdlp: str
    max_downloads: int
    scanner_sleep: int
    proc_term_timeout_sec: int
    hide_suc_fin_proc: bool
    channels: dict[str, ChannelDataType]
    use_cookies: bool
    browser: str
