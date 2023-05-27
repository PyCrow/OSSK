from __future__ import annotations

from datetime import datetime
from typing import Iterable

from PyQt5.QtGui import QStandardItemModel, QStandardItem, QColor, QPalette, \
    QLinearGradient, QBrush
from PyQt5.QtWidgets import QListView, QAbstractItemView


class ChannelStatus:
    NONE = 0
    QUEUE = 1
    REC = 2
    FAIL = 3

    @staticmethod
    def color(color_id) -> QColor:
        colors = {
            0: QColor(50, 50, 50),  # NONE
            1: QColor(66, 66, 66),  # IN_QUEUE
            2: QColor('#080'),  # RECORDING
            3: QColor('#800')  # FAILED
        }
        color = colors[color_id]
        # gradient = QLinearGradient(0, 0, 0, 400)
        gradient = QLinearGradient(0, 0, 1, 0)
        gradient.setColorAt(0.0, QColor(25, 25, 25))
        gradient.setColorAt(0.85, QColor(25, 25, 25))
        gradient.setColorAt(1.0, color)

        pal = QPalette()
        pal.setBrush(QPalette.Window, QBrush(gradient))
        return pal


class ListView(QListView):

    def __init__(self):
        super().__init__()
        self._model = QStandardItemModel()
        self.setModel(self._model)
        self.setWordWrap(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

    def add_str_item(self, text: str):
        item = QStandardItem(text)
        item.setEditable(False)
        self._model.appendRow(item)

    def add_str_items(self, list_items: Iterable[str]):
        for i in list_items:
            self.add_str_item(i)

    def del_item_by_index(self, item_index: int):
        self._model.removeRow(item_index)


class ListChannels(ListView):

    def set_stream_status(self, ch_index: int, status: int):
        """ Sets channel's row color """
        color = ChannelStatus.color(status)
        # self._model.item(ch_index).setBackground(color)
        self._model.item(ch_index).setPallete(color)


class LogWidget(ListView):
    _items_limit = 500

    @property
    def time(self):
        now = datetime.now()
        return now.strftime("%H:%M:%S")

    def __init__(self):
        super().__init__()

    def add_message(self, text):
        message = f"{self.time} {text}"
        self.add_str_item(message)
        if self._model.rowCount() > self._items_limit:
            self._model.removeRow(0)
        self.scrollToBottom()
