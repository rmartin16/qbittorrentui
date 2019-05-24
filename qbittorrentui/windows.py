import urwid
from socket import getfqdn
import logging
from attrdict import AttrDict
import panwid

from time import time

from qbittorrentui.connector import Connector
from qbittorrentui.connector import ConnectorError
from qbittorrentui.connector import LoginFailed
from qbittorrentui.events import sync_maindata_ready
from qbittorrentui.events import rebuild_torrent_list_now
from qbittorrentui.events import refresh_torrent_list_with_remote_data_now
from qbittorrentui.events import request_to_initialize_torrent_list
from qbittorrentui.events import details_ready


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


class ButtonLabel(urwid.SelectableIcon):
    def set_text(self, label):
        self.__super.set_text(label)
        self._cursor_position = len(label) + 1


class ButtonWithoutCursor(urwid.Button):
    button_left = "["
    button_right = "]"

    def __init__(self, label, on_press=None, user_data=None):
        self._label = ButtonLabel("")
        cols = urwid.Columns([
            ('fixed', len(self.button_left), urwid.Text(self.button_left)),
            self._label,
            ('fixed', len(self.button_right), urwid.Text(self.button_right))],
            dividechars=1)
        super(urwid.Button, self).__init__(cols)

        if on_press:
            urwid.connect_signal(self, 'click', on_press, user_data)

        self.set_label(label)


class DownloadProgressBar(urwid.ProgressBar):
    def get_text(self):
        return "%s %s" % (natural_file_size(self.current, gnu=True).rjust(7),
                          ("(%s)" % self.get_percentage()).ljust(6))

    def get_percentage(self):
        percent = int(self.current * 100 / self.done)
        return "%s%s" % (percent, "%")


class SelectableText(urwid.Text):
    def selectable(self):
        return True

    @staticmethod
    def keypress(size, key, *args, **kwargs):
        return key


class ConnectWindow(urwid.Pile):
    def __init__(self, main):
        self.main = main
        self.client = main.torrent_client

        self.error_w = urwid.Text("", align=urwid.CENTER)
        self.hostname_w = urwid.Edit("Hostname: ", edit_text=self.client.host)
        self.port_w = urwid.Edit("Port: ")
        self.username_w = urwid.Edit("Username: ")
        self.password_w = urwid.Edit("Password: ", mask='*')

        super(ConnectWindow, self).__init__(
            [
                urwid.Text("Enter connection information",
                           align=urwid.CENTER),
                urwid.Divider(),
                urwid.AttrMap(self.error_w, 'light red on default'),
                urwid.Divider(),
                self.hostname_w,
                self.port_w,
                self.username_w,
                self.password_w,
                urwid.Divider(),
                urwid.Columns([
                    urwid.Padding(urwid.Text("")),
                    (6, urwid.AttrMap(ButtonWithoutCursor("OK",
                                                          on_press=self.apply_settings),
                                      '', focus_map='selected')),
                    (10, urwid.AttrMap(ButtonWithoutCursor("Cancel",
                                                           on_press=self.leave_app),
                                       '', focus_map='selected')),
                    urwid.Padding(urwid.Text("")),
                ], dividechars=3),
                urwid.Divider(),
                urwid.Divider(),
            ]
        )

    def leave_app(self, _):
        raise urwid.ExitMainLoop

    def apply_settings(self, args):
        try:
            port = self.port_w.get_edit_text()
            self.client.connect(host="%s%s" % (self.hostname_w.get_edit_text(), ":%s" % port if port else ""),
                                username=self.username_w.get_edit_text(),
                                password=self.password_w.get_edit_text())
            self.main.loop.widget = self.main.torrent_list_window
            request_to_initialize_torrent_list.send('connect window')
        except LoginFailed:
            self.error_w.set_text("Error: login failed")
        except ConnectorError as e:
            self.error_w.set_text("Error: %s" % e)


