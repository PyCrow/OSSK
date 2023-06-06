from pathlib import Path
from subprocess import Popen


UNKNOWN = '<UNKNOWN>'

KEY_FFMPEG = 'ffmpeg'
KEY_YTDLP = 'ytdlp'
KEY_MAX_DOWNLOADS = 'max_downloads'
KEY_SCANNER_SLEEP = 'scanner_sleep'
KEY_CHANNELS = 'channels'

KEY_CHANNEL_NAME = 'name'
KEY_CHANNEL_ALIAS = 'alias'
KEY_CHANNEL_SVQ = 'svq'

RECORD_QUALITY_TEMPLATE = 'bv*[height<={video}]+ba/b[height<={on_failed}]'

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
        self.alias: str = name
        self.svq: str = "1080"

    def stream_quality(self) -> str:
        return RECORD_QUALITY_TEMPLATE.format(
            video=self.svq, on_failed=self.svq)

    def jdump(self) -> dict:
        return {
            KEY_CHANNEL_NAME: self.name,
            KEY_CHANNEL_ALIAS: self.alias,
            KEY_CHANNEL_SVQ: self.svq,
        }
    def jload(self, data: dict):
        self.name = data[KEY_CHANNEL_NAME]
        self.alias = data[KEY_CHANNEL_ALIAS]
        self.svq = data[KEY_CHANNEL_SVQ]


class StopThreads(Exception):
    pass


class RecordProcess(Popen):
    def __init__(self, *args, **kwargs) -> None:
        self.channel: str = UNKNOWN
        super().__init__(*args, **kwargs)
