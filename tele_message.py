from argparse import ArgumentParser

from common.environment import GROUP_CHAT_ID
from common.tele_notifier import send_message_to_telegram


def send_link(website_url):
    if website_url.startswith("#"):
        return

    try:
        send_message_to_telegram(
            website_url, disable_web_preview=False, override_chat_id=GROUP_CHAT_ID
        )
    except Exception as e:
        print(f"Error processing: {website_url} - {str(e)}")


def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "-m", "--message", type=str, required=True, help="Sends message on telegram"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    message = args.message
    send_message_to_telegram(message, override_chat_id=GROUP_CHAT_ID)


if __name__ == "__main__":
    main()
