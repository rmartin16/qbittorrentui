import blinker

# TODO: find a new home
IS_TIMING_LOGGING_ENABLED = True


update_ui_from_daemon = blinker.Signal()
"""signal from a background daemon for the ui"""

server_details_changed = blinker.Signal()
"""signal that new server details are available"""

server_state_changed = blinker.Signal()
"""signal that new server state information is available"""

server_torrents_changed = blinker.Signal()
"""signal that new information about torrents is available"""

refresh_torrent_list_now = blinker.Signal()
"""signal to rebuild torrent list using existing torrent data"""

update_torrent_list_now = blinker.Signal()
"""signal for dameon to immediately request any new torrent data (via sync maindata)"""

update_torrent_window_now = blinker.Signal()
"""signal to wake torrent sync daemon up"""

run_server_command = blinker.Signal()
"""signal for background poller to send commands to server"""

initialize_torrent_list = blinker.Signal()
"""once torrent client is connected, signal to initialize the torrent list"""

torrent_window_tab_change = blinker.Signal()
"""signal that the tab changed in a torrent window"""
