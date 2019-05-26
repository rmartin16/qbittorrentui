import urwid as uw
import logging
from attrdict import AttrDict
from time import time, sleep
from qbittorrentui.connector import Connector
from qbittorrentui.connector import ConnectorError
from qbittorrentui.windows import AppWindow
from qbittorrentui.windows import ConnectBox
from qbittorrentui.poller import Poller
from qbittorrentui.events import request_to_initialize_torrent_list
from qbittorrentui.events import sync_maindata_ready
from qbittorrentui.events import server_details_ready
from qbittorrentui.events import server_details_changed
from qbittorrentui.events import server_state_changed
from qbittorrentui.events import server_torrents_changed

try:
    logging.basicConfig(level=logging.INFO,
                        format='[%(asctime)s] {%(name)s:%(lineno)d} %(levelname)s - %(message)s',
                        filename='/home/user/output.txt',
                        filemode='w')
except Exception:
    logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class TorrentServer:
    def __init__(self, bg_poller):
        self.bg_poller = bg_poller
        self.server_state = AttrDict()
        self.torrents = AttrDict()
        self.categories = AttrDict()
        self.server_details = AttrDict()

        server_details_ready.connect(receiver=self.update_details)
        sync_maindata_ready.connect(receiver=self.update_maindata)

    def update_details(self, *a, **kw):
        self.server_details.update(self.bg_poller.get_server_details())
        server_details_changed.send('torrent server', details=self.server_details)

    def update_maindata(self, *a, **kw):
        """
        Retrieve maindata from bg poller and udpatelocal server state

        :param a:
        :param kw:
        :return:
        """
        server_details_updated = False
        server_torrents_updated = False

        logger.info("maindata queue length: %s" % self.bg_poller.maindata_q.qsize())

        # flush the queue if it backs up for any reason...
        while self.bg_poller.maindata_q.qsize() > 0:
            new_md = AttrDict(self.bg_poller.maindata_q.get())

            if new_md.get('full_update', False):
                self.server_state = AttrDict(new_md.server_state)
                server_details_updated = True
                self.torrents = AttrDict(new_md.torrents)
                server_torrents_updated = True
                self.categories = AttrDict(new_md.categories)

            else:
                if new_md.get('server_state', {}):
                    self.server_state.update(AttrDict(new_md.get('server_state', {})))
                    server_details_updated = True

                # remove torrents no longer in qbittorrent
                for torrent_hash in new_md.get('torrents_removed', {}):
                    self.torrents.pop(torrent_hash)
                    server_torrents_updated = True
                # add new torrents or new torrent info
                for torrent_hash, torrent in new_md.get('torrents', {}).items():
                    server_torrents_updated = True
                    if torrent_hash in self.torrents:
                        self.torrents[torrent_hash].update(torrent)
                    else:
                        self.torrents[torrent_hash] = AttrDict(torrent)

                # remove categories no longer in qbittorrent
                for category in new_md.get('categories_removed', {}):
                    self.categories.pop(category, None)
                # add new categories or new category info
                for category_name, category in new_md.get('categories', {}).items():
                    if category in self.categories:
                        self.categories[category_name].update(category)
                    else:
                        self.categories[category_name] = category

        if server_details_updated:
            server_state_changed.send('maindata update', server_state=self.server_state)
        if server_torrents_updated:
            server_torrents_changed.send('maindata update', torrents=self.torrents)


HOST = 'localhost:8080'
USERNAME = 'test'
PASSWORD = 'testtest'


class Main(object):
    bg_poller: Poller
    loop: uw.MainLoop

    def __init__(self):
        super(Main, self).__init__()
        self.torrent_client = Connector(self, host=HOST, username=USERNAME, password=PASSWORD)

        self.ui = None
        self.loop = None
        self.connect_dialog_w = None
        self.torrent_list_w = None
        self.torrent_window = None
        self.connect_window = None
        self.torrent_options_window = None
        self.first_window = None

        self.bg_poller = None
        self.server = None

    @staticmethod
    def loop_sync_maindata_ready(*a, **kw):
        reason = a[0]
        sync_maindata_ready.send('main loop%s' % (" for %s" % reason.decode()) if reason else "")

    @staticmethod
    def loop_server_details_ready(*a, **kw):
        server_details_ready.send('main loop')
        
    def exit(self):
        self.bg_poller.stop_request.set()
        self.bg_poller.wake_up.set()
        self.bg_poller.join()
        raise uw.ExitMainLoop()

    def _setup_screen(self):
        logger.info("Creating screen")
        self.ui = uw.raw_display.Screen()
        self.ui.set_terminal_properties(colors=256)

    def _setup_splash(self):
        logger.info("Creating splash window")
        self.splash_screen = uw.Overlay(
            uw.BigText("qBittorrenTUI", uw.Thin6x6Font()),
            uw.SolidFill(),
            'center', None, 'middle', None)

    def _create_urwid_loop(self):
        logger.info("Creating urwid loop")
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

        def unhandled_input(key):
            if key in ('q', 'Q'):
                self.exit()

        self.loop = uw.MainLoop(widget=self.splash_screen,
                                screen=self.ui,
                                handle_mouse=False,
                                unhandled_input=unhandled_input,
                                palette=palette,
                                event_loop=None,
                                pop_ups=True,
                                )

    def _start_tui(self):
        logger.info("Starting urwid loop")
        self.loop.set_alarm_in(.001, callback=self._finish_setup)
        self.loop.run()

    def _finish_setup(self, *a, **kw):
        start_time = time()
        self._start_bg_poller_daemon()
        self._setup_windows()
        # show splash screen for at least one second
        if 1 - (time() - start_time) > 0:
            sleep(1 - (time() - start_time))
        self.loop.set_alarm_in(.001, callback=self._show_application)

    def _start_bg_poller_daemon(self):
        logger.info("Starting background poller")
        fd_new_maindata = self.loop.watch_pipe(callback=self.loop_sync_maindata_ready)
        fd_new_details = self.loop.watch_pipe(callback=self.loop_server_details_ready)
        self.bg_poller = Poller(self, fd_new_maindata=fd_new_maindata, fd_new_details=fd_new_details)
        self.bg_poller.start()
        self.server = TorrentServer(bg_poller=self.bg_poller)

    def _setup_windows(self):
        logger.info("Creating application windows")
        self.connect_dialog_w = ConnectBox(main=self)
        self.app_window = AppWindow(main=self)

        # TODO: consider how to make the connect window more of a true dialog...may a popup
        #       should also probably move this in to AppWindow
        try:
            self.torrent_client.connect()
            logger.info("Initializing torrent list from main")
            request_to_initialize_torrent_list.send('loop startup')
            self.first_window = self.app_window
        except ConnectorError:
            self.first_window = uw.Overlay(top_w=uw.LineBox(self.connect_dialog_w),
                                           bottom_w=self.app_window,
                                           align=uw.CENTER,
                                           width=(uw.RELATIVE, 50),
                                           valign=uw.MIDDLE,
                                           height=(uw.RELATIVE, 50))

    def _show_application(self, *a, **kw):
        logger.info("Showing qBittorrenTUI")
        self.loop.widget = self.first_window

    def start(self):
        self._setup_screen()
        self._setup_splash()
        self._create_urwid_loop()
        self._start_tui()


def run():
    try:
        Main().start()
    except Exception:
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
