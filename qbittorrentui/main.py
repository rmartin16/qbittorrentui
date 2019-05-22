import urwid
import logging

from qbittorrentui.connector import Connector, ConnectorError
from qbittorrentui.windows import TorrentListWindow, ConnectWindow

try:
    logging.basicConfig(level=logging.INFO,
                        format='[%(asctime)s] {%(name)s:%(lineno)d} %(levelname)s - %(message)s',
                        filename='/home/user/output.txt',
                        filemode='w')
except Exception:
    logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class Main(object):
    def __init__(self):
        super(Main, self).__init__()
        self.torrent_client = Connector(host='localhost:8080', username='test', password='testtest')

        self.ui = None
        self.loop = None
        self.connect_w = None
        self.torrent_list_window = None
        self.torrent_window = None
        self.connect_window = None
        self.torrent_options_window = None

    def refresh(self, *args, **kwargs):
        self.torrent_list_window.refresh_torrent_list_window(*args, **kwargs)

    def start(self):

        def handle_key(key):
            if key in ('q', 'Q'):
                raise urwid.ExitMainLoop()

        self.ui = urwid.raw_display.Screen()
        # self.ui.set_terminal_properties(colors=256)

        self.connect_w = urwid.Filler(ConnectWindow(main=self))
        self.torrent_list_window = TorrentListWindow(main=self)
        self.torrent_window = urwid.ListBox(urwid.SimpleFocusListWalker([urwid.Text("Welcome to the torrent window")]))
        self.connect_window = urwid.Overlay(top_w=urwid.LineBox(self.connect_w),
                                            bottom_w=self.torrent_list_window,
                                            align=urwid.CENTER,
                                            width=50,
                                            valign=urwid.MIDDLE,
                                            height=15)

        palette = [
            ('dark blue on default', 'dark blue', ''),
            ('dark cyan on default', 'dark cyan', ''),
            ('dark green on default', 'dark green', ''),
            ('light red on default', 'light red', '',),
            ('selected', 'white,bold', 'dark blue', 'standout'),
            ('pg normal', '', ''),
            ('pg complete', '', 'dark blue'),
            ('pg smooth', '', ''),

            ('body', 'black', 'light gray', 'standout'),
            ('header', 'white', 'dark red', 'bold'),
            ('screen edge', 'light blue', 'dark cyan'),
            ('main shadow', 'dark gray', 'black'),
            ('line', 'black', 'light gray', 'standout'),
            ('bg background', 'light gray', 'black'),
            ('bg 1', 'black', 'dark blue', 'standout'),
            ('bg 1 smooth', 'dark blue', 'black'),
            ('bg 2', 'black', 'dark cyan', 'standout'),
            ('bg 2 smooth', 'dark cyan', 'black'),
            ('button normal', 'light gray', 'dark blue', 'standout'),
            ('button select', 'white', 'dark green'),
            ('line', 'black', 'light gray', 'standout'),
            ('reversed', 'standout', ''),
        ]

        try:
            self.torrent_client.connect()
            first_window = self.torrent_list_window
        except ConnectorError:
            first_window = self.connect_window

        self.loop = urwid.MainLoop(widget=first_window,
                                   screen=self.ui,
                                   handle_mouse=False,
                                   unhandled_input=handle_key,
                                   palette=palette,
                                   event_loop=None,
                                   pop_ups=True,
                                   )

        # refresh window immediately
        self.loop.set_alarm_in(sec=.01, callback=self.refresh)

        # display TUI
        self.loop.run()


def run():
    try:
        Main().start()
    except:
        import sys
        exc_type, exc_value, tb = sys.exc_info()
        if tb is not None:
            prev = tb
            curr = tb.tb_next
            while curr is not None:
                prev = curr
                curr = curr.tb_next
            print(prev.tb_frame.f_locals)
        raise


if __name__ == '__main__':
    run()
