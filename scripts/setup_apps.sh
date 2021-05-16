cd trading-utils || exit
#pip3 install -r requirements/base.txt --user
bash ./scripts/start_screen.sh tele-links 'python3 tele_links.py'
#bash ./scripts/start_screen.sh tele-twitter 'python3 tele_twitter.py'
bash ./scripts/start_screen.sh options-price-tracker 'python3 options_price_tracker.py -t SPX,XHB,XLC,XLY,XLP,XLE,XLF,XLV,XLI,XLB,XLR,XLK,XME,XOP,GDX,IYR,XLU'
bash ./scripts/start_screen.sh tele-stock-rider-bot 'python3 tele_stock_rider_bot.py'
bash ./scripts/start_screen.sh tele-theta-gang-bot 'python3 tele_theta_gang_bot.py'
bash ./scripts/start_screen.sh strat-usdt 'python3 crypto_strat_bot.py --strategy strat --buying-budget 10 --coins ADA,XLM,MATIC,DOGE --stable-coin USDT --time-frame 5m --wait-in-minutes 15'
#bash ./scripts/start_screen.sh 1-usdt-trade-bot 'python3 crypto_ma_trade_bot.py --strategy ma --buying-budget 50 --coins ADA,XLM,MATIC --target-pct 2 --stable-coin USDT --time-frame 5m --wait-in-minutes 1'
bash ./scripts/start_screen.sh 2-usdt-trade-bot 'python3 crypto_rsi_trade_bot.py --strategy rsi --buying-budget 100 --coins ADA,XLM,DOGE,XRP --target-pct 2 --stable-coin USDT --time-frame 5m --wait-in-minutes 1'
