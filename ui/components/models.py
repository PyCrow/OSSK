from PyQt5.QtCore import QAbstractTableModel, Qt, QModelIndex, QVariant
from PyQt5.QtGui import QColor


class ProcStatus:
    STARTED = 0
    FINISHED = 1
    FAILED = 2

    @staticmethod
    def str(status):
        if status == ProcStatus.STARTED:
            return 'Started'
        if status == ProcStatus.FINISHED:
            return 'Finished'
        if status == ProcStatus.FAILED:
            return 'Failed'


class COL:
    CHANNEL = 0
    NAME = 1
    STATUS = 2
    PID = 3


class DownloadsModel(QAbstractTableModel):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__headers: dict[int, str] = {
            COL.CHANNEL: "Channel",
            COL.NAME: "File name",
            COL.STATUS: "Status",
            COL.PID: "PID",
        }
        self.__data: dict[int, dict] = {}

    def rowCount(self, parent=None):
        return len(self.__data)

    def columnCount(self, parent=None):
        return len(self.__headers)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        row = index.row()
        col = index.column()
        proc_data = self.__data[row]
        cell_data = proc_data[col]
        if role == Qt.DisplayRole:
            if col == COL.STATUS:
                return ProcStatus.str(cell_data)
            return cell_data
        if role == Qt.ForegroundRole:
            if proc_data[COL.STATUS] == ProcStatus.FINISHED:
                return QColor(0, 255, 0)
            if proc_data[COL.STATUS] == ProcStatus.FAILED:
                return QColor(255, 0, 0)
            return QColor(255, 255, 255)
        return QVariant()

    def setData(self, index, value, role=None):
        self.__data[index.row()][index.column()] = value
        return True

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Vertical:
            return
        if role == Qt.DisplayRole:
            return self.__headers[section]
        return QVariant()

    def add_process(self, channel: str, stream_name: str, pid: int):
        proc = {
            COL.CHANNEL: channel,
            COL.NAME: stream_name,
            COL.PID: pid,
            COL.STATUS: ProcStatus.STARTED,
        }
        row = self.rowCount()
        # FUCK, I'VE FINALLY FOUND THIS ROW MANAGEMENT !!!!
        self.beginInsertRows(QModelIndex(), row, row)
        self.__data[row] = proc
        self.endInsertRows()

    def pid(self, index: QModelIndex):
        row = index.row()
        return self.__data[row][COL.PID]

    def get_tab_data(self, index: QModelIndex) -> tuple[int, str]:
        row = index.row()
        return self.__data[row][COL.PID], self.__data[row][COL.NAME]

    def _find_process(self, pid: int):
        for row in self.__data:
            if self.__data[row][COL.PID] == pid:
                return self.__data[row]
        raise Exception("Not found PID: %s" % pid)

    def setFinished(self, pid: int):
        self._find_process(pid)[COL.STATUS] = ProcStatus.FINISHED

    def isFinished(self, index: QModelIndex):
        return self.__data[index.row()][COL.STATUS] == ProcStatus.FINISHED

    def setFailed(self, pid: int):
        self._find_process(pid)[COL.STATUS] = ProcStatus.FAILED

    def delProcess(self, index: QModelIndex):
        del self.__data[index.row()]
