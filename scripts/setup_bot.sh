cd $1 || exit
bash ./scripts/start_screen.sh tele-spy-trade-bot 'uv run --no-project tele_spy_trade_bot.py --run-as-bot -v'
bash ./scripts/start_screen.sh tele-theta-gang-bot 'uv run --no-project tele_theta_gang_bot.py --run-as-bot -v'
bash ./scripts/start_screen.sh tele-spx-theta-gang-bot 'uv run --no-project tele_spx_theta_gang_bot.py --run-as-bot -v'
bash ./scripts/start_screen.sh daily-rebalance-report 'uv run daily-rebalance-report.py --run-as-bot --start-date 2026-01-01 --pdf -v'
