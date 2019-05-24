import blinker


sync_maindata_ready = blinker.Signal()
"""signal from poller to send maindata to receivers"""

torrent_list_ready = blinker.Signal()
"""signal from poller to send full torrent list to receivers"""

rebuild_torrent_list_now = blinker.Signal()
"""signal to rebuild torrent list using existing torrent data"""

refresh_torrent_list_with_remote_data_now = blinker.Signal()
"""signal for poller to immediately request any new torrent data (via sync maindata)"""

request_to_initialize_torrent_list = blinker.Signal()
"""once torrent client is connected, signal to initialize the torrent list"""
