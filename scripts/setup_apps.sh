cd $1 || exit
test -d venv || python3 -m venv venv
#venv/bin/pip3 install -r requirements.txt --user
bash ./scripts/start_screen.sh tele-spy-trade-bot 'venv/bin/python3 tele_spy_trade_bot.py --run-as-bot -v'
bash ./scripts/start_screen.sh tele-theta-gang-bot 'venv/bin/python3 tele_theta_gang_bot.py --run-as-bot -v'
bash ./scripts/start_screen.sh tele-spx-theta-gang-bot 'venv/bin/python3 tele_spx_theta_gang_bot.py --run-as-bot -v'
