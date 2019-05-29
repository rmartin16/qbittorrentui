import logging
import os
import queue
from attrdict import AttrDict
import threading
from threading import RLock
from time import time
from copy import deepcopy

from qbittorrentui.events import IS_TIMING_LOGGING_ENABLED

from qbittorrentui.connector import Connector
from qbittorrentui.connector import ConnectorError
from qbittorrentui.events import server_state_changed
from qbittorrentui.events import server_torrents_changed
from qbittorrentui.events import update_torrent_list_now
from qbittorrentui.events import server_details_changed
from qbittorrentui.events import run_server_command
from qbittorrentui.events import update_ui_from_daemon

logger = logging.getLogger(__name__)

LOOP_INTERVAL = 2


class DaemonManager(threading.Thread):
    def __init__(self, torrent_client, daemon_signal_fd: int):
        super(DaemonManager, self).__init__()

        self._stop_request = threading.Event()
        self._daemon_signal_fd = daemon_signal_fd  # use os.write to send signals back to UI
        self._signal_terminator = "\n"

        ########################################
        # Create daemons and their interfaces
        #  (these interfaces MUST be thread-safe)
        ########################################
        # Sync MainData
        self.sync_maindata_d = SyncMainData(torrent_client)
        self.sync_maindata_q = self.sync_maindata_d.maindata_q

        # Sync Torrents
        self.sync_torrent_d = SyncTorrent(torrent_client)
        self.remove_sync_torrent_hash = self.sync_torrent_d.remove_sync_torrent_hash
        self.add_sync_torrent_hash = self.sync_torrent_d.add_sync_torrent_hash
        self.get_torrent_store = self.sync_torrent_d.get_torrent_store

        # Server Details
        self.server_details_d = ServerDetails(torrent_client)
        self.get_server_details = self.server_details_d.get_server_details
        self.get_server_preferences = self.server_details_d.get_server_preferences

        # Commands
        self.commands_d = Commands(torrent_client)
        self.run_command = self.commands_d.run_command

        ########################################
        # Signals
        ########################################
        update_torrent_list_now.connect(receiver=self.sync_maindata_d.set_wake_up)
        run_server_command.connect(receiver=self.run_command)
        update_ui_from_daemon.connect(receiver=self.signal_ui)

        ########################################
        # Enumerate the daemons
        ########################################
        self.workers = [
            self.sync_maindata_d,
            self.sync_torrent_d,
            self.server_details_d,
            self.commands_d
        ]

    @property
    def signal_terminator(self):
        return self._signal_terminator

    def signal_ui(self, sender, signal: str = ""):
        signal = "%s%s" % (signal, self._signal_terminator)
        if isinstance(self._daemon_signal_fd, int):
            os.write(self._daemon_signal_fd, signal.encode())
        else:
            raise Exception("Background daemon signal file descriptor is not valid")

    def stop(self):
        self._stop_request.set()

    def run(self):
        # start workers
        for worker in self.workers:
            worker.start()

        # TODO: check if any workers died and restart them
        while not self._stop_request.is_set():
            try:
                pass
            except Exception:
                pass
            finally:
                self._stop_request.wait(timeout=LOOP_INTERVAL)

        logger.info("Background manager received stop request")

        # request workers to stop
        for worker in self.workers:
            worker.stop('shutdown')
            worker.join(timeout=1)

        self.signal_ui("daemon manager", "close_pipe")
        os.close(self._daemon_signal_fd)


class Daemon(threading.Thread):
    client: Connector

    def __init__(self, torrent_client):
        """
        Base class for background daemons to send and receive data/commands with server.

        :param torrent_client:
        """
        super(Daemon, self).__init__()
        self.setDaemon(daemonic=True)
        self.stop_request = threading.Event()
        self.wake_up = threading.Event()

        self._loop_interval = LOOP_INTERVAL

        self.client = torrent_client

    def stop(self, *a):
        self.stop_request.set()
        self.set_wake_up(*a)

    def signal_ui(self, signal: str):
        # right now, this is intercepted by background manager
        update_ui_from_daemon.send("%s" % self.__class__.__name__, signal=signal)

    def set_wake_up(self, sender):
        logging.info("Waking up %s (from %s)" % (self.__class__.__name__, sender))
        self.wake_up.set()

    def run(self):
        while not self.stop_request.is_set():
            start_time = time()
            try:
                start_time = time()
                self.wake_up.clear()
                self._one_loop()
                if IS_TIMING_LOGGING_ENABLED:
                    logger.info("Daemon %s request (%.2fs)" % (self.__class__.__name__, time() - start_time))
            except ConnectorError:
                logger.info("Daemon %s could not connect to server" % self.__class__.__name__)
            except Exception:
                logger.info("Daemon %s crashed" % self.__class__.__name__, exc_info=True)
            finally:
                # wait for next loop
                poll_time = time() - start_time
                if poll_time < self._loop_interval:
                    self.wake_up.wait(self._loop_interval - poll_time)

        logger.info("Daemon %s exiting" % self.__class__.__name__)

    def _one_loop(self):
        pass


