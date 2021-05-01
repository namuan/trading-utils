### Sample Reports

> Risk Warning: We do not guarantee accuracy and will not accept liability for any loss or damage which arise directly or indirectly from use of or reliance on information contained within these reports. We may provide general commentary which is not intended as investment advice and must not be construed as such. Trading/Investments carries a risk of losses in excess of your deposited funds and may not be suitable for all investors. Please ensure that you fully understand the risks involved.
 
#### S&P500 companies with most daily gains

```shell
py report_by_query.py -t "SP500 Daily Movers" -q "(is_large_cap == True)" -o "daily_close_change_delta_1" -v
```

#### S&P500 companies with most weekly gains

```shell
py report_by_query.py -t "SP500 Weekly Movers" -q "(is_large_cap == True)" -o "weekly_close_change_delta_1" -v
```

#### S&P500 companies with most monthly gains

```shell
py report_by_query.py -t "SP500 Monthly Movers" -q "(is_large_cap == True)" -o "monthly_close_change_delta_1" -v
```

#### EMA Bounce

```shell
py report_by_query.py -t "EMA Bounce" -q "(ema_60 < ema_50 < ema_45 < ema_40 < ema_35 < last_close < ema_30) and (adx_14 > 35)" -o "smooth_30" -v
```

#### Strat 3-2up

```shell
py report_by_query.py -t "Strat Daily 3-2dn(green)" -q "(daily_strat_direction ==  'down') and (daily_strat == '3-2') and (daily_strat_candle == 'green') and (weekly_strat_candle == 'green') and (monthly_strat_candle == 'green')" -v
```