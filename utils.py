from __future__ import annotations

import json
import logging
from pathlib import Path
from subprocess import run, DEVNULL

from static_vars import SETTINGS_FILE, RECORDS_PATH


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


def get_settings() -> tuple[bool, dict | None]:
    succ = False
    config = None
    try:
        with open(SETTINGS_FILE, 'r') as conf_file:
            config = json.load(conf_file)
        succ = True
    except Exception as e:
        logger.error(e, exc_info=True)
    finally:
        return succ, config


def save_settings(config: dict) -> bool:
    try:
        with open(SETTINGS_FILE, 'w') as conf_file:
            json.dump(config, conf_file, indent=4)
        return True
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


def get_channel_dir(channel_name: str) -> Path:
    """ Create channel's dir is not exist and return its path """
    channel_dir = RECORDS_PATH.joinpath(channel_name)
    if not channel_dir.exists():
        channel_dir.mkdir(parents=True, exist_ok=True)
    return channel_dir
