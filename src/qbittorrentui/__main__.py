import argparse
import os
from pathlib import Path

from qbittorrentui.main import run


def main():
    args = parse_args()
    run(args)


def _default_config_file() -> str:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        config_home = Path(xdg_config_home)
    else:
        config_home = Path.home() / ".config"

    return str(config_home / "qbittorrentui" / "qbittorrentui.ini")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c",
        "--config_file",
        type=str,
        default=_default_config_file(),
        help="configuration ini file",
    )

    args = parser.parse_args()

    return args


if __name__ == "__main__":
    main()
