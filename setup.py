from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="qbittorrentui",
    version="0.3.3",
    packages=find_packages(exclude=["*.tests", "*.tests.*", "tests.*", "tests"]),
    package_data={"": ["default.ini"]},
    include_package_data=True,
    install_requires=[
        "urwid==2.1.2",
        "qbittorrent-api",
        "blinker-alt==1.5",
        "panwid==0.3.4",
    ],
    entry_points={"console_scripts": ["qbittorrentui = qbittorrentui.__main__:main"]},
    url="https://github.com/rmartin16/qbittorrentui",
    author="Russell Martin",
    author_email="rmartin16@gmail.com",
    zip_safe=False,
    license="GPL-3",
    description="Console UI for qBittorrent v4.1+",
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords="qbittorrent console terminal TUI text",
    classifiers=[
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.8",
        "Environment :: Console",
        "License :: OSI Approved :: MIT License",
        "Topic :: Communications :: File Sharing",
        "Topic :: Utilities",
    ],
)
