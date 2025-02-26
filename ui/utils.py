from typing import List

from PyQt5.QtWidgets import QApplication
from yt_dlp import SUPPORTED_BROWSERS as YTDLP_BROWSERS

from static_vars import FAKE_AGENTS


def centralize(widget):
    widget.move(
        QApplication.desktop().screen().rect().center()
        - widget.rect().center())


def get_supported_browsers() -> List[str]:
    supported_browsers = []
    for supported_browser in YTDLP_BROWSERS:
        for fake_browser in FAKE_AGENTS.browsers:
            if fake_browser.lower() == supported_browser.lower():
                supported_browsers.append(supported_browser.capitalize())
    return sorted(supported_browsers)
