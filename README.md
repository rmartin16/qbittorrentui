qBittorrenTUI
===============
Console UI for qBittorrent

![qbittorrentui screenshot 1](https://i.imgur.com/iGM3bPI.png)

![qbittorrentui screensho 2t](https://i.imgur.com/msRNi86.png)

Since qBittorrent communication is currently happening in the UI thread, this should only be run with a fast, low latency connection to qBittorrent.

Installation
------------
```bash
pip install git+https://github.com/rmartin16/qbittorrentui.git

python -c 'import qbittorrentui; qbittorrentui.run()'
```

Configuration
-------------
If qBittorrent WebUI is using an untrusted (e.g. self-signed) cert:
* ```export PYTHON_QBITTORRENTAPI_DO_NOT_VERIFY_WEBUI_CERTIFICATE=1```

Using the urwid framework.
