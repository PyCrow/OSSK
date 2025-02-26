import logging
from pathlib import Path
from subprocess import run, DEVNULL

from PyQt5.QtCore import QObject, pyqtSignal

from static_vars import StopThreads, logging_handler, FAKE_AGENTS

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging_handler)


def get_useragent(browser: str):
    return FAKE_AGENTS.getBrowser(browser)['useragent']


def logger_handler(func):
    def _wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if not isinstance(e, StopThreads):
                logger.exception(
                    "Function {func_name} got exception: {err}".format(
                        func_name=func.__name__, err=e),
                    stack_info=True)
            raise e
    return _wrapper


def is_callable(path: str):
    cmd = path.split()
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


def get_channel_dir(channel_name: str, records_dir: str) -> Path:
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
