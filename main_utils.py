import logging
from pathlib import Path
from subprocess import run, PIPE, STDOUT

from PyQt5.QtCore import QObject, pyqtSignal

from static_vars import StopThreads, logging_handler, FAKE_AGENTS, DB_PATH

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
        return run(cmd, stdout=PIPE, stderr=STDOUT).returncode == 0
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
    log = pyqtSignal(int, str)
    valid = pyqtSignal(bool)

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
            self.log[int, str].emit(logging.ERROR, "yt-dlp not found!")
            self.log[int, str].emit(logging.DEBUG, f"{self.ytdlp_command=}")
            self.valid.emit(False)
        elif self.ffmpeg_path is not None \
                and not check_exists_and_callable(self.ffmpeg_path):
            self.log[int, str].emit(logging.ERROR, "ffmpeg not found!")
            self.log[int, str].emit(logging.DEBUG, f"{self.ffmpeg_path=}")
            self.valid.emit(False)
        else:
            self.valid.emit(True)