class TorrentListWindow(urwid.Frame):
    def __init__(self, main):
        """

        :param main:
        :type main: main.Main()
        """
        self.main = main
        self.client = main.torrent_client

        # initialize poll refresh data
        self.md = AttrDict()
        self.torrents_info = AttrDict()
        self.server_state = AttrDict()
        self.categories = AttrDict()
        self.torrent_manager_version = ""
        self.connection_port = ""
        self.__width = None

        # initialize title and status bars
        self.title_w = urwid.Text('')
        self.status_bar_w = urwid.Text('')

        # initialize torrent list
        self.torrent_list_walker_w = urwid.SimpleFocusListWalker([])
        self.torrent_list_w = TorrentListWindow.TorrentList(self.torrent_list_walker_w)

        #  Set up torrent status tabs
        self.torrent_tabs_list = [
            urwid.AttrMap(urwid.Filler(SelectableText('All',
                                                      align=urwid.CENTER)), 'selected',
                          focus_map='selected'),
            urwid.AttrMap(urwid.Filler(SelectableText('Downloading',
                                                      align=urwid.CENTER)), '',
                          focus_map='selected'),
            urwid.AttrMap(urwid.Filler(SelectableText('Completed',
                                                      align=urwid.CENTER)), '',
                          focus_map='selected'),
            urwid.AttrMap(urwid.Filler(SelectableText('Paused',
                                                      align=urwid.CENTER)), '',
                          focus_map='selected'),
            urwid.AttrMap(urwid.Filler(SelectableText('Active',
                                                      align=urwid.CENTER)), '',
                          focus_map='selected'),
            urwid.AttrMap(urwid.Filler(SelectableText('Inactive',
                                                      align=urwid.CENTER)), '',
                          focus_map='selected'),
            urwid.AttrMap(urwid.Filler(SelectableText('Resumed',
                                                      align=urwid.CENTER)), '',
                          focus_map='selected')
        ]
        self.torrent_tabs_w = TorrentListWindow.TorrentListTabsColumns(self.torrent_tabs_list)

        # build body
        self.torrent_list_body = urwid.Pile([(1, self.torrent_tabs_w),
                                             (1, urwid.Filler(urwid.Divider())),
                                             self.torrent_list_w])

        # signals
        details_ready.connect(receiver=self.update_details)
        rebuild_torrent_list_now.connect(receiver=self.refresh)
        request_to_initialize_torrent_list.connect(receiver=self.request_torrent_list_initialization)
        urwid.register_signal(type(self.torrent_tabs_w), 'change')
        urwid.connect_signal(self.torrent_tabs_w,
                             'change',
                             self.refresh,
                             user_args=["torrents_tabs_w change"])
        urwid.register_signal(type(self.torrent_tabs_w), 'reset list focus')
        urwid.connect_signal(self.torrent_tabs_w,
                             'reset list focus',
                             self.reset_torrent_list_focus)

        super(TorrentListWindow, self).__init__(header=self.title_w,
                                                body=self.torrent_list_body,
                                                footer=self.status_bar_w)

    class TorrentListTabsColumns(urwid.Columns):
        def __init__(self, widget_list, dividechars=0, focus_column=None):
            super(TorrentListWindow.TorrentListTabsColumns, self).__init__(widget_list, dividechars, focus_column)
            self.__selected_tab_pos = 0

        def move_cursor_to_coords(self, size, col, row):
            """Don't change focus based on coords"""
            return True

        def keypress(self, size, key):
            log_keypress(self, key)
            key = super(TorrentListWindow.TorrentListTabsColumns, self).keypress(size, key)

            focused_tab_pos = self.focus_position
            if focused_tab_pos != self.__selected_tab_pos:
                tab_text = self.contents[self.__selected_tab_pos][0].base_widget.get_text()[0]
                new_col = urwid.AttrMap(
                    urwid.Filler(SelectableText(tab_text, align=urwid.CENTER)),
                    '',
                    focus_map='selected')
                self.contents[self.__selected_tab_pos] = (new_col, ('weight', 1, False))
                self.__selected_tab_pos = focused_tab_pos
                tab_text = self.contents[self.__selected_tab_pos][0].base_widget.get_text()[0]
                new_col = urwid.AttrMap(
                    urwid.Filler(SelectableText(tab_text, align=urwid.CENTER)),
                    'selected',
                    focus_map='selected')
                self.contents[self.__selected_tab_pos] = (new_col, ('weight', 1, False))

                urwid.emit_signal(self, 'change')
                urwid.emit_signal(self, 'reset list focus')
            return key

    class TorrentList(urwid.ListBox):
        def keypress(self, size, key):
            log_keypress(self, key)
            key = super(TorrentListWindow.TorrentList, self).keypress(size, key)
            # if key == 'right':
            #    self.loop.widget = self.main.torrent_window
            #    return None
            # else:
            return key

        def get_torrent_hash_for_focused_row(self):
            focused_row, focused_row_pos = self.body.get_focus()
            if focused_row is not None:
                return focused_row.base_widget.get_torrent_hash()
            return None

    class TorrentRow(urwid.Pile):
        def __init__(self, main, widget_list, focus_item=None):
            self.__hash = None
            self.main = main
            super(TorrentListWindow.TorrentRow, self).__init__(widget_list, focus_item)

        def set_torrent_hash(self, torrent_hash):
            self.__hash = torrent_hash

        def get_torrent_hash(self):
            return self.__hash

        def open_torrent_options_window(self):

            # TODO: get torrent title from TorrentList instead of md
            #       however, TorrentRow and TorrentColumns needs to be rewritten to make that easier
            torrent_info = self.main.torrent_list_window.torrents_info[self.get_torrent_hash()]
            torrent_name = torrent_info['name']

            self.main.torrent_options_window = urwid.Overlay(
                top_w=urwid.LineBox(
                    urwid.Filler(
                        TorrentOptions(main=self.main,
                                       torrent_hash=self.get_torrent_hash())),
                    title=torrent_name
                ),
                bottom_w=self.main.torrent_list_window,
                align=urwid.CENTER,
                width=(urwid.RELATIVE, 50),
                valign=urwid.MIDDLE,
                height=25,
                min_width=75)

            self.main.loop.widget = self.main.torrent_options_window

        def keypress(self, size, key):
            log_keypress(self, key)
            if key == 'enter':
                self.open_torrent_options_window()
            return key

    class TorrentInfoColumns(urwid.Columns):
        def keypress(self, size, key):
            """Ignore keypresses by just returning key."""
            log_keypress(self, key)
            return key

    @property
    def width(self):
        if self.__width:
            return self.__width
        else:
            return self.main.get_cols_rows()[1]

    def render(self, size, focus=False):
        # catch screen resize
        if self.__width != size[0]:
            self.__width = size[0]
            # call to refresh on screen re-sizes
            rebuild_torrent_list_now.send('torrent list render')
        logger.info("Rendering Torrent List window")
        return super(TorrentListWindow, self).render(size, focus)

    def keypress(self, size, key):
        log_keypress(self, key)
        key = super(TorrentListWindow, self).keypress(size, key)
        if key in ('m', 'M'):
            pass
        return key

    def request_torrent_list_initialization(self, *a, **kw):
        """once connected to qbittorrent, initialize torrent list window"""
        sync_maindata_ready.connect(receiver=self.refresh_with_maindata)
        refresh_torrent_list_with_remote_data_now.send("initialization")

    def reset_torrent_list_focus(self, *a):
        self.torrent_list_w.set_focus(0)

    def refresh_with_maindata(self, *a, **kw):
        """
        entry point for data poller to update the torrent list

        :param a:
        :param kw:
        :return:
        """
        self.md = AttrDict(kw.pop('md', {}))
        if self.md.get('full_update', False):
            self.server_state = AttrDict(self.md.get('server_state', {}))

            self.torrents_info = AttrDict()
            for torrent_hash, torrent in self.md.get('torrents', {}).items():
                self.torrents_info[torrent_hash] = AttrDict(torrent)

            self.categories = AttrDict()
            for category_name, category in self.md.get('categories', {}).items():
                self.categories[category_name] = AttrDict(category)
        else:
            self.server_state.update(AttrDict(self.md.get('server_state', {})))

            # remove torrents no longer in qbittorrent
            for torrent_hash in self.md.get('torrents_removed', {}):
                self.torrents_info.pop(torrent_hash, None)
            # add new torrents or new torrent info
            for torrent_hash, torrent in self.md.get('torrents', {}).items():
                if torrent_hash in self.torrents_info:
                    self.torrents_info[torrent_hash].update(torrent)
                else:
                    self.torrents_info[torrent_hash] = torrent

            # remove categories no longer in qbittorrent
            for category in self.md.get('categories_removed', {}):
                self.categories.pop(category, None)
            # add new categories or new category info
            for category_name, category in self.md.get('categories', {}).items():
                if category in self.categories:
                    self.categories[category_name].update(category)
                else:
                    self.categories[category_name] = category

        rebuild_torrent_list_now.send('refresh with maindata')
        self.main.loop.draw_screen()
        self.md = AttrDict()

    def refresh(self, *a, **kw):
        refresh_start_time = time()
        sender = a[0]
        logger.info("Refreshing Torrent List %s" % "(from %s)" % (sender if sender else "from unknown"))
        # refresh title and status bars
        self.header = self._build_title_bar_w()
        self.footer = self._build_status_bar_w()

        # get torrent hash of focused torrent (none is no torrents)
        torrent_hash = self.torrent_list_w.get_torrent_hash_for_focused_row()

        # populate torrent info
        self.torrent_list_walker_w.clear()
        tab_pos = self.torrent_tabs_w._TorrentListTabsColumns__selected_tab_pos
        status_filter = self.torrent_tabs_w[tab_pos].get_text()[0].lower()
        self.torrent_list_walker_w.extend(self._build_torrent_list_for_walker_w(status_filter=status_filter))

        # re-focus same torrent if it still exists
        if torrent_hash is not None:
            for pos, torrent in enumerate(self.torrent_list_walker_w):
                if torrent.base_widget.get_torrent_hash() == torrent_hash:
                    self.torrent_list_walker_w.set_focus(pos)
        else:
            self.torrent_list_walker_w.set_focus(0)
        logger.info("Finished refreshing %s" % "(from %s)" % (sender if sender else "from unknown"))

        # TODO: delete
        if hasattr(self, 'last_refresh_time'):
            logger.info("Time since last refresh: %.2f" % (time() - self.last_refresh_time))
        self.last_refresh_time = time()
        logger.info("Time to refresh: %.2f" % (time() - refresh_start_time))

    def update_details(self, *a, **kw):
        ver = kw.pop('version', "")
        if ver != "":
            self.torrent_manager_version = ver

        conn_port = kw.pop('conn_port', "")
        if conn_port != "":
            self.connection_port = conn_port

    def _build_status_bar_w(self):
        """
        Create status bar for window.

        Sample Transfer Info:
        >>> tx = {'connection_status': 'connected', 'dht_nodes': 386, 'dl_info_data': 2056546969, 'dl_info_speed': 0, \
                  'dl_rate_limit': 31457280, 'up_info_data': 14194402619, 'up_info_speed': 0, 'up_rate_limit': 10485760}

        :return: string status
        """

        status = self.server_state.get('connection_status', 'disconnected')

        dht_nodes = self.server_state.get('dht_nodes')

        ''' ⯆[<dl rate>:<dl limit>:<dl size>] ⯅[<up rate>:<up limit>:<up size>] '''
        dl_up_text = ("%s/s%s [%s%s] (%s) %s/s%s [%s%s] (%s)" %
                      (natural_file_size(self.server_state.dl_info_speed, gnu=True).rjust(6),
                       '\u25BC',
                       natural_file_size(self.server_state.dl_rate_limit, gnu=True) if self.server_state.dl_rate_limit not in [0, ''] else '',
                       '/s' if self.server_state.dl_rate_limit not in [0, ''] else '',
                       natural_file_size(self.server_state.dl_info_data, gnu=True),
                       natural_file_size(self.server_state.up_info_speed, gnu=True).rjust(6),
                       '\u25B2',
                       natural_file_size(self.server_state.up_rate_limit, gnu=True) if self.server_state.up_rate_limit not in [0, ''] else '',
                       '/s' if self.server_state.up_rate_limit not in [0, ''] else '',
                       natural_file_size(self.server_state.up_info_data, gnu=True),
                       )
                      ) if self.server_state.get('dl_rate_limit', '') != '' else ''

        left_column_text = "%sStatus: %s" % (("DHT: %s " % dht_nodes) if dht_nodes is not None else "", status)
        right_column_text = "%s" % dl_up_text
        total_len = len(left_column_text) + len(right_column_text)

        w = urwid.Columns(
            [('weight',
              (len(left_column_text) / total_len) * 100,
              urwid.Text(left_column_text, align=urwid.LEFT, wrap=urwid.CLIP)),
             ('weight',
              (len(right_column_text) / total_len) * 100,
              urwid.Padding(urwid.Text(right_column_text, align=urwid.RIGHT, wrap=urwid.CLIP)))
             ],
            dividechars=1,
        )
        return w

    def _build_title_bar_w(self):
        """
        Create title bar for window.

        :return: string title
        """
        app_name = _APP_NAME
        hostname = getfqdn()
        return urwid.Padding(
            urwid.Text("%s (%s) %s:%s" % (app_name,
                                          self.torrent_manager_version,
                                          hostname,
                                          self.connection_port,
                                          ),
                       align=urwid.CENTER),
            width=urwid.RELATIVE_100)

    def _build_torrent_list_for_walker_w(self, status_filter=None):
        """
        Add each relevant torrent to the window.

        Sample torrent:
        >>> {'added_on': 1557844083, 'amount_left': 0, 'auto_tmm': False, 'category': 'errored', \
             'completed': 1822361865, 'completion_on': 1557844150, 'dl_limit': -1, 'dlspeed': 0, \
             'downloaded': 1823979248, 'downloaded_session': 0, 'eta': 8640000, 'f_l_piece_prio': False, \
             'force_start': False, 'hash': '4968193be892bf756a3b0b01281d75ead96dd804', 'last_activity': 0, \
             'magnet_uri': 'magnet:....', 'max_ratio': 1, 'max_seeding_time': 20160, 'name': '...', \
             'num_complete': 182, 'num_incomplete': 67, 'num_leechs': 0, 'num_seeds': 0, 'priority': 0, \
             'progress': 1, 'ratio': 1.004550842345987, 'ratio_limit': -2, 'save_path': '/home/user/torrents/', \
             'seeding_time_limit': -2, 'seen_complete': 1557852124, 'seq_dl': False, 'size': 1822361865, \
             'state': 'pausedUP', 'super_seeding': False, 'tags': '', 'time_active': 7241, 'total_size': 1822361865, \
             'tracker': 'udp://tracker.internetwarriors.net:1337', 'up_limit': -1, 'uploaded': 1832279890, \
             'uploaded_session': 1132891084, 'upspeed': 0}

        :return: list of torrent boxes
        """
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
                                   'active': ['stalledDL',
                                              'metaDL',
                                              'downloading',
                                              'forcedDL',
                                              'uploading',
                                              'forcedUP',
                                              'moving',
                                              ],
                                   'inactive': ['pausedUP',
                                                'stalledUP',
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

        # find longest torrent name length
        max_title_len = 0
        if len(self.torrents_info) != 0:
            max_title_len = max(map(len, [self.torrents_info[torrent_hash]['name'] for torrent_hash in self.torrents_info]))
        max_title_len = min(max_title_len, 170)

        torrent_list = []
        for torrent_hash, torrent in self.torrents_info.items():
            # torrent = AttrDict(torrent)
            if status_filter in state_map_for_filtering.keys() and torrent.state not in state_map_for_filtering[status_filter]:
                continue
            # build display-agnostic torrent info in list of Texts
            state = state_map_for_display[torrent.state] if torrent.state in state_map_for_display else torrent.state
            size = natural_file_size(torrent.size, gnu=True).rjust(6)
            pb = DownloadProgressBar('pg normal', 'pg complete',
                                     current=torrent.completed,
                                     done=torrent.size if torrent.size != 0 else 100)
            pb_text = pb.get_percentage().rjust(4)
            dl_speed = "%s%s" % (natural_file_size(torrent.dlspeed, gnu=True).rjust(6), '\u25BC')
            up_speed = "%s%s" % (natural_file_size(torrent.upspeed, gnu=True).rjust(6), '\u25B2')
            amt_uploaded = "%s%s" % (natural_file_size(torrent.uploaded, gnu=True).rjust(6), '\u21D1')
            ratio = "R %.2f" % torrent.ratio
            leech_num = "L %3d" % torrent.num_leechs
            seed_num = "S %3d" % torrent.num_seeds
            eta = "ETA %s" % (pretty_time_delta(seconds=torrent.eta) if torrent.eta < 8640000 else '\u221E').ljust(6)
            torrent_row_list = [
                # state
                (12, SelectableText(state)),
                # size
                (len(size), SelectableText(size)),
                # progress percentage
                (len(pb_text), SelectableText(pb_text)),
                # dl speed
                (len(dl_speed), SelectableText(dl_speed)),
                # up speed
                (len(up_speed), SelectableText(up_speed)),
                # amount uploaded
                (len(amt_uploaded), SelectableText(amt_uploaded)),
                # share ratio
                (len(ratio), SelectableText(ratio)),
                # seeders
                (len(seed_num), SelectableText(seed_num)),
                # leechers
                (len(leech_num), SelectableText(leech_num)),
                # ETA
                (10, SelectableText(eta))
            ]

            # calculate length (should be the same for all torrent row lists)
            info_len = sum([col[0] + 1 for col in torrent_row_list])

            # add extra info
            torrent_row_list.append(('pack', SelectableText(torrent.category)))

            # Additional Texts to add dependent on display
            title_w = SelectableText(torrent.name, wrap=urwid.CLIP)

            # define when a wide display takes effect
            wide_width = max_title_len + info_len

            # build wide display
            if self.width >= wide_width:
                pb_bar_width = 40
                # replace progress bar
                if self.__width >= (wide_width + pb_bar_width - len(pb_text)):
                    torrent_row_list[2] = (pb_bar_width, pb)
                # add torrent title to beginning of row
                torrent_row_list.insert(0, (max_title_len, title_w))
                # build columns
                torrent_row_w = TorrentListWindow.TorrentRow(self.main,
                                                             [TorrentListWindow.TorrentInfoColumns(torrent_row_list,
                                                                                                   dividechars=1)
                                                              ])

            # build compact display
            if self.width < wide_width:
                # build torrent row
                title_row_w = TorrentListWindow.TorrentInfoColumns([urwid.Padding(title_w)])
                # insert spacer for torrent info row
                torrent_row_list.insert(0, (1, urwid.Text(' ')))
                # build torrent info row
                torrent_info_row_w = TorrentListWindow.TorrentInfoColumns(torrent_row_list, dividechars=1)
                # build multi-line row for list
                torrent_row_w = TorrentListWindow.TorrentRow(self.main, [title_row_w, torrent_info_row_w])

            # color based on state
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

            # add row to list
            torrent_row_w.set_torrent_hash(torrent_hash)
            torrent_list.append(urwid.AttrMap(torrent_row_w, attr, focus_map='selected'))

        return torrent_list if torrent_list else [
            TorrentListWindow.TorrentRow(self.main, [TorrentListWindow.TorrentInfoColumns([])])]


class TorrentOptions(urwid.Pile):
    client: Connector

    def __init__(self, main, torrent_hash):
        self.torrent_hash = torrent_hash
        self.main = main
        self.client = main.torrent_client

        self.torrent_info = self.main.torrent_list_window.torrents_info[self.torrent_hash]

        self.delete_files_w = None

        categories = {x: x for x in list(self.main.torrent_list_window.categories.keys())}
        categories["<no category>"] = "<no category>"

        self.original_location = self.torrent_info.save_path
        self.location_w = urwid.Edit(caption="Location: ",
                                     edit_text=self.original_location)
        self.original_name = self.torrent_info.name
        self.rename_w = urwid.Edit(caption="Rename: ",
                                   edit_text=self.original_name)
        self.original_autotmm_state = self.torrent_info.auto_tmm
        self.autotmm_w = urwid.CheckBox("Automatic Torrent Management",
                                        state=self.original_autotmm_state)
        self.original_super_seeding_state = self.torrent_info.super_seeding
        self.super_seeding_w = urwid.CheckBox("Super Seeding Mode",
                                              state=self.original_super_seeding_state)
        self.original_upload_rate_limit = self.torrent_info.up_limit
        self.upload_rate_limit_w = urwid.IntEdit(caption="Upload Rate Limit (Kib/s)  : ",
                                                 default=int(
                                                     self.original_upload_rate_limit / 1024)if self.original_upload_rate_limit != -1 else "")
        self.original_download_rate_limit = self.torrent_info.dl_limit
        self.download_rate_limit_w = urwid.IntEdit(caption="Download Rate Limit (Kib/s): ",
                                                   default=int(
                                                       self.original_download_rate_limit / 1024) if self.original_download_rate_limit != -1 else "")
        # TODO: accomomdate share ratio and share time
        self.share_ratio_dropdown_w = panwid.Dropdown(items=[("Global Limit", -2), ("Unlimited", -1), ("Specify", 0)],
                                                      label="Share Ratio Limit: ",
                                                      default=self.torrent_info.ratio_limit if self.torrent_info.ratio_limit in [
                                                          -2, -1] else 0)
        self.original_category = self.torrent_info.category if self.torrent_info.category != "" else "<no category>"
        self.category_w = panwid.Dropdown(items=categories,
                                          label="Category",
                                          default=self.original_category,
                                          auto_complete=True)

        super(TorrentOptions, self).__init__(
            [
                urwid.Divider(),
                urwid.Columns(
                    [
                        urwid.Padding(urwid.Text('')),
                        (10, urwid.AttrMap(ButtonWithoutCursor("Resume",
                                                               on_press=self.resume_torrent),
                                           '', focus_map='selected')),
                        (16, urwid.AttrMap(ButtonWithoutCursor("Force Resume",
                                                               on_press=self.force_resume_torrent),
                                           '', focus_map='selected')),
                        (9, urwid.AttrMap(ButtonWithoutCursor("Pause",
                                                              on_press=self.pause_torrent),
                                          '', focus_map='selected')),
                        urwid.Padding(urwid.Text('')),
                    ],
                    dividechars=2
                ),
                urwid.Divider(),
                urwid.Columns(
                    [
                        urwid.Padding(urwid.Text('')),
                        (10, urwid.AttrMap(ButtonWithoutCursor("Delete",
                                                               on_press=self.delete_torrent),
                                           '', focus_map='selected')),
                        (11, urwid.AttrMap(ButtonWithoutCursor("Recheck",
                                                               on_press=self.recheck_torrent),
                                           '', focus_map='selected')),
                        (14, urwid.AttrMap(ButtonWithoutCursor("Reannounce",
                                                               on_press=self.reannounce_torrent),
                                           '', focus_map='selected')),
                        urwid.Padding(urwid.Text('')),
                    ],
                    dividechars=2
                ),
                urwid.Divider(),
                self.location_w,
                urwid.Divider(),
                self.rename_w,
                urwid.Divider(),
                urwid.Columns(
                    [
                        urwid.Padding(urwid.Text('')),
                        (33, self.autotmm_w),
                        (23, self.super_seeding_w),
                        urwid.Padding(urwid.Text('')),
                    ],
                    dividechars=2
                ),
                urwid.Divider(),
                self.share_ratio_dropdown_w,
                urwid.Divider(),
                self.upload_rate_limit_w,
                self.download_rate_limit_w,
                urwid.Divider(),
                self.category_w,
                urwid.Divider(),
                urwid.Divider(),
                urwid.Columns(
                    [
                        urwid.Padding(urwid.Text('')),
                        (6, urwid.AttrMap(ButtonWithoutCursor("OK",
                                                              on_press=self.apply_settings),
                                          '', focus_map='selected')),
                        (10, urwid.AttrMap(ButtonWithoutCursor("Cancel",
                                                               on_press=self.close_window),
                                           '', focus_map='selected'))
                    ],
                    dividechars=2,
                )
            ]
        )

    def apply_settings(self, b):

        new_location = self.location_w.get_edit_text()
        new_name = self.rename_w.get_edit_text()
        new_autotmm_state = self.autotmm_w.get_state()
        new_super_seeding_state = self.super_seeding_w.get_state()
        new_upload_rate_limit = int(self.upload_rate_limit_w.get_edit_text()) * 1024
        new_download_rate_limit = int(self.download_rate_limit_w.get_edit_text()) * 1024
        new_category = self.category_w.selected_label

        if new_location != self.original_location:
            logger.info("Setting new location: %s (%s)" % (new_location, self.torrent_hash))
            self.client.torrents_set_location(location=new_location, torrent_ids=self.torrent_hash)

        if new_name != self.original_name:
            logger.info("Setting new name: %s (%s)" % (new_name, self.torrent_hash))
            self.client.torrent_rename(new_name=new_name, torrent_id=self.torrent_info)

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

        self.reset_screen_to_torrent_list_window()

    def close_window(self, b):
        self.reset_screen_to_torrent_list_window()

    def resume_torrent(self, b):
        self.client.torrents_resume(torrent_ids=self.torrent_hash)

    def force_resume_torrent(self, b):
        self.client.torrents_force_resume(torrent_ids=self.torrent_hash)

    def delete_torrent(self, b):
        self.delete_files_w = urwid.CheckBox(label="Delete Files")
        self.main.loop.widget = urwid.Overlay(
            top_w=urwid.LineBox(urwid.Filler(urwid.Pile(
                [
                    urwid.Divider(),
                    self.delete_files_w,
                    urwid.Divider(),
                    urwid.Columns(
                        [
                            urwid.Padding(urwid.Text('')),
                            (6, urwid.AttrMap(ButtonWithoutCursor("OK",
                                                                  on_press=self.confirm_delete),
                                              '', focus_map='selected')),
                            (10, urwid.AttrMap(ButtonWithoutCursor("Cancel",
                                                                   on_press=self.close_delete_dialog),
                                               '', focus_map='selected'))
                        ],
                        dividechars=2,
                    ),
                ]
            ))),
            bottom_w=self.main.torrent_options_window,
            align=urwid.CENTER,
            valign=urwid.MIDDLE,
            width=30,
            height=10,
            min_width=20
        )

    def confirm_delete(self, b):
        delete_files = self.delete_files_w.get_state()
        self.client.torrents_delete(torrent_ids=self.torrent_hash, delete_files=delete_files)
        self.reset_screen_to_torrent_list_window()

    def close_delete_dialog(self, b):
        self.main.loop.widget = self.main.torrent_options_window

    def pause_torrent(self, b):
        self.client.torrents_pause(torrent_ids=self.torrent_hash)

    def recheck_torrent(self, b):
        self.client.torrents_recheck(torrent_ids=self.torrent_hash)

    def reannounce_torrent(self, b):
        self.client.torrents_reannounce(torrent_ids=self.torrent_hash)

    def reset_screen_to_torrent_list_window(self):
        refresh_torrent_list_with_remote_data_now.send()
        self.main.loop.widget = self.main.torrent_list_window

    def keypress(self, size, key):
        log_keypress(self, key)
        key = super(TorrentOptions, self).keypress(size, key)
        if key == 'esc':
            self.reset_screen_to_torrent_list_window()
        return key
