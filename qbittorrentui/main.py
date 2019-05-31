import urwid as uw
import logging
import blinker
from attrdict import AttrDict
from time import time, sleep
from os import environ

from qbittorrentui.connector import Connector
from qbittorrentui.connector import ConnectorError
from qbittorrentui.windows.application import AppWindow
from qbittorrentui.windows.application import ConnectDialog
from qbittorrentui.config import APPLICATION_NAME
from qbittorrentui.daemon import DaemonManager
from qbittorrentui.events import initialize_torrent_list
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


#HOST = 'localhost:8080'
#USERNAME = 'test'
#PASSWORD = 'testtest'


class TorrentServer:
    daemon: DaemonManager

    def __init__(self, daemon):
        self.daemon = daemon
        self.server_state = AttrDict()
        self.torrents = AttrDict()
        self.categories = AttrDict()
        self.server_details = AttrDict()
        self.partial_daemon_signal = ""

    def daemon_signal(self, signal):
        signal_str = signal.decode()
        # it's technically possible for the daemon to send multiple signals before
        # the urwid event loop reads from the buffer. (this is most obvious if you set a
        # breakpoint pausing the urwid loop.) therefore, signals can all be read together.
        # this looping will allow each signal to still be processed as intended.
        # additionally, if the buffer grows too large, the urwid documentation suggests
        # only some of the buffer will be read in. so, if the signal string doesn't end
        # in the daemon signal terminator, save off the end of the signal for the next loop.
        if signal_str:
            signal_list = signal_str.split(self.daemon.signal_terminator)
            if signal_str.endswith(self.daemon.signal_terminator):
                # if the signal list terminates as expected, prepend any partial signal
                # to the first signal and process the signals
                signal_list[0] = "%s%s" % (self.partial_daemon_signal, signal_list[0])
                self.partial_daemon_signal = ""
                # remove the last element since it'll just be an empty string
                signal_list.pop(-1)
            else:
                # if the last signal doesnt end with the terminator, remove it from the
                # signal list to be processed and concatenate to any previous partial signal
                # saving the whole thing as the new partial signal.
                # if the whole new signal string was a new partial, then nothing will be
                # processed for this signal event.
                self.partial_daemon_signal = "%s%s" % (self.partial_daemon_signal, signal_list.pop(-1))
            for one_signal in signal_list:
                signal_parts = one_signal.split(":")
                sender = signal_parts[0]
                signal = signal_parts[1]
                extra = list(signal_parts[2:])
                if signal == "sync_maindata_ready":
                    self.update_maindata()
                elif signal == "server_details_ready":
                    self.update_details()
                elif signal.startswith("sync_torrent_data_ready"):
                    self.update_sync_torrents(torrent_hash=extra[0])
                elif signal == "close_pipe":
                    # tell urwid loop to close the read end of the pipe...daemon will close write end
                    return False
                else:
                    logger.info("Received unknown signal from daemon: sender: %s signal: %s" % (sender, signal), exc_info=True)
            return True

    def update_details(self):
        self.server_details.update(self.daemon.get_server_details())
        server_details_changed.send('torrent server', details=self.server_details)

    def update_maindata(self):
        """
        Retrieve maindata from bg daemon and update local server state

        :return:
        """
        server_details_updated = False
        server_torrents_updated = False

        # flush the queue if it backs up for any reason...
        while self.daemon.sync_maindata_q.qsize() > 0:
            new_md = AttrDict(self.daemon.sync_maindata_q.get())

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

    def update_sync_torrents(self, torrent_hash):
        store = self.daemon.get_torrent_store(torrent_hash=torrent_hash)
        if store is not None:
            blinker.signal(torrent_hash).send('sync_torrent_update',
                                              torrent=store.torrent,
                                              properties=store.properties,
                                              trackers=store.trackers,
                                              sync_torrent_peers=store.sync_torrent_peers,
                                              content=store.content)


