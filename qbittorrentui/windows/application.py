import urwid as uw
from socket import getfqdn
import logging
from attrdict import AttrDict
from time import time

from qbittorrentui.windows.torrent_list import TorrentListWindow
from qbittorrentui.config import APPLICATION_NAME
from qbittorrentui.debug import log_keypress
from qbittorrentui.debug import IS_TIMING_LOGGING_ENABLED
from qbittorrentui.misc_widgets import ButtonWithoutCursor
from qbittorrentui.connector import ConnectorError
from qbittorrentui.connector import LoginFailed
from qbittorrentui.formatters import natural_file_size
from qbittorrentui.events import initialize_torrent_list
from qbittorrentui.events import server_details_changed
from qbittorrentui.events import server_state_changed

logger = logging.getLogger(__name__)


class AppWindow(uw.Frame):
    def __init__(self, main):
        self.main = main

        # build windows
        self.title_bar_w = AppTitleBar()
        self.status_bar_w = AppStatusBar()
        self.torrent_list_w = TorrentListWindow(self.main)

        # connect to signals

        super(AppWindow, self).__init__(body=self.torrent_list_w,
                                        header=self.title_bar_w,
                                        footer=self.status_bar_w,
                                        focus_part='body')

    def keypress(self, size, key):
        log_keypress(logger, self, key)
        return super(AppWindow, self).keypress(size, key)


class AppTitleBar(uw.Text):
    def __init__(self):
        """Application title bar."""
        super(AppTitleBar, self).__init__(markup="", align=uw.CENTER, wrap=uw.CLIP, layout=None)
        self.refresh("title bar init")
        server_details_changed.connect(receiver=self.refresh)

    def refresh(self, sender, details: dict = None):
        start_time = time()
        div_ch = "|"
        if details is None:
            details = {}
        app_name = APPLICATION_NAME
        hostname = getfqdn()
        ver = details.get('server_version', "")
        port = details.get('api_conn_port', "")
        server_version_str = "%s" % (" %s %s" % (div_ch, ver) if ver != "" else "")
        hostname_str = "%s" % (" %s %s" % (div_ch, ("%s" % ("%s:%s" % (hostname, port) if port != "" else hostname)) if hostname != "" else ""))
        self.set_text("%s%s%s" % (app_name,
                                  server_version_str,
                                  hostname_str,
                                  )
                      )
        if IS_TIMING_LOGGING_ENABLED:
            logger.info("Updating title bar (from %s) (%.2fs)" % (sender, time() - start_time))


class AppStatusBar(uw.Columns):
    def __init__(self):
        super(AppStatusBar, self).__init__(widget_list=[], dividechars=1, focus_column=None, min_width=1, box_columns=None)
        self.refresh("status bar init")
        server_state_changed.connect(receiver=self.refresh)

    def selectable(self):
        return False

    def refresh(self, sender, server_state: AttrDict = None):
        start_time = time()

        if server_state is None:
            server_state = {}

        status = server_state.get('connection_status', 'disconnected')

        dht_nodes = server_state.get('dht_nodes')

        ''' ⯆[<dl rate>:<dl limit>:<dl size>] ⯅[<up rate>:<up limit>:<up size>] '''
        dl_up_text = ("%s/s%s [%s%s] (%s) %s/s%s [%s%s] (%s)" %
                      (natural_file_size(server_state.dl_info_speed, gnu=True).rjust(6),
                       '\u25BC',
                       natural_file_size(server_state.dl_rate_limit,
                                         gnu=True) if server_state.dl_rate_limit not in [0, ''] else '',
                       '/s' if server_state.dl_rate_limit not in [0, ''] else '',
                       natural_file_size(server_state.dl_info_data, gnu=True),
                       natural_file_size(server_state.up_info_speed, gnu=True).rjust(6),
                       '\u25B2',
                       natural_file_size(server_state.up_rate_limit,
                                         gnu=True) if server_state.up_rate_limit not in [0, ''] else '',
                       '/s' if server_state.up_rate_limit not in [0, ''] else '',
                       natural_file_size(server_state.up_info_data, gnu=True),
                       )
                      ) if server_state.get('dl_rate_limit', '') != '' else ''

        left_column_text = "%sStatus: %s" % (("DHT: %s " % dht_nodes) if dht_nodes is not None else "", status)
        right_column_text = "%s" % dl_up_text
        total_len = len(left_column_text) + len(right_column_text)

        self.contents.clear()  # (w, (f, width, False)
        self.contents.append((uw.Text(left_column_text, align=uw.LEFT, wrap=uw.CLIP),
                             (uw.WEIGHT,
                              len(left_column_text) / total_len * 100,
                              False)
                              )
                             )
        self.contents.append((uw.Padding(uw.Text(right_column_text, align=uw.RIGHT, wrap=uw.CLIP)),
                              (uw.WEIGHT,
                               len(right_column_text) / total_len * 100,
                               False)
                              )
                             )
        if IS_TIMING_LOGGING_ENABLED:
            logger.info("Updating status bar (from %s) (%.2fs)" % (sender, time() - start_time))


class ConnectDialog(uw.ListBox):
    def __init__(self, main):
        self.main = main
        self.client = main.torrent_client

        self.error_w = uw.Text("", align=uw.CENTER)
        self.hostname_w = uw.Edit("Hostname: ", edit_text=self.client.host)
        self.port_w = uw.Edit("Port: ")
        self.username_w = uw.Edit("Username: ")
        self.password_w = uw.Edit("Password: ", mask='*')

        super(ConnectDialog, self).__init__(
            uw.SimpleFocusListWalker(
                [
                    uw.Text("Enter connection information",
                            align=uw.CENTER),
                    uw.Divider(),
                    uw.AttrMap(self.error_w, 'light red on default'),
                    uw.Divider(),
                    self.hostname_w,
                    self.port_w,
                    self.username_w,
                    self.password_w,
                    uw.Divider(),
                    uw.Divider(),
                    uw.Divider(),
                    uw.Columns([
                        uw.Padding(uw.Text("")),
                        (6, uw.AttrMap(ButtonWithoutCursor("OK",
                                                           on_press=self.apply_settings),
                                       '', focus_map='selected')),
                        (10, uw.AttrMap(ButtonWithoutCursor("Cancel",
                                                            on_press=self.leave_app),
                                        '', focus_map='selected')),
                        uw.Padding(uw.Text("")),
                    ], dividechars=3),
                    uw.Divider(),
                    uw.Divider(),
                ]
            )
        )

    def keypress(self, size, key):
        log_keypress(logger, self, key)
        key = super(ConnectDialog, self).keypress(size, key)
        if key == 'esc':
            self.leave_app()

    def leave_app(self, _=None):
        raise uw.ExitMainLoop

    def apply_settings(self, _):
        try:
            port = self.port_w.get_edit_text()
            self.client.connect(host="%s%s" % (self.hostname_w.get_edit_text(), ":%s" % port if port else ""),
                                username=self.username_w.get_edit_text(),
                                password=self.password_w.get_edit_text())
            self.main.loop.widget = self.main.app_window
            initialize_torrent_list.send('connect window')
        except LoginFailed:
            self.error_w.set_text("Error: login failed")
        except ConnectorError as e:
            self.error_w.set_text("Error: %s" % e)
