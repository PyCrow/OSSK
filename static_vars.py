import logging
from pathlib import Path
from subprocess import Popen


UNKNOWN = '<UNKNOWN>'

CURRENT_PATH = Path().resolve()
LOG_FILE = CURRENT_PATH.joinpath('stream_saver.log')
SETTINGS_FILE = CURRENT_PATH.joinpath('settings')
RECORDS_PATH = CURRENT_PATH.joinpath('records')
STYLESHEET_PATH = CURRENT_PATH.joinpath('ui').joinpath('stylesheet.qss')

FLAG_LIVE = 'live event will begin in '

# Logging config
logging_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
logging_handler.setLevel(logging.DEBUG)
logging_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s', "%Y-%m-%d %H:%M:%S"))


class KEYS:
    FFMPEG = 'ffmpeg'
    YTDLP = 'ytdlp'
    MAX_DOWNLOADS = 'max_downloads'
    SCANNER_SLEEP_SEC = 'scanner_sleep'
    PROC_TERM_TIMOUT = 'proc_term_timeout'
    CHANNELS = 'channels'

    CHANNEL_NAME = 'name'
    CHANNEL_ALIAS = 'alias'
    CHANNEL_SVQ = '_svq'


class DEFAULT:
    CHANNEL_ALIAS = ''
    CHANNEL_SVQ = '1080'
    MAX_DOWNLOADS = 2
    SCANNER_SLEEP_SEC = 300
    PROC_TERM_TIMOUT = 600


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
     - _svq (stream video quality)
    """
    def __init__(self, name: str):
        """
        :param name: channel YouTube ID
        (https://www.youtube.com/@channel_id).
        Channel GUI alias can be changed in channel settings.
        """
        self.name: str = name
        self.alias: str = DEFAULT.CHANNEL_ALIAS
        self._svq: str = "1080"

    def set_svq(self, svq: str):
        self._svq = svq

    def get_svq(self) -> tuple[str, str]:
        return AVAILABLE_STREAM_RECORD_QUALITIES[self._svq]

    def clean_svq(self):
        return str(self._svq)

    def j_dump(self) -> dict:
        return {
            KEYS.CHANNEL_NAME: self.name,
            KEYS.CHANNEL_ALIAS: self.alias,
            KEYS.CHANNEL_SVQ: self._svq,
        }

    @staticmethod
    def j_load(data: dict):
        channel = ChannelData(data.get(KEYS.CHANNEL_NAME, UNKNOWN))
        channel.alias = data.get(KEYS.CHANNEL_ALIAS, DEFAULT.CHANNEL_ALIAS)
        channel._svq = data.get(KEYS.CHANNEL_SVQ, DEFAULT.CHANNEL_SVQ)
        return channel


class StopThreads(Exception):
    pass


class RecordProcess(Popen):
    def __init__(self, *args, **kwargs) -> None:
        self.channel: str = UNKNOWN
        super().__init__(*args, **kwargs)
