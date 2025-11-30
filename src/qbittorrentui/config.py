import configparser
from os import path as os_path


class Configuration(configparser.ConfigParser):
    def __init__(self):
        super().__init__()
        # load default configuration
        self.read(os_path.join(os_path.split(__file__)[0], "default.ini"))
        self._section = "DEFAULT"

    def set_default_section(self, section: str = ""):
        self._section = section

    def get(self, option: str, section: str = None):
        if section:
            return super().get(section=section, option=option, raw=True)
        return super().get(section=self._section, option=option, raw=True)

    def set(self, option: str, value: str, section: str = None):
        if section:
            super().set(section=section, option=option, value=value)
        super().set(section=self._section, option=option, value=value)


# CONSTANTS
APPLICATION_NAME = "qBittorrenTUI"
# when a count of seconds should just be represented as infinity
SECS_INFINITY = 100 * 24 * 60 * 60  # 100 days
INFINITY = "\u221e"  # ∞
DOWN_TRIANGLE = "\u25bc"  # ▼
UP_TRIANGLE = "\u25b2"  # ▲
UP_ARROW = "\u21d1"  # ⇑
STATE_MAP_FOR_DISPLAY = {
    "pausedUP": "Completed",
    "stoppedUP": "Completed",
    "uploading": "Seeding",
    "stalledUP": "Seeding",
    "forcedUP": "[F] Seeding",
    "queuedDL": "Queued",
    "queuedUP": "Queued",
    "pausedDL": "Paused",
    "stoppedDL": "Paused",
    "checkingDL": "Checking",
    "checkingUP": "Checking",
    "downloading": "Downloading",
    "forcedDL": "[F] Downloading",
    "forcedMetaDL": "[F] Metadata DL",
    "metaDL": "Metadata DL",
    "stalledDL": "Stalled",
    "allocating": "Allocating",
    "moving": "Moving",
    "missingfiles": "Missing Files",
    "error": "Error",
    "queuedForChecking": "Queued for Checking",
    "checkingResumeData": "Checking Resume Data",
}
TORRENT_LIST_FILTERING_STATE_MAP = {
    "downloading": [
        "downloading",
        "forcedMetaDL",
        "metaDL",
        "queuedDL",
        "stalledDL",
        "pausedDL",
        "stoppedDL",
        "forcedDL",
    ],
    "completed": [
        "uploading",
        "stalledUP",
        "checkingUP",
        "pausedUP",
        "stoppedUP",
        "queuedUP",
        "forcedUP",
    ],
    "active": [
        "metaDL",
        "forcedMetaDL",
        "downloading",
        "forcedDL",
        "uploading",
        "forcedUP",
        "moving",
    ],
    "inactive": [
        "pausedUP",
        "stoppedUP",
        "stalledUP",
        "stalledDL",
        "queuedDL",
        "queuedUP",
        "pausedDL",
        "stoppedDL",
        "checkingDL",
        "checkingUP",
        "allocating",
        "missingfiles",
        "error",
        "queuedForChecking",
        "checkingResumeData",
    ],
    "paused": [
        "pausedUP",
        "stoppedUP",
        "queuedDL",
        "queuedUP",
        "pausedDL",
        "stoppedDL",
        "missingfiles",
        "error",
        "queuedForChecking",
        "checkingResumeData",
    ],
    "resumed": [
        "uploading",
        "stalledUP",
        "forcedUP",
        "checkingDL",
        "checkingUP",
        "downloading",
        "forcedDL",
        "metaDL",
        "forcedMetaDL",
        "stalledDL",
        "allocating",
        "moving",
    ],
}

# CONFIGURATION STORE
config = Configuration()
