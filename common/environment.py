import os

from dotenv import load_dotenv

load_dotenv()

EXCHANGE_API_KEY = os.getenv("EXCHANGE_API_KEY")
EXCHANGE_API_SECRET = os.getenv("EXCHANGE_API_SECRET")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")
EXCHANGE = os.getenv("EXCHANGE")
