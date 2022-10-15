import blinker

# signal from a background daemon for the ui
update_ui_from_daemon = blinker.Signal()

# signal that new server details are available
server_details_changed = blinker.Signal()

# signal that a request to the torrent server failed or succeeded
connection_to_server_status = blinker.Signal()

# signal that connection to torrent server is lost
connection_to_server_lost = blinker.Signal()

# signal that connection to torrent server is back
connection_to_server_acquired = blinker.Signal()

# signal that new server state information is available
server_state_changed = blinker.Signal()

# signal that new information about torrents is available
server_torrents_changed = blinker.Signal()

# signal to rebuild torrent list using existing torrent data
refresh_torrent_list_now = blinker.Signal()

# signal for daemon to immediately request any new torrent data (via sync maindata)
update_torrent_list_now = blinker.Signal()

# signal to wake torrent sync daemon up
update_torrent_window_now = blinker.Signal()

# signal for background poller to send commands to server
run_server_command = blinker.Signal()

# once torrent client is connected, signal to reset the torrent list
initialize_torrent_list = blinker.Signal()

# reset daemons upon torrent server connections
reset_daemons = blinker.Signal()

# signal that the tab changed in a torrent window
torrent_window_tab_change = blinker.Signal()

# signal to close up shop
exit_tui = blinker.Signal()
