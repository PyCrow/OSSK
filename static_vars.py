import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from subprocess import Popen

from PyQt5.QtCore import QThread
from fake_useragent import UserAgent
from pydantic import Field
from pydantic_settings import BaseSettings


# --- Common values definition ---

PROJECT_PATH = Path().resolve()
LOG_FILE = PROJECT_PATH.joinpath('ossk.log')
SETTINGS_FILE = PROJECT_PATH.joinpath('config.json')
STYLESHEET_PATH = PROJECT_PATH.joinpath('ui').joinpath('stylesheet.qss')

FAKE_AGENTS = UserAgent(min_version=130.0, platforms='desktop')

UNKNOWN = '<UNKNOWN>'
EMPTY_ITEM = ''
CHANNEL_URL_TEMPLATE = 'https://www.youtube.com/@{}'
CHANNEL_URL_LIVE_TEMPLATE = f'{CHANNEL_URL_TEMPLATE}/live'
FLAG_LIVE = 'live event will begin in '

logging_handler = RotatingFileHandler(
    LOG_FILE, maxBytes=1024*1024*5, encoding='utf-8')
logging_handler.setLevel(logging.DEBUG)
logging_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s', "%Y-%m-%d %H:%M:%S"))


# --- Local values ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging_handler)

AVAILABLE_STREAM_RECORD_QUALITIES = {
    'Maximum': ('-f', 'bv*+ba/b'),
    # Download the best video available with the largest resolution
    # but no better than <N>p, or the best video with the smallest resolution
    # if there is no video under <N>p.
    # Resolution is determined by using the smallest dimension.
    # So this works correctly for vertical videos as well.
    '1080p': ('-S', 'res:1080'),
    '720p': ('-S', 'res:720'),
    '480p': ('-S', 'res:480'),
    '320p': ('-S', 'res:320'),
    '240p': ('-S', 'res:240'),
}


# --- Defining classes ---

class SettingsLoader(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(
            self, object_hook=self.object_hook, *args, **kwargs)
    @staticmethod
    def object_hook(dct: dict):
        if 'channels' in dct:
            for name in dct['channels'].keys():
                dct['channels'][name] = ChannelConfig(**dct['channels'][name])
        return dct


class SettingsContainer:

    def update_values(self, setting: 'Settings'):
        raise NotImplementedError


class Settings(BaseSettings):

    records_dir: str = Field(
        default=str(PROJECT_PATH.joinpath('records')),
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

    channels: dict[str, 'ChannelConfig'] = Field(
        default={},
    )

    cookies_from_browser: str = Field(
        default=EMPTY_ITEM,
    )

    fake_useragent: bool = Field(
        default=True,
    )

    @classmethod
    def load(cls) -> tuple[bool, 'Settings']:
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

    def save(self) -> bool:
        suc = True
        settings = self.model_dump()
        try:
            with open(SETTINGS_FILE, 'w') as conf_file:
                json.dump(settings, conf_file, indent=4)
        except Exception as e:
            suc = False
            logger.error(e)
        finally:
            return suc


class ChannelConfig(BaseSettings):
    alias: str = Field(default="")
    svq: str = Field(default='Maximum')

    def svq_real(self):
        return AVAILABLE_STREAM_RECORD_QUALITIES[self.svq]


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
