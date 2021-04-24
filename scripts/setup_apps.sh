cd trading-utils || exit
#pip3 install -r requirements/base.txt --user
bash ./scripts/start_screen.sh crypto-ma-trade-bot 'python3 crypto_ma_trade_bot.py'
bash ./scripts/start_screen.sh tele-links 'python3 tele_links.py'
bash ./scripts/start_screen.sh tele-twitter 'python3 tele_twitter.py'