class SyncMainData(Daemon):
    def __init__(self, torrent_client):
        """
        Background daemon that syncs app with server

        :param torrent_client:
        """
        super(SyncMainData, self).__init__(torrent_client)

        self.maindata_q = queue.Queue()
        self._rid = 0

    def _one_loop(self):
        # if no one is listening, reset syncing just in case the next send is the first time a receiver connects
        # TODO: add support to remotely reset RID when there's a new listener
        #  that way I don't need to directly reference this signal here
        if server_state_changed.receivers or server_torrents_changed.receivers:
            md = self.client.sync_maindata(self._rid)
            self.maindata_q.put(md)
            self.signal_ui("sync_maindata_ready")
            # only start incrementing once everyone is listening
            if server_state_changed.receivers and server_torrents_changed.receivers:
                self._rid = md.get('_rid', 0)  # reset syncing if '_rid' is missing from response...
        else:
            logger.info("No receivers for sync maindata...")
            self._rid = 0


class SyncTorrent(Daemon):
    def __init__(self, torrent_client):
        """
        Background daemon that syncs data for Torrent Window.

        :param torrent_client:
        """
        super(SyncTorrent, self).__init__(torrent_client)

        self._rid = {}
        self._torrents_to_add_q = queue.Queue()
        self._torrents_to_remove_q = queue.Queue()
        self._torrent_hashes = list()

        self._torrent_stores = dict()
        """Structure: { hash: TorrentStore }"""
        self._torrent_store_lock = RLock()

    def _one_loop(self):
        # remove torrent stores
        while not self._torrents_to_remove_q.empty():
            torrent_hash = self._torrents_to_remove_q.get()
            if torrent_hash in self._torrent_hashes:
                self._rid.pop(torrent_hash)
                self._torrent_hashes.remove(torrent_hash)
                self._delete_torrent_store(torrent_hash=torrent_hash)

        # add and initialize new torrents
        while not self._torrents_to_add_q.empty():
            new_torrent_hash = self._torrents_to_add_q.get()
            if new_torrent_hash not in self._torrent_hashes:
                self._rid[new_torrent_hash] = 0
                self._torrent_hashes.append(new_torrent_hash)
                self._put_torrent_store(torrent_hash=new_torrent_hash,
                                        torrent=dict(),
                                        properties=dict(),
                                        trackers=list(),
                                        sync_torrent_peers=dict(full_update=True))

        # retrieve 'torrent' info for all torrents
        torrents_info = self.client.torrents_list(torrent_ids=[torrent_hash for torrent_hash in self._torrent_hashes])
        torrents = {t['hash']: t for t in torrents_info}

        # retrieve properties, trackers, and torrent peers info for all trackers
        for torrent_hash in self._torrent_hashes:
            properties = self.client.torrent_properties(torrent_id=torrent_hash)
            trackers = self.client.torrent_trackers(torrent_id=torrent_hash)
            sync_torrent_peers = self.client.sync_torrent_peers(torrent_id=torrent_hash, rid=self._rid[torrent_hash])
            content = self.client.torrent_files(torrent_id=torrent_hash)
            self._rid[torrent_hash] = sync_torrent_peers.get('rid', 0)

            # put everything in to the store for the torrent
            self._put_torrent_store(torrent_hash=torrent_hash,
                                    torrent=torrents[torrent_hash],
                                    properties=properties,
                                    trackers=trackers,
                                    sync_torrent_peers=sync_torrent_peers,
                                    content=content)

            # signal UI that torrent data is ready
            self.signal_ui("sync_torrent_data_ready:%s" % torrent_hash)

    def add_sync_torrent_hash(self, torrent_hash: str):
        self._torrents_to_add_q.put(torrent_hash)
        self.set_wake_up("torrent hash added")

    def remove_sync_torrent_hash(self, torrent_hash: str):
        self._torrents_to_remove_q.put(torrent_hash)

    def get_torrent_store(self, torrent_hash: str):
        self._torrent_store_lock.acquire()
        store = self._torrent_stores.get(torrent_hash, None)
        self._torrent_store_lock.release()
        return store

    def _put_torrent_store(self, torrent_hash: str, torrent=None, properties=None, trackers=None, sync_torrent_peers=None, content=None):
        self._torrent_store_lock.acquire()
        if torrent_hash not in self._torrent_stores:
            self._torrent_stores[torrent_hash] = SyncTorrent.TorrentStore()
        if torrent:
            self._torrent_stores[torrent_hash].torrent = torrent
        if properties:
            self._torrent_stores[torrent_hash].properties = properties
        if trackers:
            self._torrent_stores[torrent_hash].trackers = trackers
        if sync_torrent_peers:
            if sync_torrent_peers.get('full_update', False):
                self._torrent_stores[torrent_hash].sync_torrent_peers = sync_torrent_peers.get('peers', {})
            else:
                for peer in sync_torrent_peers.get('peers_removed', []):
                    self._torrent_stores[torrent_hash].sync_torrent_peers.pop(peer)
                for peer, peer_dict in sync_torrent_peers.get('peers', {}).items():
                    if peer in self._torrent_stores[torrent_hash].sync_torrent_peers:
                        self._torrent_stores[torrent_hash].sync_torrent_peers[peer].update(peer_dict)
                    else:
                        self._torrent_stores[torrent_hash].sync_torrent_peers[peer] = peer_dict
        if content:
            self._torrent_stores[torrent_hash].content = content
        self._torrent_store_lock.release()

    def _delete_torrent_store(self, torrent_hash: str):
        self._torrent_store_lock.acquire()
        self._torrent_stores.pop(torrent_hash, None)
        self._torrent_store_lock.release()

    class TorrentStore(object):
        def __init__(self):
            super(SyncTorrent.TorrentStore, self).__init__()
            self.torrent = AttrDict()
            self.properties = AttrDict()
            self.trackers = list()
            self.sync_torrent_peers = AttrDict()
            self.content = list()


