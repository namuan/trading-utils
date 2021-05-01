from telegram import Update


def start(update: Update, _) -> None:
    update.message.reply_text(
        "👋 Enter a stock ticker with a $ sign. Eg: $TSLA"
    )


def help_command(update: Update, _) -> None:
    update.message.reply_text("Help!")
