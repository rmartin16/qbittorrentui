import argparse
from pathlib import Path

from platformdirs import user_config_dir

from qbittorrentui.main import run


def main():
    args = parse_args()
    run(args)


def _default_config_file() -> str:
    return str(Path(user_config_dir("qbittorrentui")) / "qbittorrentui.ini")


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
