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

Right now, short of editing main.py, set these env vars to connect to qBittorrent
* ```PYTHON_QBITTORRENTAPI_HOST```
* ```PYTHON_QBITTORRENTAPI_USERNAME```
* ```PYTHON_QBITTORRENTAPI_PASSWORD```
