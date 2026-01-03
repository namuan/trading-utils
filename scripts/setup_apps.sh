cd $1 || exit
#uv sync --no-dev
#venv/bin/pip3 install -r requirements.txt --user
bash ./scripts/start_screen.sh tqqq-vol-buckets 'uv run tqqq-vol-buckets.py -v --send-alert'
bash ./scripts/start_screen.sh tqqq-vol-regimes 'uv run tqqq-vol-regimes.py -v --send-telegram'
exit 0
bash ./scripts/start_screen.sh tele-spy-trade-bot 'uv run --no-project tele_spy_trade_bot.py --run-as-bot -v'
bash ./scripts/start_screen.sh tele-theta-gang-bot 'uv run --no-project tele_theta_gang_bot.py --run-as-bot -v'
bash ./scripts/start_screen.sh tele-spx-theta-gang-bot 'uv run --no-project tele_spx_theta_gang_bot.py --run-as-bot -v'
