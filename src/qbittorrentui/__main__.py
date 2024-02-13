import argparse

from qbittorrentui.main import run


def main():
    args = parse_args()
    run(args)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c", "--config_file", type=str, default="", help="configuration ini file"
    )

    args = parser.parse_args()

    return args


if __name__ == "__main__":
    main()
