import logging
import asyncio
import blinker

from qbittorrentui.connector import Connector
from qbittorrentui.connector import ConnectorError

logger = logging.getLogger(__name__)


async def start(main, loop=asyncio.get_event_loop()):
    loop.create_task(update_torrent_info(main, loop))


async def update_torrent_info(main, loop):
    client = main.torrent_client
    md = client.sync_maindata(0)
    logger.info(md)
    await asyncio.sleep(3)
    loop.create_task(update_torrent_info(main, loop))


class ClientPoller:
    client: Connector

    def __init__(self, main):
        self.main = main
        self.client = main.torrent_client
        self.rid = 0
        self.maindata_ready = blinker.signal('maindata ready')

    async def start_polling(self):
        self.aioloop.create_task()

    async def start(self):
        while True:
            try:
                await self.run_update()
            except ConnectorError:
                pass
            finally:
                await asyncio.sleep(2)

    async def run_update(self):
        md = self.client.sync_maindata(self.rid)
        self.rid = md.get('rid', self.rid)
        logger.info("RID: %s" % self.rid)
        self.main.torrent_list_window.md = md
        # logger.info(self.maindata_ready.send('maindata poller'))
        self.main.torrent_list_window.refresh_with_maindata(md)

