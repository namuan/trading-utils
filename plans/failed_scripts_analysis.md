# Scripts Failing --help Test

## Failed Scripts and Reasons

### 1. tele_stock_alerts_bot.py
**Reason:** Missing `dotenv` dependency
- Error: `ModuleNotFoundError: No module named 'dotenv'`
- Import location: `common/environment.py:3`

### 2. tele_twitter.py
**Reason:** Missing `dotenv` dependency
- Error: `ModuleNotFoundError: No module named 'dotenv'`
- Import location: `common/environment.py:3`

### 3. report_relative_strength.py
**Reason:** Missing `finta` dependency
- Error: `ModuleNotFoundError: No module named 'finta'`
- Import location: `common/analyst.py:7`

### 4. download_earnings.py
**Reason:** Missing `pandas` dependency
- Error: `ModuleNotFoundError: No module named 'pandas'`
- Import location: `common/market.py:4`

### 5. crypto_ma_trade_bot.py
**Reason:** Missing `finta` dependency
- Error: `ModuleNotFoundError: No module named 'finta'`
- Import location: `common/analyst.py:7`

### 6. crypto_mma_trade_bot.py
**Reason:** Missing `finta` dependency
- Error: `ModuleNotFoundError: No module named 'finta'`
- Import location: `common/analyst.py:7`

### 7. crypto_rsi_trade_bot.py
**Reason:** Missing `finta` dependency
- Error: `ModuleNotFoundError: No module named 'finta'`
- Import location: `common/analyst.py:7`

### 8. crypto_strat_bot.py
**Reason:** Missing `finta` dependency
- Error: `ModuleNotFoundError: No module named 'finta'`
- Import location: `common/analyst.py:7`

### 9. 9sig_kelly.py
**Reason:** Argument parsing error
- Error: `ValueError: unsupported format character ' ' (0x20) at index 62`
- Issue: Invalid format string in argparse help text

### 10. composer-csv-processor.py
**Reason:** Missing `yfinance` dependency
- Error: `ModuleNotFoundError: No module named 'yfinance'`
- Import location: `common/market_data.py:2`

### 11. download_stocks_ohlcv.py
**Reason:** Missing `pandas` dependency
- Error: `ModuleNotFoundError: No module named 'pandas'`
- Import location: `common/market.py:4`

### 12. options_price_tracker.py
**Reason:** Missing `numpy` dependency
- Error: `ModuleNotFoundError: No module named 'numpy'`
- Import location: `common/analyst.py:5`

### 13. report_by_query.py
**Reason:** Missing `jinja2` dependency
- Error: `ModuleNotFoundError: No module named 'jinja2'`
- Import location: `common/reporting.py:5`

### 14. stocks_data_enricher.py
**Reason:** Timed out during execution
- Issue: Script takes too long to load dependencies or initialize

### 15. ib_ironfly_adjustments.py
**Reason:** Timed out during execution
- Issue: Script takes too long to load dependencies or initialize

### 16. try_enricher.py
**Reason:** Timed out during execution
- Issue: Script takes too long to load dependencies or initialize

### 17. options-3d.py
**Reason:** Timed out during execution
- Issue: Script takes too long to load dependencies or initialize

## Summary

- **Missing Dependencies:** 13 scripts
  - `dotenv`: 2 scripts
  - `finta`: 5 scripts
  - `pandas`: 2 scripts
  - `yfinance`: 1 script
  - `numpy`: 1 script
  - `jinja2`: 1 script

- **Argument Parsing Error:** 1 script (9sig_kelly.py)

- **Timeout Issues:** 4 scripts

## Working Scripts

The following 23 scripts work correctly with `--help`:
- rsi-estimate.py
- value-averaging.py
- spy_performance.py
- download_sp500_companies.py
- download_stocklist.py
- crypto_potential_setups.py
- options_trading_algo.py
- earnings_tracker.py
- portfolio-sizing.py
- spy_bear_market_analysis.py
- compare_stocks_relative_strength.py
- reit-correlation.py
- cage-fight.py
- options_payoff.py
- streamgraph_chart.py
- backtest-scale-in-out.py
- stock-volatility.py
- trend-plotter.py
- weekly-returns-analysis.py
- stock-pct-change.py
- dca-strategy.py
- spy_yearly_gains_viz.py
