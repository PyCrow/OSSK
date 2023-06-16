from pathlib import Path
from subprocess import Popen


UNKNOWN = '<UNKNOWN>'

KEY_FFMPEG = 'ffmpeg'
KEY_YTDLP = 'ytdlp'
KEY_MAX_DOWNLOADS = 'max_downloads'
KEY_SCANNER_SLEEP = 'scanner_sleep'
KEY_CHANNELS = 'channels'

KEY_CHANNEL_NAME = 'name'
KEY_CHANNEL_ALIAS, DEFAULT_CHANNEL_ALIAS = 'alias', ''
KEY_CHANNEL_SVQ, DEFAULT_CHANNEL_SVQ = '_svq', '1080'

AVAILABLE_STREAM_RECORD_QUALITIES = {
    'best': ('-f', 'bestvideo*+bestaudio/best'),
    '1080': ('-S', 'res:1080'),
    '720': ('-S', 'res:720'),
    '480': ('-S', 'res:480'),
}

DEFAULT_MAX_DOWNLOADS = 2
DEFAULT_SCANNER_SLEEP = 300

CURRENT_PATH = Path().resolve()
LOG_FILE = CURRENT_PATH.joinpath('stream_saver.log')
SETTINGS_FILE = CURRENT_PATH.joinpath('settings')
RECORDS_PATH = CURRENT_PATH.joinpath('records')
STYLESHEET_PATH = CURRENT_PATH.joinpath('ui').joinpath('stylesheet.qss')

FLAG_LIVE = 'live event will begin in '


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
        self.alias: str = DEFAULT_CHANNEL_ALIAS
        self._svq: str = "1080"

    def set_svq(self, svq: str):
        self._svq = svq

    def get_svq(self) -> tuple[str, str]:
        return AVAILABLE_STREAM_RECORD_QUALITIES[self._svq]

    def clean_svq(self):
        return str(self._svq)

    def j_dump(self) -> dict:
        return {
            KEY_CHANNEL_NAME: self.name,
            KEY_CHANNEL_ALIAS: self.alias,
            KEY_CHANNEL_SVQ: self._svq,
        }
    @staticmethod
    def j_load(data: dict):
        channel = ChannelData(data.get(KEY_CHANNEL_NAME, UNKNOWN))
        channel.alias = data.get(KEY_CHANNEL_ALIAS, DEFAULT_CHANNEL_ALIAS)
        channel._svq = data.get(KEY_CHANNEL_SVQ, DEFAULT_CHANNEL_SVQ)
        return channel


class StopThreads(Exception):
    pass


class RecordProcess(Popen):
    def __init__(self, *args, **kwargs) -> None:
        self.channel: str = UNKNOWN
        super().__init__(*args, **kwargs)
