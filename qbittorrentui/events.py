import blinker

sync_maindata_ready = blinker.Signal()

rebuild_torrent_list_now = blinker.Signal()

refresh_torrent_list_with_remote_data_now = blinker.Signal()

