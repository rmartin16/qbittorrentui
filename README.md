qBittorrenTUI
===============
Console UI for qBittorrent. Functional...but a little rough around the edges...

![qbittorrentui screenshot 1](https://i.imgur.com/iGM3bPI.png)

![qbittorrentui screensho 2t](https://i.imgur.com/msRNi86.png)

Key Map
-------
Any Window
* q : exit

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
```bash
pip install git+https://github.com/rmartin16/qbittorrentui.git

python -c 'import qbittorrentui'
```

Configuration
-------------
If qBittorrent WebUI is using an untrusted (e.g. self-signed) cert:
* ```export PYTHON_QBITTORRENTAPI_DO_NOT_VERIFY_WEBUI_CERTIFICATE=1```

For right now, set the env vars below to automatically connect to qbittorrent:
* ```PYTHON_QBITTORRENTAPI_HOST```
* ```PYTHON_QBITTORRENTAPI_USERNAME```
* ```PYTHON_QBITTORRENTAPI_PASSWORD```

TODO/Wishlist
-------------
Application
 - [ ] Figure out the theme(s)
 - [ ] Configuration for connections
 - [ ] Log/activity output (likely above status bar)

Torrent List Window
 - [ ] Torrent sorting
 - [ ] Additional torrent filtering mechanisms
 - [ ] Torrent searching
 - [ ] Torrent status icon in torrent name
 - [ ] Torrent name color coding

Torrent Window
 - [ ] Make focus more obvious when switching between tabs list and a display
 - [ ] Scrollbar in the displays
 - [ ] Speed graph display

Torrent Window Content Display
 - [ ] Left key should return to tab list