class ServerDetails(Daemon):
    def __init__(self, torrent_client):
        """
        Background daemon that syncs server details with app

        :param torrent_client:
        """
        super(ServerDetails, self).__init__(torrent_client)

        self._server_details = AttrDict({'server_version': "",
                                        'api_conn_port': ""})
        self._server_preferences = AttrDict()
        self._server_details_lock = RLock()
        self._server_preferences_lock = RLock()

    def _one_loop(self):
        server_version = self.client.version()
        preferences = self.client.preferences()
        connection_port = preferences.web_ui_port

        self.set_preferences(preferences)

        new_details = False
        if server_details_changed.receivers:
            if server_version != self.get_server_details('server_version'):
                self.set_server_detail('server_version', server_version)
                new_details = True
            if connection_port != self.get_server_details('api_conn_port'):
                self.set_server_detail('api_conn_port', connection_port)
                new_details = True

        if new_details:
            self.signal_ui("server_details_ready")

    def get_server_preferences(self):
        self._server_preferences_lock.acquire()
        prefs = deepcopy(self._server_preferences)
        self._server_preferences_lock.release()
        return prefs

    def set_preferences(self, prefs):
        self._server_preferences_lock.acquire()
        self._server_preferences = prefs
        self._server_preferences_lock.release()

    def set_server_detail(self, key, value):
        self._server_details_lock.acquire()
        self._server_details[key] = value
        self._server_details_lock.release()

    def get_server_details(self, detail=None):
        self._server_details_lock.acquire()
        details = deepcopy(self._server_details)
        self._server_details_lock.release()
        if detail is None:
            return details
        else:
            return details.get(detail, "")


# TODO: implement callback ability
class Commands(Daemon):
    def __init__(self, torrent_client):
        """
        Daemon to send commands to the server

        :param torrent_client:
        """
        super(Commands, self).__init__(torrent_client)

        # set a long loop interval since anything sending
        # commands should also be setting the wake alarm
        self._loop_interval = 60

        self._command_q = queue.Queue()

    def _one_loop(self):
        logger.info("Command queue length: %s" % self._command_q.qsize())
        ran_commands = False
        while not self._command_q.empty():
            ran_commands = True
            try:
                command = self._command_q.get()
                command_func = command.get('func', '')
                command_args = command.get('func_args', {})
                logger.info("Background command: %s" % command_func)
                logger.info("Background command args: %s " % command_args)
                command_func(**command_args)
            except Exception:
                logger.info("Failed to run command", exc_info=True)
        # request server sync if commands were issued
        if ran_commands:
            update_torrent_list_now.send('commands daemon')

    def run_command(self, sender, command_func: str, command_args: dict):
        self._command_q.put(dict(func=command_func, func_args=command_args))
        self.set_wake_up(sender)
