import logging
from time import time, sleep

from qbittorrentui.connector import Connector
from qbittorrentui.connector import ConnectorError
from qbittorrentui.events import sync_maindata_ready
from qbittorrentui.events import refresh_torrent_list_with_remote_data_now

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2


class ClientPoller:
    client: Connector

    def __init__(self, main):
        self.main = main
        self.client = main.torrent_client
        self.rid = 0
        refresh_torrent_list_with_remote_data_now.connect(receiver=self.run_update)

    def start(self):
        while True:
            start_time = time()
            try:
                self.run_update()
            except ConnectorError:
                logger.info("Could not connect to qbittorrent")
            finally:
                poll_time = time() - start_time
                if poll_time < POLL_INTERVAL:
                    sleep(POLL_INTERVAL - poll_time)

    def run_update(self):
        logger.info("Requesting maindata (RID: %s)" % self.rid)
        start_time = time()
        md = self.client.sync_maindata(self.rid)
        self.rid = md.get('rid', self.rid)
        response_time = time() - start_time
        logger.info("Received maindata (RID: %s) in %.3f secs" % (self.rid, response_time))
        sync_maindata_ready.send("client poller", md=md)

