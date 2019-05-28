import urwid as uw
from socket import getfqdn
import logging
from attrdict import AttrDict
import panwid
import blinker
from datetime import datetime

from time import time

from qbittorrentui.events import IS_TIMING_LOGGING_ENABLED

from qbittorrentui.connector import Connector
from qbittorrentui.connector import ConnectorError
from qbittorrentui.connector import LoginFailed
from qbittorrentui.events import refresh_torrent_list_now
from qbittorrentui.events import update_torrent_list_now
from qbittorrentui.events import initialize_torrent_list
from qbittorrentui.events import server_details_changed
from qbittorrentui.events import server_torrents_changed
from qbittorrentui.events import server_state_changed
from qbittorrentui.events import torrent_window_tab_change


_APP_NAME = 'qBittorrenTUI'
logger = logging.getLogger(__name__)


# TODO: put this somewhere else
def pretty_time_delta(seconds):
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days > 0:
        # return '%dd%dh%dm%ds' % (days, hours, minutes, seconds)
        return '%dd%dh' % (days, hours)
    elif hours > 0:
        # return '%dh%dm%ds' % (hours, minutes, seconds)
        return '%dh%dm' % (hours, minutes)
    elif minutes > 0:
        return '%dm%ds' % (minutes, seconds)
    else:
        return '%ds' % seconds


def natural_file_size(value, binary=False, gnu=False, num_format='%.1f'):
    """
    Format a number of byteslike a human readable filesize (eg. 10 kB).

    By
    default, decimal suffixes (kB, MB) are used.  Passing binary=true will use
    binary suffixes (KiB, MiB) are used and the base will be 2**10 instead of
    10**3.  If ``gnu`` is True, the binary argument is ignored and GNU-style
    (ls -sh style) prefixes are used (K, M) with the 2**10 definition.
    Non-gnu modes are compatible with jinja2's ``filesizeformat`` filter.
    source: https://github.com/luckydonald-forks/humanize/blob/master/humanize/filesize.py
    """
    suffixes = {
        'decimal': ('kB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'),
        'binary': ('KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB'),
        'gnu': "KMGTPEZY",
    }
    if gnu:
        suffix = suffixes['gnu']
    elif binary:
        suffix = suffixes['binary']
    else:
        suffix = suffixes['decimal']

    base = 1024 if (gnu or binary) else 1000
    num_of_bytes = float(value)

    if num_of_bytes == 1 and not gnu:
        return '1 Byte'
    elif num_of_bytes < base and not gnu:
        if num_of_bytes > 1000:
            num_of_bytes = base
        else:
            return '%d Bytes' % num_of_bytes
    elif num_of_bytes < base and gnu:
        if num_of_bytes > 1000:
            num_of_bytes = base
        else:
            return '%dB' % num_of_bytes

    for i, s in enumerate(suffix):
        unit = base ** (i + 2)
        # round up to next unit to avoid 4 digit size
        if len(str(int(base * num_of_bytes / unit))) == 4 and num_of_bytes < unit:
            num_of_bytes = unit
        if num_of_bytes < unit:
            break
    if gnu:
        return (num_format + '%s') % ((base * num_of_bytes / unit), s)
    else:
        return (num_format + ' %s') % ((base * num_of_bytes / unit), s)


def log_keypress(obj, key):
    logger.info("%s received key '%s'" % (obj.__class__.__name__, key))


class ButtonLabel(uw.SelectableIcon):
    def set_text(self, label):
        self.__super.set_text(label)
        self._cursor_position = len(label) + 1


# noinspection PyMissingConstructor
class ButtonWithoutCursor(uw.Button):
    button_left = "["
    button_right = "]"

    def __init__(self, label, on_press=None, user_data=None):
        self._label = ButtonLabel("")
        cols = uw.Columns([
            ('fixed', len(self.button_left), uw.Text(self.button_left)),
            self._label,
            ('fixed', len(self.button_right), uw.Text(self.button_right))],
            dividechars=1)
        super(uw.Button, self).__init__(cols)

        if on_press:
            uw.connect_signal(self, 'click', on_press, user_data)

        self.set_label(label)


class DownloadProgressBar(uw.ProgressBar):
    def get_text(self):
        return "%s %s" % (natural_file_size(self.current, gnu=True).rjust(7),
                          ("(%s)" % self.get_percentage()).ljust(6))

    def get_percentage(self):
        percent = int(self.current * 100 / self.done)
        return "%s%s" % (percent, "%")


class SelectableText(uw.Text):
    def selectable(self):
        return True

    @staticmethod
    def keypress(size, key, *args, **kwargs):
        return key


class AppWindow(uw.Frame):
    def __init__(self, main):
        self.main = main

        # build windows
        self.title_bar_w = AppTitleBar()
        self.status_bar_w = AppStatusBar()
        self.torrent_list_w = TorrentListBox(self.main)

        # connect to signals

        super(AppWindow, self).__init__(body=self.torrent_list_w,
                                        header=self.title_bar_w,
                                        footer=self.status_bar_w,
                                        focus_part='body')

    def keypress(self, size, key):
        log_keypress(self, key)
        return super(AppWindow, self).keypress(size, key)


