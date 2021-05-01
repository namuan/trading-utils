from telegram import Update


def start(update: Update, _) -> None:
    update.message.reply_text("Hi!")


def help_command(update: Update, _) -> None:
    update.message.reply_text("Help!")
