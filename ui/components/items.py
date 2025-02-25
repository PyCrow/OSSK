from typing import Union

from PyQt5.QtGui import QStandardItem


class ChannelItem(QStandardItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.channel: str = ''


class RecordProcessItem(QStandardItem):
    def __init__(self, *args, **kwargs):
        self.pid: Union[int, None] = None
        self.finished: bool = False
        super(RecordProcessItem, self).__init__(*args, **kwargs)