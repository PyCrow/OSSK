import re
import json
import logging
from pathlib import Path
from datetime import datetime
from subprocess import call, DEVNULL


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

CONFIG_FILE = Path().resolve().joinpath('config')
CHANNELS = 'channels'
FFMPEG = 'ffmpeg'


def is_ffmpeg(path_to_ffmpeg: str):
    ffmpeg = path_to_ffmpeg.split()
    ffmpeg.append('--help')
    try:
        return call(ffmpeg, stdout=DEVNULL, stderr=DEVNULL) == 0
    except (FileNotFoundError, PermissionError):
        return False


def check_ffmpeg(path_to_ffmpeg: str) -> bool:
    if not Path(path_to_ffmpeg).exists():
        return False
    if not is_ffmpeg(path_to_ffmpeg):
        return False
    update_ffmpeg_path(path_to_ffmpeg)
    return True


def datetime_now():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _config(new_data: dict = None,
            rem_data: dict = None) -> dict[str, str | list]:
    """ Read, update and save setting """
    new = {FFMPEG: 'ffmpeg', CHANNELS: []}

    try:

        # Try to read config
        with open(CONFIG_FILE, 'r') as file:
            try:
                old = json.loads(file.read())
            except Exception:
                old = new

        # Check content
        for k in new.keys():
            if k in old:
                new[k] = old[k]

        # Update data
        if new_data.get(FFMPEG):
            new[FFMPEG] = new_data[FFMPEG]
        if new_data.get(CHANNELS):
            new[CHANNELS].append(rem_data[CHANNELS])
        if rem_data and rem_data[CHANNELS] in new[CHANNELS]:
            new[CHANNELS].remove(rem_data[CHANNELS])

        # Write config
        with open(CONFIG_FILE, 'w') as file:
            json.dump(new, file)
    except Exception as e:
        logger.exception(e)

    return new


def update_ffmpeg_path(path_to_ffmpeg: str):
    _config(new_data={FFMPEG: path_to_ffmpeg})


def write_new_channel(channel_name: str):
    _config(new_data={CHANNELS: channel_name})


def remove_channel(channel_name: str):
    _config(rem_data={CHANNELS: channel_name})


def get_channel_dir(records_path: Path, channel_name: str) -> Path:
    """ Create channel's dir is not exist and return its path """
    channel_dir = records_path.joinpath(channel_name)
    if not channel_dir.exists():
        channel_dir.mkdir(parents=True, exist_ok=True)
    return channel_dir


def get_list_channels() -> list:
    # TODO: add handling PermissionError
    return _config()[CHANNELS]


def get_ffmpeg_path() -> str:
    return _config()[FFMPEG]


def get_valid_filename(text: str):
    return re.sub(r"\W", "", text)
