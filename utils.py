from __future__ import annotations

import json
import logging
from copy import deepcopy
from pathlib import Path
from subprocess import run, DEVNULL

from PyQt5.QtCore import QObject, pyqtSignal

from static_vars import (SETTINGS_FILE, KEYS, DEFAULT, ChannelData,
                         SettingsType, ChannelsDataType)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def is_callable(_path: str):
    cmd = _path.split()
    cmd.append('--help')
    try:
        return run(cmd, stdout=DEVNULL, stderr=DEVNULL).returncode == 0
    except (FileNotFoundError, PermissionError):
        return False
    except Exception as e:
        logger.exception(e)
        return False


def check_exists_and_callable(_path: str) -> bool:
    if Path(_path).exists() and Path(_path).is_file() and is_callable(_path):
        return True
    return False


def check_dir_exists(_path: str) -> bool:
    if Path(_path).exists() and Path(_path).is_dir():
        return True
    return False


def load_settings() -> tuple[bool, SettingsType, str]:
    loaded = False
    parsed = False
    file_not_found = False
    settings = {}
    message = "Settings loaded successfully."

    # Loading settings
    try:
        with open(SETTINGS_FILE, 'r') as conf_file:
            settings = json.load(conf_file)
        loaded = True
    except FileNotFoundError:
        file_not_found = True
        loaded = True
    except Exception as e:
        logger.error(e, exc_info=True)
        message = "Settings loading error!"

    # Soft settings validation
    settings = _parse_settings(settings)

    # Loading channels
    channels = {}
    try:
        # TODO: StreamSaver 2.0.0 will be support only dict channels
        #
        # raw_channels = settings.get(KEYS.CHANNELS, {})
        # channels: ChannelsDataType = \
        #     {channel_id: ChannelData.j_load(raw_channels[channel_id])
        #      for channel_id in raw_channels.keys()}

        # .---- Backward compatibility version ----.
        raw_channels = settings.get(KEYS.CHANNELS, None)
        if raw_channels is None:
            raw_channels = {}

        if isinstance(raw_channels, dict):
            channels: ChannelsDataType = \
                {channel_id: ChannelData.j_load(raw_channels[channel_id])
                 for channel_id in raw_channels.keys()}
        elif isinstance(raw_channels, list):
            channels: ChannelsDataType = \
                {channel_data[KEYS.CHANNEL_NAME]:
                    ChannelData.j_load(channel_data)
                 for channel_data in raw_channels}
        # ^------ Backward compatibility end ------^
        parsed = True
    except Exception as e:
        logger.error(e, exc_info=True)
        message = "Channels list parsing failed!"
    settings[KEYS.CHANNELS] = channels

    # Save if needed
    saved = True
    if file_not_found:
        saved, saver_message = save_settings(settings)
        message = " ".join((message, saver_message))
    suc: bool = loaded and parsed and saved

    return suc, settings, message


def save_settings(settings_: SettingsType) -> tuple[bool, str]:
    """ Don't worry - I'll make a deep copy. """
    suc = False
    message = "Settings saved."
    settings = deepcopy(settings_)
    try:
        settings = _parse_settings(settings)
        channels: dict[str, ChannelData] = settings[KEYS.CHANNELS]
        settings[KEYS.CHANNELS] = {ch_id: channels[ch_id].j_dump()
                                   for ch_id in channels}
        with open(SETTINGS_FILE, 'w') as conf_file:
            json.dump(settings, conf_file, indent=4)
        suc = True
    except Exception as e:
        logger.error(e, exc_info=True)
        message = "Settings saving error!"
    finally:
        return suc, message


def _parse_settings(settings: dict) -> dict:
    # Do not allow empty records path
    settings[KEYS.RECORDS_DIR] = settings.get(KEYS.RECORDS_DIR) \
                                  or DEFAULT.RECORDS_DIR
    # Do not allow empty ffmpeg path
    settings[KEYS.FFMPEG] = settings.get(KEYS.FFMPEG) or DEFAULT.FFMPEG
    # Do not allow empty yt-dlp command
    settings[KEYS.YTDLP] = settings.get(KEYS.YTDLP) or DEFAULT.YTDLP
    # Allow 0
    settings[KEYS.MAX_DOWNLOADS] = settings.get(
        KEYS.MAX_DOWNLOADS, DEFAULT.MAX_DOWNLOADS)
    # Do not allow 0
    settings[KEYS.SCANNER_SLEEP] = settings.get(
        KEYS.SCANNER_SLEEP) or DEFAULT.SCANNER_SLEEP
    # Allow 0 (kill immediately)
    settings[KEYS.PROC_TERM_TIMOUT] = settings.get(
        KEYS.PROC_TERM_TIMOUT, DEFAULT.PROC_TERM_TIMOUT)
    # Allow any bool value
    settings[KEYS.HIDE_SUC_FIN_PROC] = settings.get(
        KEYS.HIDE_SUC_FIN_PROC, DEFAULT.HIDE_SUC_FIN_PROC)
    return settings


def get_channel_dir(records_dir: str, channel_name: str) -> Path:
    """ Create channel's dir is not exist and return its path """
    channel_dir = Path(records_dir).joinpath(channel_name)
    if not channel_dir.exists():
        channel_dir.mkdir(parents=True, exist_ok=True)
    return channel_dir


class ServiceController(QObject):
    finished = pyqtSignal(bool, str)

    def __init__(self, ffmpeg_path: str = None, ytdlp_command: str = None):
        if ffmpeg_path is None and ytdlp_command is None:
            raise AttributeError("ffmpeg path and ytdlp command "
                                 "are not specified!")
        self.ffmpeg_path = ffmpeg_path
        self.ytdlp_command = ytdlp_command
        super(ServiceController, self).__init__()

    def run(self):
        if self.ytdlp_command is not None \
                and not is_callable(self.ytdlp_command):
            self.finished[bool, str].emit(False, "yt-dlp not found!")

        if self.ffmpeg_path is not None \
                and not check_exists_and_callable(self.ffmpeg_path):
            self.finished[bool, str].emit(False, "ffmpeg not found!")

        self.finished[bool, str].emit(True, "")
