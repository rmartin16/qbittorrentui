import urwid
import logging

from qbittorrentapi import Client

from windows import TorrentListWindow


logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] {%(name)s:%(lineno)d} %(levelname)s - %(message)s',
                    filename='/home/user/output.txt',
                    filemode='w')
logger = logging.getLogger(__name__)


class Main(object):
    def __init__(self):
        self._qbt_client = Client()  # host='localhost:8091', username='admin', password='adminadmin')

    def run_loop(self, loop):
        try:
            loop()
        except Exception as e:
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
        self.torrent_list_window = None
        self.torrent_window = None

    def refresh(self, *args, **kwargs):
        logger.exception("Console refresh")
        self.torrent_list_window.refresh_torrent_list_window(*args, **kwargs)

    def run_loop(self, loop=None):
        def handle_key(key):
            if key in ('q', 'Q'):
                raise urwid.ExitMainLoop()

        self.ui = urwid.raw_display.Screen()
        # self.ui.set_terminal_properties(colors=256)

        self.torrent_list_window = TorrentListWindow(self, qbt_client=self._qbt_client)
        self.torrent_window = urwid.ListBox(urwid.SimpleFocusListWalker([urwid.Text("Welcome to the torrent window")]))

        self.ui.signal_handler_setter(28, self.refresh)

        self.ui.signal_init()

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

        loop = urwid.MainLoop(self.torrent_list_window,
                              screen=self.ui,
                              handle_mouse=False,
                              unhandled_input=handle_key,
                              palette=palette,
                              event_loop=None,
                              pop_ups=False,
                              )

        # refresh window immediately
        loop.set_alarm_in(sec=.01, callback=self.refresh)

        # display TUI
        super(Console, self).run_loop(loop.run)


if __name__ == '__main__':
    try:
        Run()()
    except:
        import sys
        from pprint import pprint as pp
        exc_type, exc_value, tb = sys.exc_info()
        if tb is not None:
            prev = tb
            curr = tb.tb_next
            while curr is not None:
                prev = curr
                curr = curr.tb_next
            pp(prev.tb_frame.f_locals)
        raise