export PROJECTNAME=$(shell basename "$(PWD)")
VENV_PATH=./.venv/bin
DTALE=./venv/bin/dtale

.SILENT: ;               # no need for @

setup: ## Setup Virtual Env
	python3.12 -m venv venv
	$(VENV_PATH)/python3 -m pip install --upgrade pip
	$(PIP) install -r requirements/dev.txt

deps: ## Install dependencies
	uv tool install pre-commit
	uv pip install -r requirements.txt

pre-commit: ## Manually run all precommit hooks
	uv tool run pre-commit

pre-commit-tool: ## Manually run a single pre-commit hook
	$(VENV_PATH)/pre-commit run $(TOOL) --all-files

clean: ## Clean package
	find . -type d -name '__pycache__' | xargs rm -rf
	rm -rf build dist

bpython: ## Run bpython
	$(VENV_PATH)/bpython

ftplist: ## Download stocks from Nasdaq FTP Server
	$(VENV_PATH)/python3 download_stocklist.py

stocksohlcv: ## Download OHLCV of all available stocks
	$(VENV_PATH)/python3 download_stocks_ohlcv.py

etfsohlcv: ## Download OHLCV of all Macro ETFs
	$(VENV_PATH)/python3 download_macro_etfs.py

weeklyoptions: ## Download list of Symbols with weekly options
	$(VENV_PATH)/python3 download_weekly_option_symbols.py -v

enrich: ## Enrich data and calculate indicators
	$(VENV_PATH)/python3 stocks_data_enricher.py
	$(VENV_PATH)/python3 tele_message.py -m "Completed data enrichment"

dtale: ## Open DTale
	uvx dtale --open-browser --csv-path $(csvpath)

weekend: ftplist stocksohlcv etfsohlcv enrich ## Refreshes stock list, download OHLCV data and run analysis

deploy: clean ## Copies any changed file to the server
	ssh ${PROJECTNAME} -C 'bash -l -c "mkdir -vp ./${PROJECTNAME}/output"'
	rsync -avzr \
		.env \
		data \
		common \
		scripts \
		crypto_ma_trade_bot.py \
		crypto_rsi_trade_bot.py \
		crypto_strat_bot.py \
		tele_spy_trade_bot.py \
		tele_links.py \
		tele_twitter.py \
		options_price_tracker.py \
		tele_theta_gang_bot.py \
		tele_spx_theta_gang_bot.py \
		tele_stock_alerts_bot.py \
		tqqq-for-the-long-run.py \
		yfinance-box.py \
		webpages.txt \
		requirements \
		requirements.txt \
		${PROJECTNAME}:./${PROJECTNAME}

start: deploy ## Sets up a screen session on the server and start the app
	ssh ${PROJECTNAME} -C 'bash -l -c "./${PROJECTNAME}/scripts/setup_apps.sh ${PROJECTNAME}"'

stop: deploy ## Stop any running screen session on the server
	ssh ${PROJECTNAME} -C 'bash -l -c "./${PROJECTNAME}/scripts/stop_apps.sh ${PROJECTNAME}"'

ssh: ## SSH into the target VM
	ssh ${PROJECTNAME}

syncoptionspricedata: ## Sync options price tracker database
	rm ~/options_tracker.db; rsync -avzr ${PROJECTNAME}:./options_tracker.db ~/options_tracker.db

synccryptobotdiary: ## Sync crypto bot diary
	rm ~/crypto_trade_diary.db; rsync -avzr ${PROJECTNAME}:./crypto_trade_diary.db ~/crypto_trade_diary.db

.PHONY: help
.DEFAULT_GOAL := help

help: Makefile
	echo
	echo " Choose a command run in "$(PROJECTNAME)":"
	echo
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'
	echo
