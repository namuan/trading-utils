"""
Downloads available list of tickers from ftp.nasdaqtrader.com servers.
The combined ticker list is saved as csv file in the data folder
"""

import os
from argparse import ArgumentParser
from ftplib import FTP
from pathlib import Path


def parse_args():
    """Parse command line arguments."""
    parser = ArgumentParser(description=__doc__)
    return parser.parse_args()


def download_ftp_files(filenames):
    ftp = FTP("ftp.nasdaqtrader.com")
    ftp.login()
    print("Welcome message: " + ftp.getwelcome())
    ftp.cwd("SymbolDirectory")

    for filename, filepath in filenames.items():
        ftp.retrbinary("RETR " + filename + ".txt", open(filepath, "wb").write)


def combine_list(filenames, all_listed):
    all_listed.write("Symbol,Description\n")
    for filename, filepath in filenames.items():
        with open(filepath, "r") as file_reader:
            for i, line in enumerate(file_reader, 0):
                if i == 0:
                    continue

                line = line.strip().split("|")

                if (
                    line[0] == ""
                    or line[1] == ""
                    or (filename == "nasdaqlisted" and line[6] == "Y")
                    or (filename == "otherlisted" and line[4] == "Y")
                    or "$" in line[0]
                ):
                    continue

                all_listed.write(line[0].replace(".", "") + ',"' + line[1] + '"\n')


def remove_temp_files(filenames):
    for filename, filepath in filenames.items():
        os.remove(filepath)


if __name__ == "__main__":
    args = parse_args()
    Path("data").mkdir(exist_ok=True)

    filenames = {
        "otherlisted": "data/otherlisted.txt",
        "nasdaqlisted": "data/nasdaqlisted.txt",
    }

    all_listed = open("data/alllisted.csv", "w")

    download_ftp_files(filenames)
    combine_list(filenames, all_listed)
    remove_temp_files(filenames)
    print("Download all listed stocks. Check {}".format("data/alllisted.csv"))
