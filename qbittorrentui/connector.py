from enum import Enum
from functools import wraps

from qbittorrentapi import Client as qbt_Client
from qbittorrentapi import exceptions as qbt_exceptions
from qbittorrentui.events import run_server_command


class ClientType(Enum):
    qbittorrent = 1


class ConnectorError(Exception):
    pass


class LoginFailed(ConnectorError):
    pass


def connection_required(f):
    """Ensure client is connected before calling API methods."""
    @wraps(f)
    def wrapper(obj, *args, **kwargs):
        if not obj.is_logged_in:
            raise ConnectorError("Connect to torrent manager first")
        try:
            return f(obj, *args, **kwargs)
        except Exception as e:
            raise ConnectorError(repr(e))
    return wrapper


class Connector:
    _qbt_client: qbt_Client

    def __init__(self, main, client_type=ClientType.qbittorrent, host="", username="", password=""):
        self.main = main
        self._client_type = client_type
        # self._qbt_client = None
        self.client_version = None
        self.is_logged_in = False

        self.host = host
        self.username = username
        self.password = password

        if client_type is ClientType.qbittorrent:
            if host and username and password:
                try:
                    self.connect(host, username, password)
                except ConnectorError:
                    pass

    def send_command(self, func, func_args):
        self.main.bg_poller.command_q.put({'func': func,
                                           'func_args': func_args})
        run_server_command.send('connector')

    def connect(self, host="", username="", password=""):
        if host == "":
            host = self.host
        if username == "":
            username = self.username
        if password == "":
            password = self.password
        if self._client_type is ClientType.qbittorrent:
            try:
                self._qbt_client = qbt_Client(host, username, password)
            except AssertionError:
                raise LoginFailed("Missing host, username, or password")
            try:
                self.is_logged_in = True
                self.client_version = self._qbt_client.app_version()
            except qbt_exceptions.LoginFailed as e:
                self.is_logged_in = False
                raise LoginFailed(e)
            except qbt_exceptions.APIError as e:
                self.is_logged_in = False
                raise ConnectorError(repr(e))

    @property
    def is_connected(self):
        return self.is_logged_in

    @connection_required
    def version(self):
        if self._client_type is ClientType.qbittorrent:
            return self._qbt_client.app_version()

    @connection_required
    def preferences(self):
        if self._client_type is ClientType.qbittorrent:
            return self._qbt_client.app_preferences()

    @connection_required
    def transfer_info(self):
        if self._client_type is ClientType.qbittorrent:
            return self._qbt_client.transfer_info()

    @connection_required
    def torrents_add(self, urls=None, torrent_files=None, save_path=None, cookie=None, category=None,
                     is_skip_checking=None, is_paused=None, is_root_folder=None, rename=None,
                     upload_limit=None, download_limit=None, use_auto_torrent_management=None,
                     is_sequential_download=None, is_first_last_piece_priority=None):
        if self._client_type is ClientType.qbittorrent:
            return self._qbt_client.torrents_add(urls=urls, torrent_files=torrent_files, save_path=save_path,
                                                 cookie=cookie, category=category, is_skip_checking=is_skip_checking,
                                                 is_paused=is_paused, is_root_folder=is_root_folder, rename=rename,
                                                 upload_limit=upload_limit, download_limit=download_limit,
                                                 use_auto_torrent_management=use_auto_torrent_management,
                                                 is_sequential_download=is_sequential_download,
                                                 is_first_last_piece_priority=is_first_last_piece_priority)

    @connection_required
    def torrent_properties(self, torrent_id):
        if self._client_type is ClientType.qbittorrent:
            return self._qbt_client.torrents_properties(hash=torrent_id)

    @connection_required
    def torrents_list(self, status_filter='all', torrent_ids=None):
        if self._client_type is ClientType.qbittorrent:
            return self._qbt_client.torrents_info(status_filter=status_filter, hashes=torrent_ids)

    @connection_required
    def torrents_delete(self, torrent_ids, delete_files=False):
        if self._client_type is ClientType.qbittorrent:
            self.send_command(func=self._qbt_client.torrents_delete,
                              func_args=dict(delete_files=delete_files,
                                             hashes=torrent_ids))

    @connection_required
    def torrents_resume(self, torrent_ids):
        if self._client_type is ClientType.qbittorrent:
            self.send_command(func=self._qbt_client.torrents_resume,
                              func_args=dict(hashes=torrent_ids))

    @connection_required
    def torrents_pause(self, torrent_ids):
        if self._client_type is ClientType.qbittorrent:
            self.send_command(func=self._qbt_client.torrents_pause,
                              func_args=dict(hashes=torrent_ids))

    @connection_required
    def torrents_force_resume(self, torrent_ids):
        if self._client_type is ClientType.qbittorrent:
            self.send_command(func=self._qbt_client.torrents_set_force_start,
                              func_args=dict(hashes=torrent_ids, enable=True))

    @connection_required
    def torrents_recheck(self, torrent_ids):
        if self._client_type is ClientType.qbittorrent:
            self.send_command(func=self._qbt_client.torrents_recheck,
                              func_args=dict(hashes=torrent_ids))

    @connection_required
    def torrents_reannounce(self, torrent_ids):
        if self._client_type is ClientType.qbittorrent:
            self.send_command(func=self._qbt_client.torrents_reannounce,
                              func_args=dict(hashes=torrent_ids))

    @connection_required
    def torrents_categories(self):
        if self._client_type is ClientType.qbittorrent:
            return self._qbt_client.torrents_categories()

    @connection_required
    def torrents_set_location(self, location, torrent_ids):
        if self._client_type is ClientType.qbittorrent:
            self.send_command(func=self._qbt_client.torrents_set_location,
                              func_args=dict(location=location, hashes=torrent_ids))

    @connection_required
    def torrent_rename(self, new_name, torrent_id):
        if self._client_type is ClientType.qbittorrent:
            self.send_command(func=self._qbt_client.torrents_rename,
                              func_args=dict(new_torrent_name=new_name, hash=torrent_id))

    @connection_required
    def torrents_set_automatic_torrent_management(self, enable, torrent_ids):
        if self._client_type is ClientType.qbittorrent:
            self.send_command(func=self._qbt_client.torrents_set_auto_management,
                              func_args=dict(enable=enable, hashes=torrent_ids))

    @connection_required
    def torrents_set_super_seeding(self, enable, torrent_ids):
        if self._client_type is ClientType.qbittorrent:
            self.send_command(func=self._qbt_client.torrents_set_super_seeding,
                              func_args=dict(enable=enable, hashes=torrent_ids))

    @connection_required
    def torrents_set_upload_limit(self, limit, torrent_ids):
        if self._client_type is ClientType.qbittorrent:
            self.send_command(func=self._qbt_client.torrents_set_upload_limit,
                              func_args=dict(limit=limit, hashes=torrent_ids))

    @connection_required
    def torrents_set_download_limit(self, limit, torrent_ids):
        if self._client_type is ClientType.qbittorrent:
            self.send_command(func=self._qbt_client.torrents_set_download_limit,
                              func_args=dict(limit=limit, hashes=torrent_ids))

    @connection_required
    def torrents_set_category(self, category, torrent_ids):
        if self._client_type is ClientType.qbittorrent:
            self.send_command(func=self._qbt_client.torrents_set_category,
                              func_args=dict(category=category, hashes=torrent_ids))

    @connection_required
    def torrents_set_share_limits(self, ratio_limit, seeding_time_limit, torrent_ids):
        if self._client_type is ClientType.qbittorrent:
            self.send_command(func=self._qbt_client.torrents_set_share_limits,
                              func_args=dict(ratio_limit=ratio_limit,
                                             seeding_time_limit=seeding_time_limit,
                                             hashes=torrent_ids))

    @connection_required
    def sync_maindata(self, rid):
        if self._client_type is ClientType.qbittorrent:
            return self._qbt_client.sync_maindata(rid)

    @connection_required
    def api_wrapper(self, api_endpoint, **kwargs):
        return getattr(self._qbt_client, api_endpoint)(**kwargs)
