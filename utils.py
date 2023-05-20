import re
import json
from pathlib import Path
from datetime import datetime
from subprocess import call, DEVNULL


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
            rem_data: dict = None) -> dict[str, list]:
    """ Read, update and save setting """
    new = {FFMPEG: 'ffmpeg', CHANNELS: []}

    Path(CONFIG_FILE).touch(0o777)
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
    if new_data:
        if CHANNELS in new_data:
            new[CHANNELS].append(rem_data[CHANNELS])
        if FFMPEG in new_data:
            new[FFMPEG] = new_data[FFMPEG]
    if rem_data:
        new[CHANNELS].remove(rem_data[CHANNELS])

    # Write config
    with open(CONFIG_FILE, 'w') as file:
        json.dump(new, file)

    return new


def update_ffmpeg_path(path_to_ffmpeg: str):
    _config(new_data={FFMPEG: path_to_ffmpeg})


def write_new_channel(channel_name: str):
    _config(new_data={CHANNELS: channel_name})


def remove_channel(channel_name: str):
    _config(rem_data={CHANNELS: channel_name})


def get_list_channels():
    # TODO: add handling PermissionError
    return _config()[CHANNELS]


def get_valid_filename(text: str):
    return re.sub(r"\W", "", text)
