from __future__ import annotations

import sys
import logging
from copy import deepcopy
from logging import DEBUG, INFO, WARNING, ERROR

from PyQt5.QtCore import QObject, QMutex, QThread, pyqtSlot
from PyQt5.QtWidgets import QApplication

from services import Master
from static_vars import (
    logging_handler,
    KEYS,
    ChannelData,
    SettingsType)
from ui.view import MainWindow, Status
from ui.dynamic_style import STYLE
from main_utils import (
    load_settings,
    save_settings,
    ServiceController)


# Threads management attributes
THREADS_LOCK = QMutex()

# Local logging config
logger = logging.getLogger()
logger.setLevel(DEBUG)
logger.addHandler(logging_handler)
DEBUG_LEVELS = {DEBUG: 'DEBUG', INFO: 'INFO',
                WARNING: 'WARNING', ERROR: 'ERROR'}


class Controller(QObject):
    def __init__(self):
        super(Controller, self).__init__()
        self._channels: dict[str, ChannelData] = {}

        # Initiate UI and services, update views settings
        self.Window = MainWindow()
        self.Master = Master(THREADS_LOCK)

        self.settings = self._load_settings(update_everywhere=False)
        self.Window.init_settings(self.settings)
        self.Master.channels = deepcopy(self._channels)

        self._srv_thread: QThread | None = None
        self._srv_controller: ServiceController | None = None

        # Connecting signals
        self._connect_ui_signals()
        self._connect_service_signals()

        # Updating services settings
        self._update_threads_settings(self.settings)

        self.Window.show()

    def _connect_ui_signals(self):
        # Settings
        self.Window.saveSettings.connect(self._save_settings)

        # Channel management
        self.Window.checkExistsChannel[str].connect(self.highlight_on_exists)
        self.Window.addChannel[str].connect(self.add_channel)
        self.Window.delChannel[str].connect(self.del_channel)
        self.Window.openChannelSettings[str].connect(
            self.open_channel_settings)
        self.Window.applyChannelSettings[tuple].connect(
            self.apply_channel_settings)

        # Service management
        self.Window.runServices[str, str].connect(self.run_services)
        self.Window.stopServices.connect(self.set_stop_services)

        # Process
        self.Window.stopProcess[int].connect(self.stop_single_process)

    def _connect_service_signals(self):
        # New message signals
        self.Master.log[int, str].connect(self.add_log_message)
        self.Master.Slave.procLog[int, str].connect(
            self.Window.log_tabs.proc_log)

        # Stream status signals
        self.Master.works[bool].connect(self.Window.update_master_enabled)
        self.Master.Slave.works[bool].connect(self.Window.update_slave_enabled)
        self.Master.Slave.streamRec[str, int, str].connect(self._stream_rec)
        self.Master.Slave.streamFinished[int].connect(self._stream_finished)
        self.Master.Slave.streamFailed[int].connect(self._stream_fail)

        # Channel status signals
        self.Master.channelOff[str].connect(self._channel_off)
        self.Master.channelLive[str].connect(self._channel_live)

        # Next scan timer signal
        self.Master.nextScanTimer[int].connect(self.Window.update_scan_timer)

    def _load_settings(
            self, update_everywhere: bool = True
    ) -> SettingsType | None:
        """
        Loading settings

        :param update_everywhere: Update services and view by loaded settings
        """
        suc, settings, message = load_settings()
        if not suc:
            self.add_log_message(ERROR, message)
        elif message:
            self.add_log_message(DEBUG, message)

        # Getting channels from settings and saving them
        self._channels = settings[KEYS.CHANNELS]

        # Update Master, Slave and views
        if update_everywhere:
            self._update_settings_everywhere(settings)
        else:
            return settings

    @pyqtSlot(dict)
    def _save_settings(self, settings: SettingsType = None):
        """
        Preparing and saving settings data
        """
        if settings is not None:
            self.settings.update(settings)

        suc, message = save_settings(self.settings)
        if not suc:
            self.add_log_message(ERROR, message)
        elif message:
            self.add_log_message(DEBUG, message)

        # Update services and views
        self._update_settings_everywhere(self.settings)

    def _update_settings_everywhere(self, settings: SettingsType):
        self._update_threads_settings(settings)
        self._update_views_settings(settings)

    def _update_threads_settings(self, settings: SettingsType):
        # There is no need to make settings deep copy.
        # All transferring data values are immutable.
        # TODO: add check for settings data is immutable.
        THREADS_LOCK.lock()
        self.Master.scanner_sleep_min = settings[KEYS.SCANNER_SLEEP_MIN]
        self.Master.Slave.records_path = settings[KEYS.RECORDS_DIR]
        self.Master.Slave.path_to_ffmpeg = settings[KEYS.FFMPEG]
        self.Master.Slave.ytdlp_command = settings[KEYS.YTDLP]
        self.Master.Slave.max_downloads = settings[KEYS.MAX_DOWNLOADS]
        self.Master.Slave.proc_term_timeout_sec = \
            settings[KEYS.PROC_TERM_TIMEOUT_SEC]
        THREADS_LOCK.unlock()
        self.add_log_message(DEBUG, "Service settings updated.")

    def _update_views_settings(self, settings: SettingsType):
        # There is no need to make settings deep copy.
        # The View should not change settings data.
        self.Window.set_common_settings_values(settings)

    @pyqtSlot(str, str)
    def run_services(self, ffmpeg_path: str, ytdlp_command: str):
        """
        Run checks for ffmpeg and yt-dlp in another thread.
        """
        # Initialize
        self._srv_thread = QThread()
        self._srv_controller = ServiceController(ffmpeg_path, ytdlp_command)
        self._srv_controller.moveToThread(self._srv_thread)

        # Connect signals
        self._srv_thread.started.connect(self._srv_controller.run)
        self._srv_controller.finished[bool, str].connect(self._real_run_master)
        self._srv_controller.finished.connect(self._srv_thread.quit)
        self._srv_controller.finished.connect(self._srv_controller.deleteLater)
        self._srv_thread.finished.connect(self._srv_thread.deleteLater)

        self._srv_thread.start()

    @pyqtSlot(bool, str)
    def _real_run_master(self, suc: bool, message: str):
        """
        Checks thread output and services, then start services.

        :param suc: Is ffmpeg and yt-dlp checks finished successfully
        :param message: Error message
        """
        if not suc:
            self.add_log_message(WARNING, message)

        if self.Master.isRunning() and self.Master.Slave.isRunning():
            self.Master.set_start_force_scan()
            return

        self.Master.start()

    @pyqtSlot()
    def set_stop_services(self):
        THREADS_LOCK.lock()
        self.Master.soft_stop()
        self.Master.Slave.soft_stop()
        THREADS_LOCK.unlock()

    @pyqtSlot(int)
    def stop_single_process(self, pid: int):
        THREADS_LOCK.lock()
        self.Master.Slave.pids_to_stop.append(pid)
        THREADS_LOCK.unlock()

    @pyqtSlot(int, str)
    def add_log_message(self, level: int, text: str):
        logger.log(level, text)
        message = f"[{DEBUG_LEVELS[level]}] {text}"
        self.Window.log_tabs.add_common_message(message, level)

    @pyqtSlot(str)
    def add_channel(self, channel_name: str):
        """ Add a channel to the monitored list """
        if not channel_name or channel_name in self._channels:
            return
        channel_data = ChannelData(channel_name)
        self._channels[channel_name] = channel_data

        # Saving settings
        self._save_settings()

        # Update Master
        THREADS_LOCK.lock()
        self.Master.channels[channel_name] = deepcopy(channel_data)
        THREADS_LOCK.unlock()

        # Update UI
        self.Window.widget_channels_tree.add_channel_item(
            channel_name, channel_data.alias)
        self.Window.add_channel_widget.field_channel.clear()

    @pyqtSlot(str)
    def del_channel(self, channel_name: str):
        """ Delete selected channel from the monitored list """
        if channel_name not in self._channels:
            return
        THREADS_LOCK.lock()
        active_channels = self.Master.Slave.get_names_of_active_channels()
        THREADS_LOCK.unlock()
        if channel_name in active_channels:
            self.add_log_message(
                WARNING,
                f"Cannot delete channel \"{channel_name}\": "
                "There are active downloads from this channel.")
            return
        del self._channels[channel_name]
        self._save_settings()

        # Update Master channel dict
        THREADS_LOCK.lock()
        self.Master.remove_channel(channel_name)
        THREADS_LOCK.unlock()

        # Update UI
        self.Window.widget_channels_tree.del_channel_item()

    @pyqtSlot(str)
    def highlight_on_exists(self, ch_name: str):
        status = STYLE.LINE_INVALID if ch_name in self._channels \
            else STYLE.LINE_VALID
        self.Window.add_channel_widget.field_channel.setStyleSheet(status)

    @pyqtSlot(str)
    def open_channel_settings(self, channel_name: str):
        if channel_name not in self._channels:
            return
        self.Window.channel_settings_window.update_data(
            channel_name,
            self._channels[channel_name].alias,
            self._channels[channel_name].svq_view()
        )
        self.Window.channel_settings_window.show()

    @pyqtSlot(tuple)
    def apply_channel_settings(self, channel_settings: tuple[str, str, str]):
        ch_name, alias, svq = channel_settings
        self._channels[ch_name].alias = alias
        self._channels[ch_name].svq = svq
        self._save_settings()
        channel_row_text = alias if alias else ch_name
        self.Window.widget_channels_tree.set_channel_alias(channel_row_text)

    @pyqtSlot(str)
    def _channel_off(self, ch_name: str):
        ch_index = list(self._channels.keys()).index(ch_name)
        self.Window.widget_channels_tree.set_channel_status(
            ch_index, Status.Channel.OFF)

    @pyqtSlot(str)
    def _channel_live(self, ch_name: str):
        ch_index = list(self._channels.keys()).index(ch_name)
        self.Window.widget_channels_tree.set_channel_status(
            ch_index, Status.Channel.LIVE)

    @pyqtSlot(str, int, str)
    def _stream_rec(self, ch_name: str, pid: int, stream_name: str):
        self.Window.log_tabs.stream_rec(pid)
        self.Window.widget_channels_tree.add_child_process_item(
            ch_name, pid, stream_name)

    @pyqtSlot(int)
    def _stream_finished(self, pid: int):
        self.Window.log_tabs.stream_finished(pid)
        self.Window.widget_channels_tree.stream_finished(pid)

    @pyqtSlot(int)
    def _stream_fail(self, pid: int):
        self.Window.log_tabs.stream_failed(pid)
        self.Window.widget_channels_tree.stream_failed(pid)


if __name__ == '__main__':
    controller = None
    e_ = None
    try:
        app = QApplication(sys.argv)
        controller = Controller()
        sys.exit(app.exec_())
    except Exception as e_:
        logger.critical(e_, exc_info=True)
    finally:
        if controller is not None:
            controller.set_stop_services()
        if e_ is not None:
            raise e_
