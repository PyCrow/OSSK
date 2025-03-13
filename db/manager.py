import logging
import sqlite3

from static_vars import DB_PATH, ChannelConfig, logging_handler

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging_handler)


def db_conn(func):
    def wrapper(*args, **kwargs):
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            res = func(conn, cur, *args, **kwargs)
            return res
    return wrapper


class DBManager:
    def __init__(self):
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute(
                'CREATE TABLE IF NOT EXISTS Channels ('
                '  pk INTEGER PRIMARY KEY AUTOINCREMENT,'
                '  url TEXT NOT NULL,'
                '  alias TEXT,'
                '  svq TEXT NOT NULL'
                ')'
            )
            conn.commit()

    def get_channels(self):
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute('SELECT * FROM Channels')
            channels = cur.fetchall()
            for channel in channels:
                print(channel)
            return channels

    def add_channel(self, channel: ChannelConfig):
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute(
                'INSERT INTO Channels (url, alias, svq) VALUES (?, ?, ?)',
                (channel.url, channel.alias, channel.svq)
            )
            conn.commit()

    def del_channel(self, pk: int):
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute('DELETE FROM Channels WHERE pk=?', (pk,))
