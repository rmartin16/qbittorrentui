import configparser
from os import path as os_path


class Configuration(configparser.ConfigParser):
    def __init__(self):
        super(Configuration, self).__init__()
        # load default configuration
        self.read(os_path.join(os_path.split(__file__)[0], "default.ini"))
        self._section = "DEFAULT"

    def set_default_section(self, section: str = ""):
        self._section = section

    def get(self, option: str, section: str = None):
        if section:
            return super(Configuration, self).get(
                section=section, option=option, raw=True
            )
        return super(Configuration, self).get(
            section=self._section, option=option, raw=True
        )

    def set(self, option: str, value: str, section: str = None):
        if section:
            super(Configuration, self).set(section=section, option=option, value=value)
        super(Configuration, self).set(
            section=self._section, option=option, value=value
        )


# CONSTANTS
APPLICATION_NAME = "qBittorrenTUI"
# when a count of seconds should just be represented as infinity
SECS_INFINITY = 100 * 24 * 60 * 60  # 100 days
INFINITY = "\u221E"  # ∞
DOWN_TRIANGLE = "\u25BC"  # ▼
UP_TRIANGLE = "\u25B2"  # ▲
UP_ARROW = "\u21D1"  # ⇑
STATE_MAP_FOR_DISPLAY = {
    "pausedUP": "Completed",
    "uploading": "Seeding",
    "stalledUP": "Seeding",
    "forcedUP": "[F] Seeding",
    "queuedDL": "Queued",
    "queuedUP": "Queued",
    "pausedDL": "Paused",
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
        "forcedDL",
    ],
    "completed": [
        "uploading",
        "stalledUP",
        "checkingUP",
        "pausedUP",
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
        "stalledUP",
        "stalledDL",
        "queuedDL",
        "queuedUP",
        "pausedDL",
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
        "queuedDL",
        "queuedUP",
        "pausedDL",
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
