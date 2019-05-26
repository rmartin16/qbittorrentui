import logging
import os
import queue
from attrdict import AttrDict
import threading
from threading import RLock
from time import time, sleep

from qbittorrentui.connector import Connector
from qbittorrentui.connector import ConnectorError
from qbittorrentui.events import sync_maindata_ready
from qbittorrentui.events import refresh_torrent_list_with_remote_data_now
from qbittorrentui.events import server_details_ready
from qbittorrentui.events import run_server_command

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2


class Poller(threading.Thread):
    client: Connector

    def __init__(self, main, **kw):
        """
        Background poller to qbittorrent.
        
        :param main:
        """
        super(Poller, self).__init__()
        self.setDaemon(daemonic=True)
        self.stop_request = threading.Event()
        self.wake_up = threading.Event()

        self.command_q = queue.Queue()

        self.main = main
        self.client = main.torrent_client

        self.rid = 0
        self.fd_new_maindata = kw.pop('fd_new_maindata', None)
        self.fd_new_details = kw.pop('fd_new_details', None)
        self.maindata_q = queue.Queue()
        self.server_details = {'server_version': "",
                               'api_conn_port': ""}
        self.server_preferences = AttrDict()
        self.server_details_lock = RLock()
        self.server_preferences_lock = RLock()

        # signals to respond to
        refresh_torrent_list_with_remote_data_now.connect(receiver=self.set_wake_up)
        run_server_command.connect(receiver=self.set_wake_up)

    def set_wake_up(self, *a, **kw):
        logging.info("Set Poller to wake up and loop (from %s)" % a[0])
        self.wake_up.set()

    def is_queues_empty(self):
        if not self.command_q.empty():
            return False
        return True

    def run(self):
        while not self.stop_request.is_set():
            start_time = time()
            try:
                # process waiting server commands
                self._run_commands()
                # retrieve server updates
                self._run_detail_fetch()
                self._run_sync_maindata_update()
            except ConnectorError:
                logger.info("Poller could not connect to request data")
            except Exception:
                logger.info("Data poller daemon crashed", exc_info=True)
            finally:
                # clear any potential alarms if queues are empty
                if self.is_queues_empty():
                    self.wake_up.clear()
                # wait for next loop
                poll_time = time() - start_time
                if poll_time < POLL_INTERVAL:
                    self.wake_up.wait(POLL_INTERVAL - poll_time)

    def _run_commands(self):
        logger.info("Command queue length: %s" % self.command_q.qsize())
        while not self.command_q.empty():
            try:
                command = self.command_q.get()
                command_func = command.get('func', '')
                command_args = command.get('func_args', {})
                logger.info("Background command: %s" % command_func)
                logger.info("Background command args: %s " % command_args)
                command_func(**command_args)
            except Exception:
                logger.info("Failed to run command", exc_info=True)

    def _run_sync_maindata_update(self):
        logger.info("Requesting maindata (RID: %s)" % self.rid)
        start_time = time()
        md = self.client.sync_maindata(self.rid)
        logger.info("Response for maindata took %.3f secs" % (time() - start_time))

        # if no one is listening, reset syncing just in case the next send is the first time a receiver connects
        if sync_maindata_ready.receivers:
            logger.info("Sending sync maindata")
            # sync_maindata_ready.send("client poller", md=md)
            if self.fd_new_maindata is not None:
                self.maindata_q.put(md)
                os.write(self.fd_new_maindata, b"maindata refresh_torrent_list")
                self.rid = md.get('rid', self.rid)
            else:
                logger.info("Failed to send new maindata; no FD to send on")
        else:
            logger.info("Sync maindata reset")
            self.rid = 0

    def get_preferences(self):
        self.server_preferences_lock.acquire()
        prefs = self.server_preferences
        self.server_preferences_lock.release()
        return prefs

    def set_preferences(self, prefs):
        self.server_preferences_lock.acquire()
        self.server_preferences = prefs
        self.server_preferences_lock.release()

    def set_server_detail(self, key, value):
        self.server_details_lock.acquire()
        self.server_details[key] = value
        self.server_details_lock.release()

    def get_server_details(self, detail=None):
        self.server_details_lock.acquire()
        details = self.server_details
        self.server_details_lock.release()
        if detail is None:
            return details
        else:
            return details.get(detail, "")

    def _run_detail_fetch(self):
        server_version = self.client.version()
        preferences = self.client.preferences()
        connection_port = preferences.web_ui_port

        self.set_preferences(preferences)

        new_details = False
        if server_details_ready.receivers:
            if server_version != self.get_server_details('server_version'):
                self.set_server_detail('server_version', server_version)
                new_details = True
            if connection_port != self.get_server_details('api_conn_port'):
                self.set_server_detail('api_conn_port', connection_port)
                new_details = True

        if new_details:
            os.write(self.fd_new_details, b'x')

