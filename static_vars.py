from pathlib import Path
from subprocess import Popen


UNKNOWN = '<UNKNOWN>'

KEY_FFMPEG = 'ffmpeg'
KEY_YTDLP = 'ytdlp'
KEY_MAX_DOWNLOADS = 'max_downloads'
KEY_SCANNER_SLEEP = 'scanner_sleep'
KEY_CHANNELS = 'channels'

DEFAULT_MAX_DOWNLOADS = 2
DEFAULT_SCANNER_SLEEP = 300

CURRENT_PATH = Path().resolve()
LOG_FILE = CURRENT_PATH.joinpath('stream_saver.log')
SETTINGS_FILE = CURRENT_PATH.joinpath('settings')
RECORDS_PATH = CURRENT_PATH.joinpath('records')
STYLESHEET_PATH = CURRENT_PATH.joinpath('ui').joinpath('stylesheet.qss')

FLAG_LIVE = 'live event will begin in '


class StopThreads(Exception):
    pass


class RecordProcess(Popen):
    def __init__(self, *args, **kwargs) -> None:
        self.channel: str = UNKNOWN
        super().__init__(*args, **kwargs)
