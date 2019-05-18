import urwid
from socket import getfqdn
from humanize import naturalsize  # TODO: consider if this is the right library for this
import logging


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


class TorrentListWindow(urwid.Frame):
    def __init__(self, console, qbt_client):
        self.console = console
        self.qbt_client = qbt_client
        self.loop = None  # is set after first refresh
        self.__width = None

        # initialize title and status bars
        self.title_w = urwid.Text('')
        self.status_bar_w = urwid.Text('')

        # initialize torrent list
        self.torrent_list_walker_w = urwid.SimpleFocusListWalker([])
        self.torrent_list_w = TorrentListWindow.TorrentList(self.torrent_list_walker_w)

        #  Set up torrent status tabs
        self.torrent_tabs_list = [
            urwid.AttrMap(urwid.Filler(TorrentListWindow.SelectableText('All',
                                                                        align=urwid.CENTER)), 'selected',
                          focus_map='selected'),
            urwid.AttrMap(urwid.Filler(TorrentListWindow.SelectableText('Downloading',
                                                                        align=urwid.CENTER)), '',
                          focus_map='selected'),
            urwid.AttrMap(urwid.Filler(TorrentListWindow.SelectableText('Completed',
                                                                        align=urwid.CENTER)), '',
                          focus_map='selected'),
            urwid.AttrMap(urwid.Filler(TorrentListWindow.SelectableText('Paused',
                                                                        align=urwid.CENTER)), '',
                          focus_map='selected'),
            urwid.AttrMap(urwid.Filler(TorrentListWindow.SelectableText('Active',
                                                                        align=urwid.CENTER)), '',
                          focus_map='selected'),
            urwid.AttrMap(urwid.Filler(TorrentListWindow.SelectableText('Inactive',
                                                                        align=urwid.CENTER)), '',
                          focus_map='selected'),
            urwid.AttrMap(urwid.Filler(TorrentListWindow.SelectableText('Resumed',
                                                                        align=urwid.CENTER)), '',
                          focus_map='selected')
        ]
        self.torrent_tabs_w = TorrentListWindow.TorrentListTabsColumns(self.torrent_tabs_list)

        # build body
        self.torrent_list_body = urwid.Pile([(1, self.torrent_tabs_w),
                                             (1, urwid.Filler(urwid.Divider())),
                                             self.torrent_list_w])

        # signals
        urwid.register_signal(type(self.torrent_tabs_w), 'change')
        urwid.connect_signal(self.torrent_tabs_w,
                             'change',
                             self.refresh_torrent_list_window_args,
                             user_args=["no alarm"])
        urwid.register_signal(type(self.torrent_tabs_w), 'reset list focus')
        urwid.connect_signal(self.torrent_tabs_w,
                             'reset list focus',
                             self.reset_torrent_list_focus)

        super(TorrentListWindow, self).__init__(header=self.title_w,
                                                body=self.torrent_list_body,
                                                footer=self.status_bar_w)

    class SelectableText(urwid.Text):
        def selectable(self):
            return True

        def keypress(self, size, key, *args, **kwargs):
            return key

    class TorrentListTabsColumns(urwid.Columns):
        def __init__(self, widget_list, dividechars=0, focus_column=None):
            super(TorrentListWindow.TorrentListTabsColumns, self).__init__(widget_list, dividechars, focus_column)
            self.__selected_tab_pos = 0

        def keypress(self, size, key):
            logger.info("%s received key '%s'" % (self.__class__.__name__, key))
            key = super(TorrentListWindow.TorrentListTabsColumns, self).keypress(size, key)

            focused_tab_pos = self.focus_position
            if focused_tab_pos != self.__selected_tab_pos:
                tab_text = self.contents[self.__selected_tab_pos][0].base_widget.get_text()[0]
                new_col = urwid.AttrMap(
                    urwid.Filler(TorrentListWindow.SelectableText(tab_text, align=urwid.CENTER)),
                    '',
                    focus_map='selected')
                self.contents[self.__selected_tab_pos] = (new_col, ('weight', 1, False))
                self.__selected_tab_pos = focused_tab_pos
                tab_text = self.contents[self.__selected_tab_pos][0].base_widget.get_text()[0]
                new_col = urwid.AttrMap(
                    urwid.Filler(TorrentListWindow.SelectableText(tab_text, align=urwid.CENTER)),
                    'selected',
                    focus_map='selected')
                self.contents[self.__selected_tab_pos] = (new_col, ('weight', 1, False))
            urwid.emit_signal(self, 'change')
            urwid.emit_signal(self, 'reset list focus')
            return key

    class TorrentList(urwid.ListBox):
        def keypress(self, size, key):
            logger.info("%s received key '%s'" % (self.__class__.__name__, key))
            key = super(TorrentListWindow.TorrentList, self).keypress(size, key)
            #if key == 'right':
            #    self.loop.widget = self.console.torrent_window
            #    return None
            #else:
            return key

        def get_torrent_hash_for_focused_row(self):
            focused_row, focused_row_pos = self.body.get_focus()
            if focused_row is not None:
                return focused_row.base_widget.get_torrent_hash()
            return None

    class TorrentRow(urwid.Pile):
        def __init__(self, widget_list, focus_item=None):
            self.__hash = None
            super(TorrentListWindow.TorrentRow, self).__init__(widget_list, focus_item)

        def get_torrent_hash(self):
            return self.__hash

        def keypress(self, size, key):
            return key

    class TorrentInfoColumns(urwid.Columns):
        def keypress(self, size, key):
            return key

        def get_torrent_hash(self):
            """Retrieve torrent hash from first column.

            Note: the column is effectively hidden since it's size is 0
            """
            if 0 in self:
                return self[0][0].get_text()[0]
            return None

    def render(self, size, focus=False):
        self.__width = size[0]
        logger.info("Rendering TorrentWindow")
        # call to refresh on screen re-sizes
        self.refresh_torrent_list_window_args('no alarm')
        return super(TorrentListWindow, self).render(size, focus)

    def keypress(self, size, key):
        logger.info("Focus path: %s" % self.get_focus_path())
        logger.info("%s received key '%s'" % (self.__class__.__name__, key))
        key = super(TorrentListWindow, self).keypress(size, key)
        logger.info("Focus path: %s" % self.get_focus_path())
        return key

    def reset_torrent_list_focus(self, *args):
        self.torrent_list_w.set_focus(0)

    def refresh_torrent_list_window_args(self, *args):
        d = {}
        if 'no alarm' in args:
            d = {'no alarm': 1}
        self.refresh_torrent_list_window(None, d)

    def refresh_torrent_list_window(self, loop=None, user_data=None):
        logger.info("Refreshing torrent list")

        if loop is not None:
            self.loop = loop
        if user_data is None:
            user_data = {}

        # refresh title and status bars
        self.header = self._build_title_bar_w()
        self.footer = self._build_status_bar_w()

        # get torrent hash of focused torrent (none is no torrents)
        torrent_hash = self.torrent_list_w.get_torrent_hash_for_focused_row()

        # populate torrent info
        self.torrent_list_walker_w.clear()
        status_filter = 'all'
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

        if self.loop is not None:
            # schedule next refresh
            if not user_data.get('no alarm'):
                self.loop.set_alarm_in(sec=2, callback=self.refresh_torrent_list_window)

        logger.info("Tabs focus: %s" % self.torrent_tabs_w.focus_col)

    def _build_title_bar_w(self):
        """
        Create title bar for window.

        :return: string title
        """
        app_name = _APP_NAME
        qbt_version = self.qbt_client.app_version()
        hostname = getfqdn()
        webui_port = self.qbt_client.app_preferences().web_ui_port
        return urwid.Padding(
            urwid.Text("%s (%s) %s:%s" % (app_name, qbt_version, hostname, webui_port),
                       align=urwid.CENTER),
            width=urwid.RELATIVE_100)

    def _build_status_bar_w(self):
        """
        Create status bar for window.

        Sample Transfer Info:
        >>> tx = {'connection_status': 'connected', 'dht_nodes': 386, 'dl_info_data': 2056546969, 'dl_info_speed': 0, \
                  'dl_rate_limit': 31457280, 'up_info_data': 14194402619, 'up_info_speed': 0, 'up_rate_limit': 10485760}

        :return: string status
        """
        tx_info = self.qbt_client.transfer_info()

        status = tx_info.connection_status

        dht_nodes = tx_info.dht_nodes

        ''' ⯆[<dl rate>:<dl limit>:<dl size>] ⯅[<up rate>:<up limit>:<up size>] '''
        dl_up_text = "%s[%s/s %s/s (%s)]  %s[%s/s %s/s (%s)]" % \
                     ('\u25BC',
                      naturalsize(tx_info.dl_info_speed, gnu=True).rjust(6),
                      naturalsize(tx_info.dl_rate_limit, gnu=True),
                      naturalsize(tx_info.dl_info_data, gnu=True),
                      '\u25B2',
                      naturalsize(tx_info.up_info_speed, gnu=True).rjust(6),
                      naturalsize(tx_info.up_rate_limit, gnu=True),
                      naturalsize(tx_info.up_info_data, gnu=True),
                      )

        left_column_text = "DHT: %s Status: %s" % (dht_nodes, status)
        right_column_text = "%s" % dl_up_text
        total_len = len(left_column_text) + len(right_column_text)

        w = urwid.Columns(
            [('weight',
              (len(left_column_text)/total_len)*100,
              urwid.Text(left_column_text, align=urwid.LEFT, wrap=urwid.CLIP)),
             ('weight',
              (len(right_column_text)/total_len)*100,
              urwid.Padding(urwid.Text(right_column_text, align=urwid.RIGHT, wrap=urwid.CLIP)))
             ],
            dividechars=1,
        )
        return w

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
        state_map = {'pausedUP': "Completed",
                     'uploading': 'Uploading',
                     'stalledUP': 'Uploading',
                     'queuedUP': 'Queued',
                     'pausedDL': "Paused",
                     'downloading': 'Downloading',
                     'stalledDL': "Downloading"}

        torrent_info = self.qbt_client.torrents_info(status_filter=status_filter)
        max_title_len = 0
        if len(torrent_info) != 0:
            max_title_len = max(map(len, [torrent.name for torrent in torrent_info]))
        max_title_len = min(max_title_len, 170)

        torrent_list = []
        for torrent in torrent_info:
            # build display-agnostic torrent info in list of Texts
            state = state_map[torrent.state] if torrent.state in state_map else torrent.state
            size = (naturalsize(torrent.total_size, gnu=True) if torrent.total_size != -1 else 'Unk').rjust(6)
            pb = urwid.ProgressBar('pg normal', 'pg complete', satt='pg smooth',
                                   current=torrent.completed / torrent.total_size * 100,)
            pb_text = pb.get_text().replace(' ', '').rjust(4)
            dl_speed = "%s%s" % (naturalsize(torrent.dlspeed, gnu=True).rjust(6), '\u25BC')
            up_speed = "%s%s" % (naturalsize(torrent.upspeed, gnu=True).rjust(6), '\u25B2')
            amt_uploaded = "%s%s" % (naturalsize(torrent.uploaded, gnu=True).rjust(6), '\u21D1')
            ratio = "R %.2f" % torrent.ratio
            leech_num = "L %3d" % torrent.num_leechs
            seed_num = "S %3d" % torrent.num_seeds
            eta = "ETA %s" % (pretty_time_delta(seconds=torrent.eta) if torrent.eta < 8640000 else '\u221E')
            torrent_row_list = [
                # state
                (12, TorrentListWindow.SelectableText(state)),
                # size
                (len(size), TorrentListWindow.SelectableText(size)),
                # progress percentage
                (len(pb_text), TorrentListWindow.SelectableText(pb_text)),
                # dl speed
                (len(dl_speed), TorrentListWindow.SelectableText(dl_speed)),
                # up speed
                (len(up_speed), TorrentListWindow.SelectableText(up_speed)),
                # amount uploaded
                (len(amt_uploaded), TorrentListWindow.SelectableText(amt_uploaded)),
                # share ratio
                (len(ratio), TorrentListWindow.SelectableText(ratio)),
                # seeders
                (len(seed_num), TorrentListWindow.SelectableText(seed_num)),
                # leechers
                (len(leech_num), TorrentListWindow.SelectableText(leech_num)),
                # ETA
                (10, TorrentListWindow.SelectableText(eta))
            ]

            # calculate length (should be the same for all torrent row lists)
            info_len = sum([col[0]+1 for col in torrent_row_list])

            # add extra info
            torrent_row_list.append(('pack',  TorrentListWindow.SelectableText(torrent.category)))

            # Additional Texts to add dependent on display
            title_w = TorrentListWindow.SelectableText(torrent.name, wrap=urwid.CLIP)

            # define when a wide display takes effect
            wide_width = max_title_len + info_len

            # build wide display
            if self.__width >= wide_width:  # build wide list
                pb_bar_width = 40
                # replace progress bar
                if self.__width >= (wide_width+pb_bar_width-len(pb_text)):
                    torrent_row_list[2] = (pb_bar_width, pb)
                # add torrent title to beginning of row
                torrent_row_list.insert(0, (max_title_len, title_w))
                # build columns
                torrent_row_w = TorrentListWindow.TorrentRow(
                    [TorrentListWindow.TorrentInfoColumns(torrent_row_list, dividechars=1)])

            # build compact display
            if self.__width < wide_width:
                # build torrent row
                title_row_w = TorrentListWindow.TorrentInfoColumns([urwid.Padding(title_w)])
                # insert spacer for torrent info row
                torrent_row_list.insert(0, (1, urwid.Text(' ')))
                # build torrent info row
                torrent_info_row_w = TorrentListWindow.TorrentInfoColumns(torrent_row_list, dividechars=1)
                # build multi-line row for list
                torrent_row_w = TorrentListWindow.TorrentRow([title_row_w, torrent_info_row_w])

            # add row to list
            torrent_row_w._TorrentRow__hash = torrent.hash
            torrent_list.append(urwid.AttrMap(torrent_row_w, '', focus_map='selected'))

        return torrent_list if torrent_list else [TorrentListWindow.TorrentRow([TorrentListWindow.TorrentInfoColumns([])])]
