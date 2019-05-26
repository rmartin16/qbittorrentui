import blinker


sync_maindata_ready = blinker.Signal()
"""signal from poller to send maindata to receivers"""

server_details_ready = blinker.Signal()
"""signal that new details were retrieved from the torrent server"""

server_details_changed = blinker.Signal()
"""signal that new server details are available"""

server_state_changed = blinker.Signal()
"""signal that new server state information is available"""

server_torrents_changed = blinker.Signal()
"""signal that new information about torrents is available"""

rebuild_torrent_list_now = blinker.Signal()
"""signal to rebuild torrent list using existing torrent data"""

refresh_torrent_list_with_remote_data_now = blinker.Signal()
"""signal for poller to immediately request any new torrent data (via sync maindata)"""

run_server_command = blinker.Signal()
"""signal for background poller to send commands to server"""

request_to_initialize_torrent_list = blinker.Signal()
"""once torrent client is connected, signal to initialize the torrent list"""