class Main(object):
    server: TorrentServer
    torrent_client: Connector
    daemon: DaemonManager
    loop: uw.MainLoop

    def __init__(self):
        super(Main, self).__init__()
        self.connect_dialog_w = None
        self.first_window = None

        self.ui = uw.raw_display.Screen()
        self.loop = uw.MainLoop(widget=None,
                                unhandled_input=self.unhandled_urwid_loop_input)
        self.torrent_client = Connector() #host=HOST,
                                        #username=USERNAME,
                                        #password=PASSWORD)
        # TODO: revamp data sharing between daemon and torrent server such that
        #       torrent server isn't dependent on daemon. This will likely require
        #       a single queue between the two. May be too much trouble though...
        self.daemon = DaemonManager(torrent_client=self.torrent_client,
                                    daemon_signal_fd=self.loop.watch_pipe(callback=self.daemon_signal))
        self.server = TorrentServer(daemon=self.daemon)

    def daemon_signal(self, *a, **kw):
        return self.server.daemon_signal(*a, **kw)

    #########################################
    # Start Application
    #########################################
    def start(self):
        self._setup_screen()
        self._setup_splash()
        self._setup_urwid_loop()
        self._start_tui()

    #########################################
    # start() calls the preceding methods in the order they are listed
    #########################################
    def _setup_screen(self):
        logger.info("Setting up screen")
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
        self.ui.set_terminal_properties(colors=256)
        self.ui.register_palette(palette=palette)

    def _setup_splash(self):
        logger.info("Creating splash window")
        self.splash_screen = uw.Overlay(
            uw.BigText("qBittorrenTUI", uw.Thin6x6Font()),
            uw.SolidFill(),
            'center', None, 'middle', None)

    def _setup_urwid_loop(self):
        logger.info("Setting up urwid loop")
        self.loop.widget = self.splash_screen
        self.loop.screen = self.ui
        self.loop.handle_mouse = False
        self.loop.pop_ups = True

    def _start_tui(self):
        logger.info("Starting urwid loop")
        self.loop.set_alarm_in(.001, callback=self._finish_setup)
        self.loop.run()

    def _finish_setup(self, loop, _):
        """
        Once the TUI shows the splash screen, setup will continue here

        :param loop: urwid loop
        :param _: user_data from urwid loop
        """
        start_time = time()
        self._setup_windows()
        self._start_daemon()
        sleep_time_to_show_splash = 1 - (time() - start_time)
        if environ.get('PYTHON_QBITTORRENTUI_DEV_ENV'):
            sleep_time_to_show_splash = 0
        # show splash screen for at least one second during startup
        if sleep_time_to_show_splash > 0:
            sleep(1 - (time() - start_time))
        self._show_application()

    def _start_daemon(self):
        logger.info("Starting background daemon")
        self.daemon.start()

    def _setup_windows(self):
        logger.info("Creating application windows")
        self.connect_dialog_w = ConnectDialog(main=self)
        self.app_window = AppWindow(main=self)

        # TODO: consider how to make the connect window more of a true dialog...may a popup
        #       should also probably move this in to AppWindow
        try:
            self.torrent_client.connect()
            initialize_torrent_list.send('loop startup')
            self.first_window = self.app_window
        except ConnectorError:
            self.first_window = uw.Overlay(top_w=uw.LineBox(self.connect_dialog_w),
                                           bottom_w=self.app_window,
                                           align=uw.CENTER,
                                           width=(uw.RELATIVE, 50),
                                           valign=uw.MIDDLE,
                                           height=(uw.RELATIVE, 50))

    def _show_application(self):
        logger.info("Showing %s" % APPLICATION_NAME)
        self.loop.widget = self.first_window

    #########################################
    # Cleanup and Exit - always exit through here
    #########################################
    def unhandled_urwid_loop_input(self, key):
        if key in ('q', 'Q'):
            self.exit()

    def exit(self):
        """
        Called from urwid loop's unhandled input callback.

        :return:
        """
        self.cleanup()
        raise uw.ExitMainLoop()

    def cleanup(self):
        self.daemon.stop()
        self.daemon.join(2)


def run():
    program = Main()
    try:
        program.start()
    except Exception:
        # try to print some mildly helpful info about the crash
        import sys
        from pprint import pprint as pp
        exc_type, exc_value, tb = sys.exc_info()
        if tb is not None:
            prev = tb
            curr = tb.tb_next
            while curr is not None:
                prev = curr
                curr = curr.tb_next
            try:
                pp(prev.tb_frame.f_locals)
            except Exception:
                pass

        print()
        program.cleanup()
        raise
