qBittorrenTUI
===============
[![PyPI](https://img.shields.io/pypi/v/qbittorrentui?style=flat-square)](https://pypi.org/project/qbittorrentui/) 
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/qbittorrentui?style=flat-square)

Console UI for qBittorrent. Not feature-complete but is usable for low volume and everyday torrenting.

![qbittorrentui screenshot 1](https://i.imgur.com/Uy7DK37.png)

![qbittorrentui screensho 2](https://i.imgur.com/E6I9q4V.png)

Key Map
-------
Any Window
* q : exit
* n : open connection dialog

Torrent List Window
* a : open add torrent dialog
* enter : open context menu for selected torrent
* right arrow: open Torrent Window

Torrent Window
* left : return to Torrent List
* esc : return to Torrent List
* Content
  * enter : bump priority
  * space : bump priority

Installation
------------
Install from pypi:
```bash
pip install qbittorrentui
```
In most cases, this should allow you to run the application simply with the `qbittorrentui` command. Alternatively, you can specify a specific python binary with `./venv/bin/python -m qbittorrentui` or similar.

Configuration
-------------
Connections can be pre-defined within a configuration file (modeled after default.ini). Specify the configuration file using --config_file. Each section in the file will be presented as a separate instance to connect to.

Sample configuration file section:
```
[localhost:8080]
HOST = localhost
PORT = 8080
USERNAME = admin
PASSWORD = adminadmin
CONNECT_AUTOMATICALLY = 1
TIME_AFTER_CONNECTION_FAILURE_THAT_CONNECTION_IS_CONSIDERED_LOST = 5
TORRENT_CONTENT_MAX_FILENAME_LENGTH = 75
TORRENT_LIST_MAX_TORRENT_NAME_LENGTH = 60
TORRENT_LIST_PROGRESS_BAR_LENGTH = 40
DO_NOT_VERIFY_WEBUI_CERTIFICATE = 1
```

Only HOST, USERNAME, AND PASSWORD are required.
DO_NOT_VERIFY_WEBUI_CERTIFICATE is necessary if the certificate is untrusted (e.g. self-signed).

TODO/Wishlist
-------------
Application
 - [ ] Figure out the theme(s)
 - [x] Configuration for connections
 - [ ] Log/activity output (likely above status bar)
 - [ ] Implement window for editing qBittorrent settings

Torrent List Window
 - [ ] Torrent sorting
 - [ ] Additional torrent filtering mechanisms
 - [ ] Torrent searching
 - [ ] Torrent status icon in torrent name
 - [ ] Torrent name color coding
 - [ ] Torrent list column configuration

Torrent Window
 - [ ] Make focus more obvious when switching between tabs list and a display
 - [ ] Scrollbar in the displays
 - [ ] Speed graph display

Torrent Window Content Display
 - [ ] Left key should return to tab list
