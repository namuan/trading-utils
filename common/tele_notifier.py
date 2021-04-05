import os

import requests
from dotenv import load_dotenv

load_dotenv()

CHAT_ID = os.getenv("CHAT_ID")
BOT_TOKEN = os.getenv("BOT_TOKEN")


def get_url(method, token):
    return "https://api.telegram.org/bot{}/{}".format(token, method)


def send_file_to_telegram(message, file_path, override_chat_id=None):
    data = {
        "chat_id": override_chat_id or CHAT_ID,
        "text": message,
    }
    files = {"document": open(file_path, "rb")}
    r = requests.post(get_url("sendDocument", BOT_TOKEN), files=files, data=data)
    return r


def send_message_to_telegram(
    message, format="Markdown", disable_web_preview=True, override_chat_id=None
):
    data = {
        "chat_id": override_chat_id or CHAT_ID,
        "text": message,
        "parse_mode": format,
        "disable_web_page_preview": disable_web_preview,
    }
    requests.post(get_url("sendMessage", BOT_TOKEN), data=data)