class AppTitleBar(uw.Text):
    def __init__(self):
        """Application title bar."""
        super(AppTitleBar, self).__init__(markup="", align=uw.CENTER, wrap=uw.CLIP, layout=None)
        self.refresh("title bar init")
        server_details_changed.connect(receiver=self.refresh)

    def refresh(self, sender, details: dict = None):
        start_time = time()
        if details is None:
            details = {}
        app_name = _APP_NAME
        hostname = getfqdn()
        self.set_text("%s (%s) %s:%s" % (app_name,
                                         details.get('server_version', ""),
                                         hostname,
                                         details.get('api_conn_port', "")
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


class ConnectBox(uw.ListBox):
    def __init__(self, main):
        self.main = main
        self.client = main.torrent_client

        self.error_w = uw.Text("", align=uw.CENTER)
        self.hostname_w = uw.Edit("Hostname: ", edit_text=self.client.host)
        self.port_w = uw.Edit("Port: ")
        self.username_w = uw.Edit("Username: ")
        self.password_w = uw.Edit("Password: ", mask='*')

        super(ConnectBox, self).__init__(
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
        log_keypress(self, key)
        key = super(ConnectBox, self).keypress(size, key)
        if key == 'esc':
            self.leave_app()

    def leave_app(self, _=None):
        raise uw.ExitMainLoop

    def apply_settings(self, args):
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


class TorrentListBox(uw.Pile):
    def __init__(self, main):
        """

        :param main:
        :type main: main.Main()
        """
        self.main = main
        self.client = main.torrent_client

        self.__width = None
        self.last_refresh_time = None

        # initialize torrent list
        self.torrent_list_walker_w = uw.SimpleFocusListWalker([uw.Text("Loading...")])
        self.torrent_list_w = TorrentListBox.TorrentList(self, self.torrent_list_walker_w)

        #  Set up torrent status tabs
        self.torrent_tabs_w = TorrentListBox.TorrentListTabsColumns()

        # initialize torrent list box
        super(TorrentListBox, self).__init__([(1, self.torrent_tabs_w),
                                              (1, uw.Filler(uw.Divider())),
                                              self.torrent_list_w
                                              ])

        # signals
        initialize_torrent_list.connect(receiver=self.torrent_list_init)
        uw.register_signal(type(self.torrent_tabs_w), 'change')
        uw.connect_signal(self.torrent_tabs_w,
                          'change',
                          self.refresh_torrent_list,
                          user_args=["torrents_tabs_w change"])
        uw.register_signal(type(self.torrent_tabs_w), 'reset list focus')
        uw.connect_signal(self.torrent_tabs_w,
                          'reset list focus',
                          self.set_torrent_list_focus)

    @property
    def width(self):
        if self.__width:
            return self.__width
        else:
            return self.main.ui.get_cols_rows()[1]

    def render(self, size, focus=False):
        # catch screen resize
        start_time = time()
        if self.__width != size[0]:
            self.__width = size[0]
            # call to refresh_torrent_list on screen re-sizes
            refresh_torrent_list_now.send('torrent list render')
        ret = super(TorrentListBox, self).render(size, focus)
        if IS_TIMING_LOGGING_ENABLED:
            logger.info("Rendering Torrent List window (%.2fs)" % (time() - start_time))
        return ret

    def keypress(self, size, key):
        log_keypress(self, key)
        key = super(TorrentListBox, self).keypress(size, key)
        if key in ['a', 'A']:
            self.main.loop.widget = uw.Overlay(top_w=uw.LineBox(TorrentAdd(self.main)),
                                               bottom_w=self.main.app_window,
                                               align=uw.CENTER,
                                               valign=uw.MIDDLE,
                                               width=(uw.RELATIVE, 50),
                                               height=(uw.RELATIVE, 50),
                                               min_width=20
                                               )
        return key

    def torrent_list_init(self, sender):
        """once connected to qbittorrent, initialize torrent list window"""
        server_torrents_changed.connect(receiver=self.update_torrent_list)
        refresh_torrent_list_now.connect(receiver=self.refresh_torrent_list)
        update_torrent_list_now.send("initialization")

    def apply_torrent_list_filter(self):
        status_filter = self.torrent_tabs_w.get_selected_tab_name()
        self.torrent_list_walker_w.clear()
        state_map_for_filtering = {'downloading': ['downloading',
                                                   'metaDL',
                                                   'queuedDL',
                                                   'stalledDL',
                                                   'pausedDL',
                                                   'forcedDL'
                                                   ],
                                   'completed': ['uploading',
                                                 'stalledUP',
                                                 'checkingUP',
                                                 'pausedUP',
                                                 'queuedUP',
                                                 'forcedUP',
                                                 ],
                                   'active': ['metaDL',
                                              'downloading',
                                              'forcedDL',
                                              'uploading',
                                              'forcedUP',
                                              'moving',
                                              ],
                                   'inactive': ['pausedUP',
                                                'stalledUP',
                                                'stalledDL',
                                                'queuedDL',
                                                'queuedUP',
                                                'pausedDL',
                                                'checkingDL',
                                                'checkingUP',
                                                'allocating',
                                                'missingfiles',
                                                'error',
                                                'queuedForChecking',
                                                'checkingResumeData',
                                                ],
                                   'paused': ['pausedUP',
                                              'queuedDL',
                                              'queuedUP',
                                              'pausedDL',
                                              'missingfiles',
                                              'error',
                                              'queuedForChecking',
                                              'checkingResumeData',
                                              ],
                                   'resumed': ['uploading',
                                               'stalledUP',
                                               'forcedUP',
                                               'checkingDL',
                                               'checkingUP',
                                               'downloading',
                                               'forcedDL',
                                               'metaDL',
                                               'stalledDL',
                                               'allocating',
                                               'moving']
                                   }
        if status_filter != 'all':
            for torrent_row_w in self.torrent_list_w.torrent_row_list:
                state = torrent_row_w.base_widget.cached_torrent.state
                if state in state_map_for_filtering[status_filter]:
                    self.torrent_list_walker_w.append(torrent_row_w)
        else:
            self.torrent_list_walker_w.extend(self.torrent_list_w.torrent_row_list)

    def set_torrent_list_focus(self, sender="", torrent_hash: str = None):
        """
        Focus torrent row with provided torrent hash or focus first row

        :param sender:
        :param torrent_hash:
        """
        found = False
        if torrent_hash is not None:
            for pos, torrent in enumerate(self.torrent_list_walker_w):
                if torrent.base_widget.get_torrent_hash() == torrent_hash:
                    self.torrent_list_walker_w.set_focus(pos)
                    found = True
                    break
        if not found:
            self.torrent_list_walker_w.set_focus(0)

    def update_torrent_list(self, sender, torrents=None):
        """
        Update torrents with new data and refresh_torrent_list window.

        :param sender:
        :param torrents:
        :return:
        """
        start_time = time()

        if torrents is None:
            torrents = dict()

        # remove torrents no longer on the server
        # update any torrents found
        for i, entry in enumerate(self.torrent_list_w.torrent_row_list):
            torrent_row_w = entry.base_widget
            if not isinstance(torrent_row_w, TorrentListBox.TorrentRow) or torrent_row_w.get_torrent_hash() not in torrents:
                self.torrent_list_w.torrent_row_list.pop(i)
            else:
                torrent_row_w.update(torrents[torrent_row_w.get_torrent_hash()])

        # add any new torrents
        for torrent_hash, torrent in torrents.items():
            found = False
            for torrent_row_w in [entry.base_widget for entry in self.torrent_list_w.torrent_row_list]:
                if torrent_row_w.get_torrent_hash() == torrent_hash:
                    found = True
                    break
            if found is False:
                self.torrent_list_w.torrent_row_list.append(TorrentListBox.TorrentRow(torrent_list_box_w=self,
                                                                                      torrent_hash=torrent_hash,
                                                                                      torrent=AttrDict(torrent)
                                                                                      ))

        if IS_TIMING_LOGGING_ENABLED:
            logger.info("Updating Torrent List (from %s) (%.2fs)" % (sender, (time() - start_time)))
        self.refresh_torrent_list(sender)

    def refresh_torrent_list(self, sender):
        """
        Refreshes the torrent list using local torrent data.

        :param sender:
        :return:
        """
        start_time = time()

        # save off focused row so it can be re-focused after refresh
        torrent_hash_in_focus = self.torrent_list_w.get_torrent_hash_for_focused_row()

        # dynamically resize torrent list based on window width
        self.torrent_list_w.resize()

        # put the relevant torrents in the walker
        self.apply_torrent_list_filter()

        # re-focus same torrent if it still exists
        self.set_torrent_list_focus("torrent list refresh", torrent_hash=torrent_hash_in_focus)

        if IS_TIMING_LOGGING_ENABLED:
            logger.info("Refreshing Torrent List (from %s) (%.2fs)" % (sender, (time() - start_time)))

    class TorrentListTabsColumns(uw.Columns):
        def __init__(self):
            self.torrent_tabs_list = []
            for i, tab_name in enumerate(
                    ["All", "Downloading", "Completed", "Paused", "Active", "Inactive", "Resumed"]):
                self.torrent_tabs_list.append(
                    uw.AttrMap(
                        uw.Filler(SelectableText(tab_name,
                                                 align=uw.CENTER)),
                        "selected" if i == 0 else "",
                        focus_map='selected')
                )
            super(TorrentListBox.TorrentListTabsColumns, self).__init__(widget_list=self.torrent_tabs_list,
                                                                        dividechars=0,
                                                                        focus_column=0)
            # TODO: replace references with get_focus()
            self.__selected_tab_pos = 0

        def get_selected_tab_name(self):
            return self[self.__selected_tab_pos].get_text()[0].lower()

        def move_cursor_to_coords(self, size, col, row):
            """Don't change focus based on coords"""
            return True

        def keypress(self, size, key):
            log_keypress(self, key)
            key = super(TorrentListBox.TorrentListTabsColumns, self).keypress(size, key)

            focused_tab_pos = self.focus_position
            if focused_tab_pos != self.__selected_tab_pos:
                tab_text = self.contents[self.__selected_tab_pos][0].base_widget.get_text()[0]
                new_col = uw.AttrMap(
                    uw.Filler(SelectableText(tab_text, align=uw.CENTER)),
                    '',
                    focus_map='selected')
                self.contents[self.__selected_tab_pos] = (new_col, ('weight', 1, False))
                self.__selected_tab_pos = focused_tab_pos
                tab_text = self.contents[self.__selected_tab_pos][0].base_widget.get_text()[0]
                new_col = uw.AttrMap(
                    uw.Filler(SelectableText(tab_text, align=uw.CENTER)),
                    'selected',
                    focus_map='selected')
                self.contents[self.__selected_tab_pos] = (new_col, ('weight', 1, False))

                uw.emit_signal(self, 'change')
                uw.emit_signal(self, 'reset list focus')
            return key

    class TorrentList(uw.ListBox):
        def __init__(self, torrent_list_box, body):
            super(TorrentListBox.TorrentList, self).__init__(body)
            self.torrent_list_box_w = torrent_list_box

            self.torrent_row_list = []
            """master torrent row widget list of all torrents"""

        def keypress(self, size, key):
            log_keypress(self, key)
            key = super(TorrentListBox.TorrentList, self).keypress(size, key)
            # if key == 'right':
            #    self.loop.widget = self.main.torrent_window
            #    return None
            # else:
            return key

        def get_torrent_hash_for_focused_row(self):
            focused_row, focused_row_pos = self.body.get_focus()
            if isinstance(focused_row, TorrentListBox.TorrentRow):
                return focused_row.base_widget.get_torrent_hash()
            return None

        def resize(self):
            """
            Resize all torrent rows to screen width.

            1) Determine longest torrent name
            2) Resize all torrent names to max name length
            3) Determine widths of different sizings
            4) Apply largest sizing that fits
            """
            # torrent info width with graphic progress bar: 115

            name_list = [torrent_row_w.cached_torrent.name for torrent_row_w in self.torrent_row_list]
            if name_list:
                max_name_len = max(map(len, name_list))
                for torrent_row_w in self.torrent_row_list:
                    torrent_row_w.resize_name_len(max_name_len)
            else:
                max_name_len = 50

            if self.torrent_list_box_w.width < (max_name_len + 80):
                for torrent_row_w in self.torrent_row_list:
                    # resize torrent name to 0 (effectively hiding it)
                    #  name keeps resetting each time info is udpated
                    torrent_row_w.resize_name_len(0)
                    if torrent_row_w.base_widget.current_sizing != "narrow":
                        logger.info("Resizing %s to narrow" % torrent_row_w.base_widget.cached_torrent.name)
                        # ensure we're using the pb text
                        torrent_row_w.swap_pb_bar_for_pb_text()
                        # insert a blank space
                        torrent_row_w.base_widget.torrent_info_columns_w.base_widget.contents.insert(
                            0,
                            (TorrentListBox.TorrentRow.TorrentInfoColumns.TorrentInfoColumnValueContainer(
                                name="blank",
                                raw_value=" ",
                                format_func=str),
                             torrent_row_w.base_widget.torrent_info_columns_w.base_widget.options(uw.PACK,
                                                                                                  None,
                                                                                                  False)
                            ))
                        # add the torrent name as a new widget in the Pile for the TorrentRow
                        torrent_row_w.base_widget.contents.insert(
                            0,
                            (uw.Padding(uw.Text(torrent_row_w.cached_torrent.name)),
                             ('pack', None))
                        )
                        torrent_row_w.base_widget.current_sizing = "narrow"

            elif self.torrent_list_box_w.width < (max_name_len + 115):
                for torrent_row_w in self.torrent_row_list:
                    if torrent_row_w.base_widget.current_sizing != 'pb_text':
                        if torrent_row_w.base_widget.current_sizing == 'narrow':
                            torrent_row_w.base_widget.torrent_info_columns_w.base_widget.contents.pop(0)
                            torrent_row_w.base_widget.contents.pop(0)
                        logger.info("Resizing %s to pb text" % torrent_row_w.base_widget.cached_torrent.name)
                        torrent_row_w.swap_pb_bar_for_pb_text()
                        torrent_row_w.base_widget.current_sizing = 'pb_text'

            else:
                for torrent_row_w in self.torrent_row_list:
                    if torrent_row_w.base_widget.current_sizing != 'pb_bar':
                        if torrent_row_w.base_widget.current_sizing == 'narrow':
                            torrent_row_w.base_widget.torrent_info_columns_w.base_widget.contents.pop(0)
                            torrent_row_w.base_widget.contents.pop(0)
                        logger.info("Resizing %s to pb bar" % torrent_row_w.base_widget.cached_torrent.name)
                        torrent_row_w.swap_pb_text_for_pb_bar()
                        torrent_row_w.base_widget.current_sizing = 'pb_bar'

    class TorrentRow(uw.Pile):
        state_map_for_display = {'pausedUP': 'Completed',
                                 'uploading': 'Seeding',
                                 'stalledUP': 'Seeding',
                                 'forcedUP': '[F] Seeding',
                                 'queuedDL': 'Queued',
                                 'queuedUP': 'Queued',
                                 'pausedDL': 'Paused',
                                 'checkingDL': 'Checking',
                                 'checkingUP': 'Checking',
                                 'downloading': 'Downloading',
                                 'forcedDL': '[F] Downloading',
                                 'metaDL': 'Downloading',
                                 'stalledDL': 'Stalled',
                                 'allocating': 'Allocating',
                                 'moving': 'Moving',
                                 'missingfiles': 'Missing Files',
                                 'error': 'Error',
                                 'queuedForChecking': 'Queued for Checking',
                                 'checkingResumeData': 'Checking Resume Data'}

        def __init__(self, torrent_list_box_w, torrent_hash: str, torrent: AttrDict):
            """
            Build a row for the torrent list.

            :param main:
            :param torrent_hash:
            :param torrent:
            :param max_title_len:
            :param focus_item:
            """
            self.__hash = None
            self.torrent_list_box_w = torrent_list_box_w
            self.main = torrent_list_box_w.main

            self.current_sizing = None

            self.cached_torrent = AttrDict(torrent)

            self.max_title_len = 50
            self.pb_len = 40

            # color based on state
            state = TorrentListBox.TorrentRow.state_map_for_display.get(torrent.state, '')
            if state in ["Downloading", "Queued", "Stalled"]:
                attr = 'dark green on default'
            elif state == "Paused":
                attr = 'dark cyan on default'
            elif state in ["Completed", '[F] Seeding', 'Seeding']:
                attr = 'dark blue on default'
            elif state == 'Error':
                attr = 'light red on default'
            else:
                attr = ''

            # build and populate new torrent row
            self.torrent_info_columns_w = uw.AttrMap(
                TorrentListBox.TorrentRow.TorrentInfoColumns(torrent_list_box_w,
                                                             torrent,
                                                             max_name_len=self.max_title_len,
                                                             pb_len=self.pb_len),
                attr,
                focus_map='selected'
            )
            # store hash
            self.set_torrent_hash(torrent_hash)
            # build row widget
            super(TorrentListBox.TorrentRow, self).__init__([self.torrent_info_columns_w])

        def update(self, torrent: AttrDict):
            self.cached_torrent = AttrDict(torrent)
            self.torrent_info_columns_w.base_widget.update(torrent)

        def resize_name_len(self, name_length: int):
            for i, w in enumerate(self.torrent_info_columns_w.base_widget.contents):
                if hasattr(w[0], 'name'):
                    if w[0].name == 'name':
                        self.torrent_info_columns_w.base_widget.contents[i] = (
                            w[0], self.torrent_info_columns_w.base_widget.options(w[1][0], name_length, w[1][2]))
            self.torrent_info_columns_w.base_widget.name_len = name_length

        def swap_pb_bar_for_pb_text(self):
            for i, w in enumerate(self.torrent_info_columns_w.base_widget.contents):
                if hasattr(w[0], 'name'):
                    if w[0].name == 'pb':
                        self.torrent_info_columns_w.base_widget.contents[i] = (
                            self.torrent_info_columns_w.base_widget.pb_text_w,
                            self.torrent_info_columns_w.base_widget.options(uw.GIVEN,
                                                                            len(self.torrent_info_columns_w.base_widget.pb_text_w),
                                                                            False)
                        )

        def swap_pb_text_for_pb_bar(self):
            for i, w in enumerate(self.torrent_info_columns_w.base_widget.contents):
                if hasattr(w[0], 'name'):
                    if w[0].name == 'pb_text':
                        self.torrent_info_columns_w.base_widget.contents[i] = (
                            self.torrent_info_columns_w.base_widget.pb_w,
                            self.torrent_info_columns_w.base_widget.options(uw.GIVEN,
                                                                            self.pb_len,
                                                                            False)
                        )

        def set_torrent_hash(self, torrent_hash):
            self.__hash = torrent_hash

        def get_torrent_hash(self):
            return self.__hash

        def open_torrent_options_window(self):
            torrent_name = self.cached_torrent.get('name', "")

            self.main.torrent_options_window = uw.Overlay(
                top_w=uw.LineBox(
                    TorrentOptions(torrent_list_box_w=self.torrent_list_box_w,
                                   torrent_hash=self.get_torrent_hash(),
                                   torrent=self.cached_torrent),
                    title=torrent_name
                ),
                bottom_w=self.torrent_list_box_w.main.app_window,
                align=uw.CENTER,
                width=(uw.RELATIVE, 50),
                valign=uw.MIDDLE,
                height=25,
                min_width=75)

            self.main.loop.widget = self.main.torrent_options_window

        def open_torrent_window(self):
            torrent_window = TorrentWindow(self.main,
                                           torrent_hash=self.get_torrent_hash(),
                                           torrent=self.cached_torrent
                                           )
            self.main.app_window.body = torrent_window

        def keypress(self, size, key):
            log_keypress(self, key)
            if key == 'enter':
                self.open_torrent_options_window()
                return None
            if key in ['right']:
                self.open_torrent_window()
                return None
            return key

        class TorrentInfoColumns(uw.Columns):
            def __init__(self, torrent_list_box, torrent: AttrDict, max_name_len, pb_len):
                self.wide = False
                self.name_len = max_name_len

                val_cont = TorrentListBox.TorrentRow.TorrentInfoColumns.TorrentInfoColumnValueContainer
                pb_cont = TorrentListBox.TorrentRow.TorrentInfoColumns.TorrentInfoColumnPBContainer

                def format_title(v): return str(v).ljust(self.name_len)
                self.name_w = val_cont(name='name', raw_value="", format_func=format_title)

                def format_state(v):
                    return (TorrentListBox.TorrentRow.state_map_for_display.get(v, v)).ljust(12)
                self.state_w = val_cont(name='state', raw_value="", format_func=format_state)

                def format_size(v): return natural_file_size(v, gnu=True).rjust(6)
                self.size_w = val_cont(name='size', raw_value=0, format_func=format_size)

                def format_pb(v: DownloadProgressBar):
                    return v.get_percentage().rjust(4)
                self.pb_w = pb_cont(name='pb', current=0, done=0)
                self.pb_text_w = val_cont(name='pb_text', raw_value=DownloadProgressBar('pg normal',
                                                                                        'pg complete',
                                                                                        torrent['completed'],
                                                                                        torrent['size']),
                                          format_func=format_pb)

                def format_dl_speed(v): return "%s%s" % (natural_file_size(v, gnu=True).rjust(6), '\u25BC')
                self.dl_speed_w = val_cont(name='dlspeed', raw_value=0, format_func=format_dl_speed)

                def format_up_speed(v): return "%s%s" % (natural_file_size(v, gnu=True).rjust(6), '\u25B2')
                self.up_speed_w = val_cont(name='upspeed', raw_value=0, format_func=format_up_speed)

                def format_amt_uploaded(v): return "%s%s" % (natural_file_size(v, gnu=True).rjust(6), '\u21D1')
                self.amt_uploaded_w = val_cont(name='uploaded', raw_value=0, format_func=format_amt_uploaded)

                def format_ratio(v): return "R %.2f" % v
                self.ratio_w = val_cont(name='ratio', raw_value=0, format_func=format_ratio)

                def format_leech_num(v): return "L %3d" % v
                self.leech_num_w = val_cont(name='num_leechs', raw_value=0, format_func=format_leech_num)

                def format_seed_num(v): return "S %3d" % v
                self.seed_num_w = val_cont(name='num_seeds', raw_value=0, format_func=format_seed_num)

                def format_eta(v):
                    return "ETA %s" % (pretty_time_delta(seconds=v) if v < 8640000 else '\u221E').ljust(6)
                self.eta_w = val_cont(name='eta', raw_value=8640000, format_func=format_eta)

                def format_category(v): return str(v)
                self.category_w = val_cont(name='category', raw_value="", format_func=format_category)

                self.pb_info_list = [
                    # state
                    (len(self.state_w), self.state_w),
                    # size
                    (len(self.size_w), self.size_w),
                    # progress percentage
                    (pb_len, self.pb_w),
                    # dl speed
                    (len(self.dl_speed_w), self.dl_speed_w),
                    # up speed
                    (len(self.up_speed_w), self.up_speed_w),
                    # amount uploaded
                    (len(self.amt_uploaded_w), self.amt_uploaded_w),
                    # share ratio
                    (len(self.ratio_w), self.ratio_w),
                    # seeders
                    (len(self.seed_num_w), self.seed_num_w),
                    # leechers
                    (len(self.leech_num_w), self.leech_num_w),
                    # ETA
                    (len(self.eta_w), self.eta_w),
                ]

                self.pb_full_info_list = [(len(self.name_w), self.name_w)]
                self.pb_full_info_list.extend(self.pb_info_list)
                self.pb_full_info_list.append(self.category_w)

                self.text_pb_info_list = list(self.pb_full_info_list)
                self.text_pb_info_list.pop(3)
                self.text_pb_info_list.insert(3, (len(self.pb_text_w), self.pb_text_w))

                super(TorrentListBox.TorrentRow.TorrentInfoColumns, self).__init__(self.pb_full_info_list,
                                                                                   dividechars=1,
                                                                                   focus_column=None,
                                                                                   min_width=1, box_columns=None)

                self.update(torrent)

            def update(self, torrent: AttrDict):
                for w in self.contents:
                    e = w[0]
                    e.update(torrent)

            def keypress(self, size, key):
                """Ignore keypresses by just returning key."""
                log_keypress(self, key)
                return key

            class TorrentInfoColumnValueContainer(SelectableText):
                def __init__(self, name, raw_value, format_func):
                    super(TorrentListBox.TorrentRow.TorrentInfoColumns.TorrentInfoColumnValueContainer, self).__init__(
                        "", wrap=uw.CLIP)

                    self.name = name
                    self.format_func = format_func

                    self._raw_value = None
                    self.raw_value = raw_value

                def __len__(self):
                    return len(self.text)

                @property
                def raw_value(self):
                    return self._raw_value

                @raw_value.setter
                def raw_value(self, v):
                    self._raw_value = v
                    self.set_text(self.format_func(v))

                def update(self, torrent: AttrDict):
                    try:
                        if self.name == 'blank':
                            pass
                        elif self.name == "pb_text":
                            self.raw_value = DownloadProgressBar('pg normal',
                                                                 'pg complete',
                                                                 torrent['completed'],
                                                                 torrent['size'])
                        else:
                            self.raw_value = torrent[self.name]
                    except KeyError:
                        logger.info("Failed to update '%s' torrent info column" % self.name)

            class TorrentInfoColumnPBContainer(DownloadProgressBar):
                def __init__(self, name, current, done):
                    self.name = name
                    super(TorrentListBox.TorrentRow.TorrentInfoColumns.TorrentInfoColumnPBContainer, self).__init__(
                        'pg normal',
                        'pg complete',
                        current=current,
                        done=done if done != 0 else 100)

                def __len__(self):
                    return len(self.get_pb_text())

                def get_pb_text(self):
                    return self.get_percentage().rjust(4)

                def update(self, torrent: AttrDict):
                    try:
                        self.current = torrent['completed']
                        self.done = torrent['size'] if torrent['size'] != 0 else 100
                    except KeyError:
                        logger.info("Failed to update 'progress bar' torrent info column")


class TorrentWindow(uw.Columns):
    def __init__(self, main, torrent_hash, torrent):

        self.tabs = {"General": TorrentWindow.GeneralWindow(torrent_hash=torrent_hash),  #  uw.Filler(SelectableText("This is the general window")),
                     "Trackers": uw.Filler(SelectableText("This is the trackers window")),
                     "Peers": uw.Filler(SelectableText("This is the peers window")),
                     "Content": uw.Filler(SelectableText("This is the content window")),
                     }

        self.tabs_column_w = TorrentWindow.TorrentTabs(list(self.tabs.keys()))
        self.content_column = self.tabs['General']

        columns_list = [(uw.WEIGHT, 10, self.tabs_column_w),
                        (uw.WEIGHT, 90, self.content_column)]

        super(TorrentWindow, self).__init__(columns_list, dividechars=3, focus_column=0,
                                            min_width=15, box_columns=None)

        self.main = main
        self.torrent = torrent
        self.torrent_hash = torrent_hash

        torrent_window_tab_change.connect(receiver=self.switch_tab_window)

        self.main.daemon.add_sync_torrent_hash(torrent_hash=torrent_hash)

    def switch_tab_window(self, sender, tab=None):
        if tab is None:
            return
        self.content_column = self.tabs[tab]
        self.contents[1] = (self.content_column,
                            self.options(width_type=uw.WEIGHT, width_amount=90, box_widget=False)
                            )

    def keypress(self, size, key):
        log_keypress(self, key)
        key = super(TorrentWindow, self).keypress(size, key)
        if key in ['esc', 'left']:
            self.return_to_torrent_list()
            return None
        return key

    def return_to_torrent_list(self):
        self.main.daemon.remove_sync_torrent_hash(torrent_hash=self.torrent_hash)
        blinker.signal(self.torrent_hash).disconnect(self.tabs["General"].update)
        self.main.app_window.body = self.main.app_window.torrent_list_w

    class TorrentTabs(uw.ListBox):
        def __init__(self, tabs: list):
            tabs_list_for_walker = [uw.Text("")]
            for i, tab_name in enumerate(tabs):
                tabs_list_for_walker.extend(
                    [
                        uw.AttrMap(SelectableText(tab_name,
                                                  align=uw.CENTER,
                                                  wrap=uw.CLIP),
                                   '',
                                   focus_map='selected'),
                        uw.Text("")
                    ]
                )
            self.list_walker = uw.SimpleFocusListWalker(tabs_list_for_walker)
            super(TorrentWindow.TorrentTabs, self).__init__(self.list_walker)

            self.__selected_tab_pos = None

        def keypress(self, size, key):
            log_keypress(self, key)
            key = super(TorrentWindow.TorrentTabs, self).keypress(size, key)

            # Add 'selected' AttrMap to newly focused tab
            #  and remove 'selected'' AttrMap from previously focused tab
            if self.focus_position != self.__selected_tab_pos:
                if self.__selected_tab_pos is not None:
                    tab_text = self.list_walker[self.__selected_tab_pos].base_widget.get_text()[0]
                    new_tab = uw.AttrMap(
                        SelectableText(tab_text, align=uw.CENTER),
                        '',
                        focus_map='selected')
                    self.list_walker[self.__selected_tab_pos] = new_tab
                self.__selected_tab_pos = self.focus_position
                tab_text = self.list_walker[self.__selected_tab_pos].base_widget.get_text()[0]
                new_tab = uw.AttrMap(
                    SelectableText(tab_text, align=uw.CENTER),
                    'selected',
                    focus_map='selected')
                self.list_walker[self.__selected_tab_pos] = new_tab

                torrent_window_tab_change.send("torrent window tabs", tab=tab_text)
            return key

    class GeneralWindow(uw.Pile):
        def __init__(self, torrent_hash: str):
            self.updatable_widgets = []
            self.create_widgets()

            # TODO: layout needs updating....obviously
            self.updatable_widgets = [uw.Filler(w) for w in self.updatable_widgets]
            super(TorrentWindow.GeneralWindow, self).__init__(self.updatable_widgets)

            blinker.signal(torrent_hash).connect(receiver=self.update)

        def create_widgets(self):
            val_cont = TorrentWindow.GeneralWindow.TorrentGeneralValueContainer

            def format_time_active(time_elapsed=0): return format_time_delta(seconds=time_elapsed)
            def format_reannounce(reannounce=0): return format_time_delta(seconds=reannounce)
            def format_eta(eta=8640000): return format_time_delta(seconds=eta, infinity=True)
            def format_time_delta(seconds=0, infinity=False):
                if infinity is True: return "%s" % (pretty_time_delta(seconds=seconds) if seconds < 8640000 else '\u221E')
                return "%s" % pretty_time_delta(seconds=seconds)

            def format_uploaded(total_uploaded=0, total_uploaded_session=0): return format_up_or_down(total=total_uploaded, total_session=total_uploaded_session)
            def format_downloaded(total_downloaded=0, total_downloaded_session=0): return format_up_or_down(total=total_downloaded, total_session=total_downloaded_session)
            def format_up_or_down(total=0, total_session=0):
                return "%s (%s this session)" % (format_size(size_bytes=total),
                                                 format_size(size_bytes=total_session))
            def format_upload_speed(up_speed=0, up_speed_avg=0): return format_up_or_down_speed(speed=up_speed, speed_avg=up_speed_avg)
            def format_download_speed(dl_speed=0, dl_speed_avg=0): return format_up_or_down_speed(speed=dl_speed, speed_avg=dl_speed_avg)
            def format_up_or_down_speed(speed=0, speed_avg=0):
                return "%s/s (%s/s avg)" % (format_size(size_bytes=speed),
                                            format_size(size_bytes=speed_avg))
            def format_up_limit(up_limit=0): return format_up_or_down_limit(limit=up_limit)
            def format_down_limit(dl_limit=0): return format_up_or_down_limit(limit=dl_limit)
            def format_up_or_down_limit(limit=0):
                if limit == -1: return '\u221E'
                return "%s/s" % format_size(size_bytes=limit)
            def format_wasted(total_wasted=0): return format_size(size_bytes=total_wasted)
            def format_total_size(total_size=0): return format_size(size_bytes=total_size)
            def format_size(size_bytes=0):
                return natural_file_size(size_bytes, binary=True)

            def format_share_ratio(share_ratio=0):
                return "%.2f" % share_ratio

            def format_connections(nb_connections=0, nb_connections_limit=0):
                return "%d (%d max)" % (nb_connections, nb_connections_limit)

            def format_seeds(seeds=0, seeds_total=0): return format_seeds_or_peers(num=seeds, total=seeds_total)
            def format_peers(peers=0, peers_total=0): return format_seeds_or_peers(num=peers, total=peers_total)
            def format_seeds_or_peers(num=0, total=0):
                return "%d (%d total)" % (num, total)

            def format_last_seen(last_seen=-1): return format_date_time(seconds=last_seen)
            def format_added_on(addition_date=-1): return format_date_time(seconds=addition_date)
            def format_completed_on(completion_date=-1): return format_date_time(seconds=completion_date)
            def format_creation_date(creation_date=-1): return format_date_time(seconds=creation_date)
            def format_date_time(seconds):
                if seconds == -1:
                    return ""
                dt = datetime.fromtimestamp(seconds)
                return dt.strftime("%m/%d/%y %H:%M:%S")

            def format_hash(hash=""): return format_string(string=hash)
            def format_save_path(save_path=""): return format_string(string=save_path)
            def format_comment(comment=""): return format_string(string=comment)
            def format_created_by(created_by=""): return format_string(string=created_by)
            def format_string(string): return string

            def format_pieces(pieces_num=0, piece_size=0, pieces_have=0):
                return "%d x %s (have %d)" % (pieces_have, format_size(size_bytes=piece_size), pieces_have)

            # TRANSFER
            self.time_active_w = val_cont(data_elements=['time_elapsed'],
                                     caption="Time Active",
                                     format_func=format_time_active)
            self.updatable_widgets.append(self.time_active_w)

            self.downloaded_w = val_cont(data_elements=['total_downloaded', 'total_downloaded_session'],
                                    caption="Downloaded",
                                    format_func=format_downloaded)
            self.updatable_widgets.append(self.downloaded_w)

            self.download_speed_w = val_cont(data_elements=['dl_speed', 'dl_speed_avg'],
                                        caption="Download Speed",
                                        format_func=format_download_speed)
            self.updatable_widgets.append(self.download_speed_w)

            self.download_limit_w = val_cont(data_elements=['dl_limit'],
                                        caption="Download Limit",
                                        format_func=format_down_limit)
            self.updatable_widgets.append(self.download_limit_w)

            self.share_ratio_w = val_cont(data_elements=['share_ratio'],
                                     caption="Share Ratio",
                                     format_func=format_share_ratio)
            self.updatable_widgets.append(self.share_ratio_w)

            self.eta_w = val_cont(data_elements=['eta'],
                             caption='ETA',
                             format_func=format_eta)
            self.updatable_widgets.append(self.eta_w)

            self.uploaded_w = val_cont(data_elements=['total_uploaded', 'total_uploaded_session'],
                                  caption="Uploaded",
                                  format_func=format_uploaded)
            self.updatable_widgets.append(self.uploaded_w)

            self.upload_speed_w = val_cont(data_elements=['up_speed', 'up_speed_avg'],
                                      caption="Upload Speed",
                                      format_func=format_upload_speed)
            self.updatable_widgets.append(self.upload_speed_w)

            self.upload_limit_w = val_cont(data_elements=['up_limit'],
                                      caption="Upload Limit",
                                      format_func=format_up_limit)
            self.updatable_widgets.append(self.upload_limit_w)

            self.reannounce_w = val_cont(data_elements=['reannounce'],
                                    caption="Reannounce In",
                                    format_func=format_reannounce)
            self.updatable_widgets.append(self.reannounce_w)

            self.connections_w = val_cont(data_elements=['nb_connections', 'nb_connections_limit'],
                                     caption="Connections",
                                     format_func=format_connections)
            self.updatable_widgets.append(self.connections_w)

            self.seeds_w = val_cont(data_elements=['seeds', 'seeds_total'],
                               caption="Seeds",
                               format_func=format_seeds)
            self.updatable_widgets.append(self.seeds_w)

            self.peers_w = val_cont(data_elements=['peers', 'peers_total'],
                               caption="Peers",
                               format_func=format_peers)
            self.updatable_widgets.append(self.peers_w)

            self.wasted_w = val_cont(data_elements=['total_wasted'],
                                caption="Wasted",
                                format_func=format_wasted)
            self.updatable_widgets.append(self.wasted_w)

            self.last_seen_w = val_cont(data_elements=['last_seen'],
                                   caption='Last Seen Complete',
                                   format_func=format_last_seen)
            self.updatable_widgets.append(self.last_seen_w)

            # INFORMATION
            self.total_size_w = val_cont(data_elements=['total_size'],
                                    caption="Total Size",
                                    format_func=format_total_size)
            self.updatable_widgets.append(self.total_size_w)

            self.added_on_w = val_cont(data_elements=['addition_date'],
                                       caption="Added On",
                                       format_func=format_added_on)
            self.updatable_widgets.append(self.added_on_w)

            self.torrent_hash_w = val_cont(data_elements=['hash'],
                                           caption="Torrent Hash",
                                           source="torrent",
                                           format_func=format_hash)
            self.updatable_widgets.append(self.torrent_hash_w)

            self.save_path_w = val_cont(data_elements=['save_path'],
                                        caption="Save Path",
                                        format_func=format_save_path)

            self.comment_w = val_cont(data_elements=['comment'],
                                      caption="Comment",
                                      format_func=format_comment)
            self.updatable_widgets.append(self.comment_w)

            self.pieces_w = val_cont(data_elements=['pieces_num', 'piece_size', 'pieces_have'],
                                     caption="Pieces",
                                     format_func=format_pieces)
            self.updatable_widgets.append(self.pieces_w)

            self.completed_on_w = val_cont(data_elements=['completion_date'],
                                           caption='Completed On',
                                           format_func=format_completed_on)
            self.updatable_widgets.append(self.completed_on_w)

            self.created_by_w = val_cont(data_elements=['created_by'],
                                         caption="Created By",
                                         format_func=format_created_by)
            self.updatable_widgets.append(self.created_by_w)

            self.created_on_w = val_cont(data_elements=['creation_date'],
                                         caption="Created On",
                                         format_func=format_creation_date)
            self.updatable_widgets.append(self.created_on_w)

        def update(self, sender, torrent: dict, properties: dict):
            start_time = time()
            for w in self.updatable_widgets:
                w.base_widget.update(torrent=torrent, properties=properties)
            if IS_TIMING_LOGGING_ENABLED:
                logger.info("Refreshing Torrent Window General (%.2f)" % (time() - start_time))

        class TorrentGeneralValueContainer(uw.Text):
            def __init__(self, data_elements: list, caption: str, format_func, source: str = "properties"):
                super(TorrentWindow.GeneralWindow.TorrentGeneralValueContainer, self).__init__("", wrap=uw.CLIP)

                self.data_elements = data_elements
                self.source = source  # torrent or properties
                self.caption = caption
                self.format_func = format_func
                # initialize widget with default values
                #  update should be called immediately after instantiation
                self.raw_value = dict()

            def __len__(self):
                return len(self.text)

            @property
            def raw_value(self):
                return self._raw_value

            @raw_value.setter
            def raw_value(self, values: dict):
                self._raw_value = values
                self.set_text("%s: %s" % (self.caption, self.format_func(**values)))

            def update(self, torrent: dict, properties: dict):
                values = dict()
                source = torrent if self.source == "torrent" else properties
                for e in self.data_elements:
                    # TODO: add if back in....want to crash for now to find bugs
                    #if e in source:
                    values[e] = source[e]
                if self.raw_value != values:
                    logger.info("Updating %s" % self.__class__.__name__)
                    self.raw_value = values


class TorrentOptions(uw.ListBox):
    client: Connector

    def __init__(self, torrent_list_box_w: TorrentListBox, torrent_hash, torrent):
        self.torrent_list_box_w = torrent_list_box_w
        self.main = self.torrent_list_box_w.main
        self.torrent_hash = torrent_hash
        self.torrent = torrent
        self.client = self.torrent_list_box_w.client

        self.torrent = AttrDict(torrent)

        self.delete_files_w = None

        categories = {x: x for x in list(self.main.server.categories.keys())}
        categories["<no category>"] = "<no category>"

        self.original_location = self.torrent.save_path
        self.location_w = uw.Edit(caption="Save path: ",
                                  edit_text=self.original_location)
        self.original_name = self.torrent.name
        self.rename_w = uw.Edit(caption="Rename: ",
                                edit_text=self.original_name)
        self.original_autotmm_state = self.torrent.auto_tmm
        self.autotmm_w = uw.CheckBox("Automatic Torrent Management",
                                     state=self.original_autotmm_state)
        self.original_super_seeding_state = self.torrent.super_seeding
        self.super_seeding_w = uw.CheckBox("Super Seeding Mode",
                                           state=self.original_super_seeding_state)
        self.original_upload_rate_limit = self.torrent.up_limit
        self.upload_rate_limit_w = uw.IntEdit(caption="Upload Rate Limit (Kib/s)  : ",
                                              default=int(
                                                  self.original_upload_rate_limit / 1024) if self.original_upload_rate_limit != -1 else "")
        self.original_download_rate_limit = self.torrent.dl_limit
        self.download_rate_limit_w = uw.IntEdit(caption="Download Rate Limit (Kib/s): ",
                                                default=int(
                                                    self.original_download_rate_limit / 1024) if self.original_download_rate_limit != -1 else "")
        # TODO: accommodate share ratio and share time
        self.original_share_ratio = self.torrent.ratio_limit
        self.share_ratio_dropdown_w = panwid.Dropdown(items=[("Global Limit", -2), ("Unlimited", -1), ("Specify", 0)],
                                                      label="Share Ratio: ",
                                                      default=self.torrent.ratio_limit if self.torrent.ratio_limit in [
                                                          -2, -1] else 0)
        if self.torrent.ratio_limit >= 0:
            self.original_share_ratio_percentage = int(self.torrent.ratio_limit * 100)
            self.original_share_minutes = self.torrent.seeding_time_limit
        else:
            self.original_share_ratio_percentage = None
            self.original_share_minutes = None
        self.share_ratio_limit_w = uw.IntEdit(caption="Share ratio limit (%): ",
                                              default=self.original_share_ratio_percentage)
        self.share_ratio_minutes_w = uw.IntEdit(caption="Share ratio minutes: ", default=self.original_share_minutes)
        self.original_category = self.torrent.category if self.torrent.category != "" else "<no category>"
        self.category_w = panwid.Dropdown(items=categories,
                                          label="Category",
                                          default=self.original_category,
                                          auto_complete=True)

        super(TorrentOptions, self).__init__(uw.SimpleFocusListWalker(
            [
                uw.Divider(),
                uw.Columns(
                    [
                        uw.Padding(uw.Text('')),
                        (10, uw.AttrMap(ButtonWithoutCursor("Resume",
                                                            on_press=self.resume_torrent),
                                        '', focus_map='selected')),
                        (16, uw.AttrMap(ButtonWithoutCursor("Force Resume",
                                                            on_press=self.force_resume_torrent),
                                        '', focus_map='selected')),
                        (9, uw.AttrMap(ButtonWithoutCursor("Pause",
                                                           on_press=self.pause_torrent),
                                       '', focus_map='selected')),
                        uw.Padding(uw.Text('')),
                    ],
                    dividechars=2
                ),
                uw.Divider(),
                uw.Columns(
                    [
                        uw.Padding(uw.Text('')),
                        (10, uw.AttrMap(ButtonWithoutCursor("Delete",
                                                            on_press=self.delete_torrent),
                                        '', focus_map='selected')),
                        (11, uw.AttrMap(ButtonWithoutCursor("Recheck",
                                                            on_press=self.recheck_torrent),
                                        '', focus_map='selected')),
                        (14, uw.AttrMap(ButtonWithoutCursor("Reannounce",
                                                            on_press=self.reannounce_torrent),
                                        '', focus_map='selected')),
                        uw.Padding(uw.Text('')),
                    ],
                    dividechars=2
                ),
                uw.Divider(),
                self.location_w,
                uw.Divider(),
                self.rename_w,
                uw.Divider(),
                uw.Columns(
                    [
                        uw.Padding(uw.Text('')),
                        (33, self.autotmm_w),
                        (23, self.super_seeding_w),
                        uw.Padding(uw.Text('')),
                    ],
                    dividechars=2
                ),
                uw.Divider(),
                self.share_ratio_dropdown_w,
                self.share_ratio_limit_w,
                self.share_ratio_minutes_w,
                uw.Divider(),
                self.upload_rate_limit_w,
                self.download_rate_limit_w,
                uw.Divider(),
                self.category_w,
                uw.Divider(),
                uw.Divider(),
                uw.Columns(
                    [
                        uw.Padding(uw.Text('')),
                        (6, uw.AttrMap(ButtonWithoutCursor("OK",
                                                           on_press=self.apply_settings),
                                       '', focus_map='selected')),
                        (10, uw.AttrMap(ButtonWithoutCursor("Cancel",
                                                            on_press=self.close_window),
                                        '', focus_map='selected'))
                    ],
                    dividechars=2,
                )
            ]
        ))

    def keypress(self, size, key):
        log_keypress(self, key)
        key = super(TorrentOptions, self).keypress(size, key)
        if key == 'esc':
            self.close_window()

    def apply_settings(self, b):

        new_location = self.location_w.get_edit_text()
        new_name = self.rename_w.get_edit_text()
        new_autotmm_state = self.autotmm_w.get_state()
        new_super_seeding_state = self.super_seeding_w.get_state()
        new_share_ratio = self.share_ratio_dropdown_w.selected_value
        if self.share_ratio_limit_w.get_edit_text():
            new_share_ratio_percentage = int(self.share_ratio_limit_w.get_edit_text()) / 100
        else:
            new_share_ratio_percentage = self.original_share_ratio_percentage
        if self.share_ratio_minutes_w.get_edit_text():
            new_share_ratio_minutes = self.share_ratio_minutes_w.get_edit_text()
        else:
            new_share_ratio_minutes = self.original_share_minutes
        if self.upload_rate_limit_w.get_edit_text() != "":
            new_upload_rate_limit = int(self.upload_rate_limit_w.get_edit_text()) * 1024
        else:
            new_upload_rate_limit = self.original_upload_rate_limit
        if self.download_rate_limit_w.get_edit_text() != "":
            new_download_rate_limit = int(self.download_rate_limit_w.get_edit_text()) * 1024
        else:
            new_download_rate_limit = self.original_download_rate_limit
        new_category = self.category_w.selected_label

        if new_location != self.original_location:
            logger.info("Setting new location: %s (%s)" % (new_location, self.torrent_hash))
            self.client.torrents_set_location(location=new_location, torrent_ids=self.torrent_hash)

        if new_name != self.original_name:
            logger.info("Setting new name: %s (%s)" % (new_name, self.torrent_hash))
            self.client.torrent_rename(new_name=new_name, torrent_id=self.torrent_hash)

        if new_autotmm_state is not self.original_autotmm_state:
            logger.info("Setting Auto TMM: %s (%s)" % (new_autotmm_state, self.torrent_hash))
            self.client.torrents_set_automatic_torrent_management(enable=new_autotmm_state,
                                                                  torrent_ids=self.torrent_hash)

        if new_super_seeding_state is not self.original_super_seeding_state:
            logger.info("Setting super seeding: %s (%s)" % (new_super_seeding_state, self.torrent_hash))
            self.client.torrents_set_super_seeding(enable=new_super_seeding_state, torrent_ids=self.torrent_hash)

        if new_upload_rate_limit != self.original_upload_rate_limit:
            logger.info("Setting new upload rate: %s (%s)" % (new_upload_rate_limit, self.torrent_hash))
            self.client.torrents_set_upload_limit(limit=new_upload_rate_limit, torrent_ids=self.torrent_hash)

        if new_download_rate_limit != self.original_download_rate_limit:
            logger.info("Setting new download rate: %s (%s)" % (new_download_rate_limit, self.torrent_hash))
            self.client.torrents_set_download_limit(limit=new_download_rate_limit, torrent_ids=self.torrent_hash)

        if new_category != self.original_category:
            if new_category == '<no category>':
                new_category = ""
            logger.info("Setting new category: %s (%s)" % (new_category, self.torrent_hash))
            self.client.torrents_set_category(category=new_category, torrent_ids=self.torrent_hash)

        if new_share_ratio != self.original_share_ratio:
            if new_share_ratio in [-1, -2]:
                self.client.torrents_set_share_limits(ratio_limit=new_share_ratio,
                                                      seeding_time_limit=new_share_ratio,
                                                      torrent_ids=self.torrent_hash)
            else:
                self.client.torrents_set_share_limits(ratio_limit=new_share_ratio_percentage,
                                                      seeding_time_limit=new_share_ratio_minutes,
                                                      torrent_ids=self.torrent_hash)

        self.reset_screen_to_torrent_list_window()

    def close_window(self, b=None):
        self.reset_screen_to_torrent_list_window()

    def resume_torrent(self, b):
        self.client.torrents_resume(torrent_ids=self.torrent_hash)
        self.reset_screen_to_torrent_list_window()

    def force_resume_torrent(self, b):
        self.client.torrents_force_resume(torrent_ids=self.torrent_hash)
        self.reset_screen_to_torrent_list_window()

    def delete_torrent(self, b):
        self.delete_files_w = uw.CheckBox(label="Delete Files")
        self.main.loop.widget = uw.Overlay(
            top_w=uw.LineBox(
                uw.ListBox(
                    uw.SimpleFocusListWalker(
                        [
                            uw.Divider(),
                            self.delete_files_w,
                            uw.Divider(),
                            uw.Columns(
                                [
                                    uw.Padding(uw.Text('')),
                                    (6, uw.AttrMap(ButtonWithoutCursor("OK",
                                                                       on_press=self.confirm_delete),
                                                   '', focus_map='selected')),
                                    (10, uw.AttrMap(ButtonWithoutCursor("Cancel",
                                                                        on_press=self.close_delete_dialog),
                                                    '', focus_map='selected'))
                                ],
                                dividechars=2,
                            ),
                        ]
                    )
                )
            ),
            bottom_w=self.main.app_window,
            align=uw.CENTER,
            valign=uw.MIDDLE,
            width=30,
            height=10,
            min_width=20
        )

    def confirm_delete(self, b):
        delete_files = self.delete_files_w.get_state()
        self.client.torrents_delete(torrent_ids=self.torrent_hash, delete_files=delete_files)
        self.reset_screen_to_torrent_list_window()

    def close_delete_dialog(self, b):
        self.main.loop.widget = self.main.app_window

    def pause_torrent(self, b):
        self.client.torrents_pause(torrent_ids=self.torrent_hash)
        self.reset_screen_to_torrent_list_window()

    def recheck_torrent(self, b):
        self.client.torrents_recheck(torrent_ids=self.torrent_hash)
        self.reset_screen_to_torrent_list_window()

    def reannounce_torrent(self, b):
        self.client.torrents_reannounce(torrent_ids=self.torrent_hash)
        self.reset_screen_to_torrent_list_window()

    def reset_screen_to_torrent_list_window(self):
        update_torrent_list_now.send("torrent menu")
        self.main.loop.widget = self.main.app_window


class TorrentAdd(uw.ListBox):
    def __init__(self, main):
        self.main = main

        categories = {x: x for x in list(self.main.server.categories.keys())}
        categories["<no category>"] = "<no category>"

        prefs = self.main.daemon.get_server_preferences()

        self.torrent_file_w = uw.Edit(caption="Torrent file path: ")
        self.torrent_url_w = uw.Edit(caption="Torrent url: ")
        self.autotmm_w = uw.CheckBox("Automatic Torrent Management",
                                     state=prefs.auto_tmm_enabled)
        self.location_w = uw.Edit(caption="Save path: ",
                                  edit_text=prefs.save_path)
        self.name_w = uw.Edit(caption="Custom name: ")
        self.category_w = panwid.Dropdown(items=categories,
                                          label="Category",
                                          default="<no category>",
                                          auto_complete=True)
        self.start_torrent_w = uw.CheckBox("Start Torrent",
                                           state=(not prefs.start_paused_enabled))
        self.download_in_sequential_order_w = uw.CheckBox("Download in Sequential Order")
        self.download_first_last_first_w = uw.CheckBox("Download First and Last Pieces First")
        self.skip_hash_check_w = uw.CheckBox("Skip Hash Check")
        self.create_subfolder_w = uw.CheckBox("Create Subfolder",
                                              state=prefs.create_subfolder_enabled)
        self.upload_rate_limit_w = uw.IntEdit(caption="Upload Rate Limit (Kib/s)  : ")
        self.download_rate_limit_w = uw.IntEdit(caption="Download Rate Limit (Kib/s): ")

        super(TorrentAdd, self).__init__(
            uw.SimpleFocusListWalker(
                [
                    self.torrent_file_w,
                    self.torrent_url_w,
                    uw.Divider(),
                    self.location_w,
                    self.name_w,
                    uw.Divider(),
                    self.category_w,
                    uw.Divider(),
                    self.autotmm_w,
                    self.start_torrent_w,
                    self.create_subfolder_w,
                    self.skip_hash_check_w,
                    self.download_in_sequential_order_w,
                    self.download_first_last_first_w,
                    uw.Divider(),
                    self.upload_rate_limit_w,
                    self.download_rate_limit_w,
                    uw.Divider(),
                    uw.Divider(),
                    uw.Columns(
                        [
                            uw.Padding(uw.Text('')),
                            (6, uw.AttrMap(ButtonWithoutCursor("OK",
                                                               on_press=self.add_torrent),
                                           '', focus_map='selected')),
                            (10, uw.AttrMap(ButtonWithoutCursor("Cancel",
                                                                on_press=self.close_window),
                                            '', focus_map='selected'))
                        ],
                        dividechars=2,
                    ),
                ]
            )
        )

    def add_torrent(self, b):
        torrent_file = self.torrent_file_w.get_edit_text()
        torrent_url = self.torrent_url_w.get_edit_text()
        is_autotmm = self.autotmm_w.get_state()
        save_path = self.location_w.get_edit_text()
        name = self.name_w.get_edit_text()
        category = self.category_w.selected_label
        is_start_torrent = self.start_torrent_w.get_state()
        is_seq_download = self.download_in_sequential_order_w.get_state()
        is_first_last_download = self.download_first_last_first_w.get_state()
        is_skip_hash = self.skip_hash_check_w.get_state()
        is_create_subfolder = self.create_subfolder_w.get_state()
        upload_limit = self.upload_rate_limit_w.get_edit_text()
        download_limit = self.download_rate_limit_w.get_edit_text()

        try:
            upload_limit = int(upload_limit) * 1024
        except ValueError:
            upload_limit = None
        try:
            download_limit = int(download_limit) * 1024
        except ValueError:
            download_limit = None

        outcome = self.main.torrent_client.torrents_add(
            urls=torrent_url if torrent_url else None,
            torrent_files=torrent_file if torrent_file else None,
            save_path=save_path if save_path else None,
            cookie=None,
            category=category if category != "<no category>" else None,
            is_skip_checking=is_skip_hash,
            is_paused=(not is_start_torrent),
            is_root_folder=is_create_subfolder,
            rename=name if name else None,
            upload_limit=upload_limit,
            download_limit=download_limit,
            use_auto_torrent_management=is_autotmm,
            is_sequential_download=is_seq_download,
            is_first_last_piece_priority=is_first_last_download
        )
        self.reset_screen_to_torrent_list_window()

    def keypress(self, size, key):
        log_keypress(self, key)
        key = super(TorrentAdd, self).keypress(size, key)
        if key == 'esc':
            self.close_window()
        return key

    def close_window(self, b=None):
        self.reset_screen_to_torrent_list_window()

    def reset_screen_to_torrent_list_window(self):
        update_torrent_list_now.send("torrent add")
        self.main.loop.widget = self.main.app_window
