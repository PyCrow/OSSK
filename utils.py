import re
import json
from pathlib import Path
from datetime import datetime
from subprocess import call, DEVNULL


CONFIG_FILE = Path().resolve().joinpath('config')
CHANNELS = 'channels'


def has_ffmpeg(path_to_ffmpeg: str):
    ffmpeg = path_to_ffmpeg.split()
    ffmpeg.append('--help')
    try:
        return call(ffmpeg, stdout=DEVNULL, stderr=DEVNULL) == 0
    except FileNotFoundError:
        return False


def datetime_now():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _config(new_data: dict = None,
            rem_data: dict = None) -> dict[str, list]:
    """ Read, update and save setting """
    new = {CHANNELS: []}

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
        new[CHANNELS].append(new_data[CHANNELS])
    if rem_data:
        new[CHANNELS].remove(rem_data[CHANNELS])

    # Write config
    with open(CONFIG_FILE, 'w') as file:
        json.dump(new, file)

    return new


def write_new_channel(channel_name):
    _config(new_data={CHANNELS: channel_name})


def remove_channel(channel_name):
    _config(rem_data={CHANNELS: channel_name})


def get_list_channels():
    # TODO: add handling PermissionError
    return _config()[CHANNELS]


def get_valid_filename(text: str):
    return re.sub(r"\W", "", text)
