import json
import shutil
from pathlib import Path


def mkdir(dir_name, clean_up=True):
    if clean_up:
        shutil.rmtree(dir_name, ignore_errors=True)
    Path(dir_name).mkdir(exist_ok=True)
    return dir_name


def output_dir():
    return mkdir("output", clean_up=False)


def earnings_file_path():
    output_file = "earnings.json"
    return Path(output_dir()).joinpath(output_file)


def file_as_json(file_path):
    return json.load(open(file_path))
