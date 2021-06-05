export PROJECTNAME=$(shell basename "$(PWD)")
PY=./venv/bin/python3
DTALE=./venv/bin/dtale

.SILENT: ;               # no need for @

setup: ## Setup Virtual Env
	python3 -m venv venv
	./venv/bin/pip3 install -r requirements/dev.txt

deps: ## Install dependencies
	./venv/bin/pip3 install -r requirements/dev.txt

lint: ## Run black for code formatting
	./venv/bin/black . --exclude venv

clean: ## Clean package
	find . -type d -name '__pycache__' | xargs rm -rf
	rm -rf build dist

bpython: ## Run bpython
	./venv/bin/bpython

ftplist: ## Download stocks from Nasdaq FTP Server
	$(PY) download_stocklist.py

stocksohlcv: ## Download OHLCV of all available stocks
	$(PY) download_stocks_ohlcv.py

etfsohlcv: ## Download OHLCV of all Macro ETFs
	$(PY) download_macro_etfs.py

enrich: ## Enrich data and calculate indicators
	$(PY) stocks_data_enricher.py
	$(PY) tele_message.py -m "Completed data enrichment"

dtale: ## Open DTale
	$(DTALE) --open-browser --csv-path $(csvpath)

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
		tele_stock_rider_bot.py \
		tele_theta_gang_bot.py \
		webpages.txt \
		twitter_furus.py \
		twitter_furus_accounts.txt \
		requirements \
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