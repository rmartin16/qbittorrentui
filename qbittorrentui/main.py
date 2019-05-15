import urwid
import logging

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] {%(name)s:%(lineno)d} %(levelname)s - %(message)s',
                    filename='/home/user/output.txt',
                    filemode='w')


from qbittorrentapi import Client
class Main(object):
    def __init__(self):
        self._qbt_client = Client(host='localhost:8096', username='admin', password='adminadmin')

    def run_loop(self, loop):
        try:
            loop()
        except:
            raise
        finally:
            pass


class Run(object):
    def __init__(self):
        super(Run, self).__init__()

    def __call__(self, *args, **kwargs):
        console = Console()
        console.run_loop()


class Console(Main):
    def __init__(self):
        super(Console, self).__init__()
        self.ui = None
        self.window = None

    def run_loop(self, loop=None):

        def quit(*args, **kwargs):
            raise urwid.ExitMainLoop()

        def handle_key(key):
            if key in ('q', 'Q'):
                quit()

        def refresh(*args, **kwargs):
            self.window.refresh(*args, **kwargs)

        self.ui = urwid.raw_display.Screen()
        self.window = Window(self, qbt_client=self._qbt_client)

        loop = urwid.MainLoop(self.window,
                              screen=self.ui,
                              handle_mouse=False,
                              unhandled_input=handle_key,
                              palette=[],
                              event_loop=None,
                              pop_ups=False,
                              )

        # refresh window immediately
        loop.set_alarm_in(sec=.01, callback=refresh)

        # display TUI
        super(Console, self).run_loop(loop.run)


import datetime
from socket import getfqdn
from humanize import naturalsize  # TODO: consider if this is the right library for this
_APP_NAME = 'qBittorrenTUI'
class Window(urwid.Frame):
    def __init__(self, console, qbt_client):
        self.console = console
        self._qbt_client = qbt_client

        # initialize title and status bars
        self.title_w = urwid.Padding(urwid.Text(''), width=urwid.RELATIVE_100)
        # self.status_bar_w = urwid.Padding(urwid.Text(''), align=urwid.RELATIVE_100, width=urwid.PACK, left=0, right=1)
        self.status_bar_w = urwid.Text('', align=urwid.RIGHT)

        # initialize torrent list
        self.torrent_list_walker_w = urwid.SimpleFocusListWalker([])
        self.torrent_list_w = urwid.ListBox(self.torrent_list_walker_w)

        super(Window, self).__init__(body=self.torrent_list_w,
                                     header=urwid.Pile([self.title_w, urwid.Divider()]),
                                     footer=self.status_bar_w,
                                     focus_part='body')

    def refresh(self, loop=None, user_data=None):
        # refresh title and status bars
        self.title_w.original_widget = self._build_title_bar_text()
        self.footer = self._build_status_bar_w()

        self.torrent_list_walker_w.clear()
        self.torrent_list_walker_w.extend(self._build_torrent_list_for_walker_w())

        loop.set_alarm_in(sec=1, callback=self.refresh)

    def _build_title_bar_text(self):
        """
        Create title bar for window.

        :return: string title
        """
        app_name = _APP_NAME
        qbt_version = self._qbt_client.app_version()
        hostname = getfqdn()
        return urwid.Text("%s (%s) %s" % (app_name, qbt_version, hostname), align=urwid.CENTER)

    def _build_status_bar_w(self):
        """
        Create status bar for window.

        Sample Transfer Info:
        >>> tx = {'connection_status': 'connected', 'dht_nodes': 386, 'dl_info_data': 2056546969, 'dl_info_speed': 0, \
                  'dl_rate_limit': 31457280, 'up_info_data': 14194402619, 'up_info_speed': 0, 'up_rate_limit': 10485760}

        :return: string status
        """
        tx_info = self._qbt_client.transfer_info()

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

    def _build_torrent_list_for_walker_w(self):
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

        torrent_list = []
        for torrent in self._qbt_client.torrents_info():
            title = urwid.Text("%s" % torrent.name, wrap=urwid.CLIP)
            state = state_map[torrent.state] if torrent.state in state_map else torrent.state
            info_w = urwid.Columns(
                 # indent
                [(6, urwid.Text('')),
                 # state
                 (12, urwid.Text("%s" % state,
                                 wrap=urwid.CLIP)),
                # size
                 (14, urwid.Text("Size: %s" % naturalsize(torrent.total_size, gnu=True).rjust(6),
                                 wrap=urwid.CLIP)),
                 # dl/up speeds
                 ('pack', urwid.Text("Rate: %s / %s" %
                                     (naturalsize(torrent.dlspeed, gnu=True).rjust(6),
                                      naturalsize(torrent.upspeed, gnu=True).rjust(6)),
                                     wrap=urwid.CLIP)),
                 # amount uploaded
                 ('pack', urwid.Text("Uploaded: %s" % naturalsize(torrent.uploaded, gnu=True).rjust(6),
                                     wrap=urwid.CLIP)),
                 # share ratio
                 ('pack', urwid.Text("[R: %.2f]" % torrent.ratio,
                                     wrap=urwid.CLIP)),
                 # leechers
                 ('pack', urwid.Text("S:%s" % torrent.num_leechs)),
                 # seeders
                 ('pack', urwid.Text("L:%s" % torrent.num_seeds)),
                 # ETA
                 ('pack', urwid.Text("ETA: %s" % (datetime.timedelta(seconds=torrent.eta) if torrent.eta < 8640000 else '\u221E')))
                 ],
                dividechars=1)
            logging.getLogger(__name__).info(torrent.eta)
            torrent_list.append(title)
            torrent_list.append(info_w)
            torrent_list.append(urwid.Padding(urwid.Text("")))

        return torrent_list


Run()()
