import logging
import os
import queue
from attrdict import AttrDict
import threading
from threading import RLock
from time import time

from qbittorrentui.connector import Connector
from qbittorrentui.connector import ConnectorError
from qbittorrentui.events import sync_maindata_ready
from qbittorrentui.events import update_torrent_list_now
from qbittorrentui.events import server_details_ready
from qbittorrentui.events import run_server_command

logger = logging.getLogger(__name__)

LOOP_INTERVAL = 2


class BackgroundManager(threading.Thread):
    client: Connector

    def __init__(self, main, **kw):
        super(BackgroundManager, self).__init__()
        self.stop_request = threading.Event()

        self.wake_up = threading.Event()

        self.main = main
        self.client = main.torrent_client

        # Sync MainData
        self.sync_maindata_bg = SyncMainData(self, **kw)
        self.maindata_q = queue.Queue()

        # Server Details
        self.server_details_bg = ServerDetails(self, **kw)
        self.server_details = AttrDict({'server_version': "",
                                        'api_conn_port': ""})
        self.server_preferences = AttrDict()
        self.server_details_lock = RLock()
        self.server_preferences_lock = RLock()

        # Commands
        self.commands_bg = Commands(self)
        self.command_q = queue.Queue()

        self.workers = [
            self.sync_maindata_bg,
            self.server_details_bg,
            self.commands_bg
        ]

        # signals to respond to
        update_torrent_list_now.connect(receiver=self.sync_maindata_bg.set_wake_up)
        run_server_command.connect(receiver=self.run_command)

    def run(self):
        # start workers
        for worker in self.workers:
            worker.start()

        while not self.stop_request.is_set():
            try:
                pass
            except Exception:
                pass
            finally:
                self.stop_request.wait(timeout=LOOP_INTERVAL)

        logger.info("Background manager received stop request")

        # request workers to stop
        for worker in self.workers:
            worker.stop('shutdown')
            worker.join(timeout=1)

    @staticmethod
    def create_command(func=None, func_args: dict = None):
        return dict(func=func, func_args=func_args)

    def run_command(self, *a, **kw):
        self.command_q.put(kw.get('command', ""))
        self.commands_bg.set_wake_up(a[0])

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


class Looper(threading.Thread):
    bg_man: BackgroundManager

    def __init__(self, bg_man):
        """
        Parent class for background daemons to send and receive data/commands with server

        :param bg_man:
        """
        super(Looper, self).__init__()
        self.setDaemon(daemonic=True)
        self.stop_request = threading.Event()
        self.wake_up = threading.Event()

        self.loop_interval = LOOP_INTERVAL

        self.bg_man = bg_man

    def stop(self, *a):
        self.stop_request.set()
        self.set_wake_up(*a)

    def set_wake_up(self, *a, **kw):
        try:
            sender = a[0]
        except IndexError:
            sender = 'unknown'
        logging.info("Wake up %s (from %s)" % (self.__class__.__name__, sender))
        self.wake_up.set()

    def run(self):
        while not self.stop_request.is_set():
            start_time = time()
            try:
                self.wake_up.clear()
                self._one_loop()
            except ConnectorError:
                logger.info("Looper %s could not connect to server" % self.__class__.__name__)
            except Exception:
                logger.info("Looper %s crashed" % self.__class__.__name__, exc_info=True)
            finally:
                # wait for next loop
                poll_time = time() - start_time
                if poll_time < self.loop_interval:
                    self.wake_up.wait(self.loop_interval - poll_time)

        logger.info("Exiting daemon: %s" % self.__class__.__name__)

    def _one_loop(self):
        pass


class SyncMainData(Looper):
    def __init__(self, bg_man, **kw):
        """
        Background daemon that syncs app with server

        :param bg_man:
        :param kw:
        """
        super(SyncMainData, self).__init__(bg_man)

        self.rid = 0
        self.fd_new_maindata = kw.get('fd_new_maindata', None)

    def _one_loop(self):
        logger.info("Requesting maindata (RID: %s)" % self.rid)
        start_time = time()
        md = self.bg_man.client.sync_maindata(self.rid)
        logger.info("Response for maindata took %.3f secs" % (time() - start_time))

        # if no one is listening, reset syncing just in case the next send is the first time a receiver connects
        if sync_maindata_ready.receivers:
            logger.info("Sending sync maindata")
            # sync_maindata_ready.send("client poller", md=md)
            if self.fd_new_maindata is not None:
                self.bg_man.maindata_q.put(md)
                os.write(self.fd_new_maindata, b"maindata refresh_torrent_list")
                self.rid = md.get('rid', self.rid)
            else:
                logger.info("Failed to send new maindata; no FD to send on")
        else:
            logger.info("Sync maindata reset")
            self.rid = 0


class ServerDetails(Looper):
    def __init__(self, bg_man, **kw):
        """
        Background daemon that syncs server details with app

        :param bg_man:
        :param kw:
        """
        super(ServerDetails, self).__init__(bg_man)

        self.fd_new_details = kw.get('fd_new_details', None)

    def _one_loop(self):
        logger.info("Requesting server details")
        start_time = time()
        server_version = self.bg_man.client.version()
        preferences = self.bg_man.client.preferences()
        connection_port = preferences.web_ui_port
        logger.info("Response for server details took %.3f secs" % (time() - start_time))

        self.bg_man.set_preferences(preferences)

        new_details = False
        if server_details_ready.receivers:
            if server_version != self.bg_man.get_server_details('server_version'):
                self.bg_man.set_server_detail('server_version', server_version)
                new_details = True
            if connection_port != self.bg_man.get_server_details('api_conn_port'):
                self.bg_man.set_server_detail('api_conn_port', connection_port)
                new_details = True

        if new_details:
            # just need to send "something" to trigger the signal
            os.write(self.fd_new_details, b'x')


class Commands(Looper):
    def __init__(self, bg_man):
        super(Commands, self).__init__(bg_man)

        # set a long loop interval since anything sending
        # commands should also be setting the wake alarm
        self.loop_interval = 60

    def _one_loop(self):
        logger.info("Command queue length: %s" % self.bg_man.command_q.qsize())
        ran_commands = False
        while not self.bg_man.command_q.empty():
            ran_commands = True
            try:
                command = self.bg_man.command_q.get()
                command_func = command.get('func', '')
                command_args = command.get('func_args', {})
                logger.info("Background command: %s" % command_func)
                logger.info("Background command args: %s " % command_args)
                command_func(**command_args)
            except Exception:
                logger.info("Failed to run command", exc_info=True)
        # request server sync if commands were issued
        if ran_commands:
            self.bg_man.sync_maindata_bg.set_wake_up('commands looper')
