### Sample Reports

> Risk Warning: We do not guarantee accuracy and will not accept liability for any loss or damage which arise directly or indirectly from use of or reliance on information contained within these reports. We may provide general commentary which is not intended as investment advice and must not be construed as such. Trading/Investments carries a risk of losses in excess of your deposited funds and may not be suitable for all investors. Please ensure that you fully understand the risks involved.
 
#### S&P500 companies with most daily gains

```shell
py report_by_query.py -t "SP500 Daily Movers" -q "(is_large_cap == True)" -o "daily_close_change_delta_1" -v
```

#### S&P500 companies with most weekly gains

```shell
py report_by_query.py -t "SP500 Weekly Movers" -q "(is_large_cap == True)" -o "week_1_close_change_delta_1" -v
```

#### S&P500 companies with most monthly gains

```shell
py report_by_query.py -t "SP500 Monthly Movers" -q "(is_large_cap == True)" -o "month_1_close_change_delta_1" -v
```

### Scanners

EMA Bounce
```shell
py report_by_query.py -t "EMA Bounce" -q "(day_0_ema_60 < day_0_ema_50 < day_0_ema_45 < day_0_ema_40 < day_0_ema_35 < last_close < day_0_ema_30) and (adx_14 > 35) and (daily_strat.str.contains('.*-2d-2d')) and (daily_strat_candle.str.contains('.*-red-green$'))" -o "natr_30" -v
```

```shell
py report_by_query.py -t "EMA 8x21 Pullback" -q "(day_0_ema_60 < day_0_ema_50 < day_0_ema_45 < day_0_ema_40 < day_0_ema_35 < day_0_ema_21 < day_0_ema_8) and (vol_ema_3 > vol_ema_5 > vol_ema_7) and (last_low > day_0_ema_21) and (last_low < day_0_ema_8) and (adx_14 < 30) and (adx_9 > adx_14 > adx_21)" -o "natr_30" -v
```

```shell
py report_by_query.py -t "UpTrend" -q "(day_0_ema_3 > day_0_ema_5 > day_0_ema_7 > day_0_ema_9 > day_0_ema_11 > day_0_ema_13 > day_0_ema_15 > day_0_ema_21 > day_0_ema_30 > day_0_ema_35 > day_0_ema_40 > day_0_ema_45 > day_0_ema_50 > day_0_ema_60)" -o "smooth_30" -v
```

```shell
# 21 x 50
py report_by_query.py -t "UpTrend" -q "(day_0_ema_21 > day_0_ema_50) and (last_high > day_0_ema_8) and (last_low < day_0_ema_8)" -o "smooth_30" -v
```

```shell
# 8 x 21 CrossOver (Possible Beginning of new trend)
py report_by_query.py -t "8x21" -q "(last_close > 100) and (last_close > day_0_ema_8) and (day_0_ema_8 > day_0_ema_21) and (day_1_ema_8 < day_1_ema_21)" -o "natr_30" -v
```

```shell
py report_by_query.py -t "Ema21 Bounce" -q "(day_0_ema_8 > day_0_ema_21) and (day_0_ema_8 > day_0_ema_21) and (last_high < day_0_ema_8) and (last_low > day_0_ema_21) and (daily_strat_candle.str.contains('.*-red-green$'))" -o "smooth_30" -v
```

```shell
py report_by_query.py -t "Power of 3 Daily" -q "(power_of_3_daily == True)" -o natr_30 -v
```

```shell
py report_by_query.py -t "Power of 3 Weekly" -q "(power_of_3_week_1 == True) and (last_close < day_0_boll_21_2)" -o natr_30 -v
```

```shell
py report_by_query.py -t "⬆ 5D Volume" -o natr_30 -v -q "(last_volume > day_2_volume > day_3_volume > day_4_volume > day_5_volume > day_6_volume > day_7_volume > day_8_volume > day_9_volume)"
```

```shell
py report_by_query.py -t "⬆ 4D Vol/R-G-G Candles" -o natr_30 -v -q "(last_volume > day_2_volume > day_3_volume > day_4_volume) and (daily_strat_candle.str.contains('red-green-green$'))"
```

```shell
py report_by_query.py -t "⬆ 2W Vol/GG Candles" -o natr_30 -v -q "(week_0_volume > week_1_volume > week_2_volume > week_3_volume and (week_1_strat.str.contains('2d-2d-2u$')) and (week_1_strat_candle.str.contains('.*-green-green$')))"
```

```shell
py report_by_query.py -t "123 Pullbacks(Daily)" -q "(adx_14 > 35) and (pdi_14 > mdi_14) and (daily_strat.str.contains('2d-2d-2u$'))" -o natr_30 -v
```

```shell
# Track - Buy when cross-up week high
py report_by_query.py -t "123 Pullbacks(week_1)" -q "(adx_14 > 35) and (pdi_14 > mdi_14) and (week_1_strat.str.contains('2d-2d-2u$'))" -o natr_30 -v
```

```shell
# Oversold and mean reversion
py report_by_query.py -t "Mean Rev 50 LowerBB" -o natr_30 -v -q "(daily_strat_candle.str.contains('.*-red-green$')) and (last_close < day_0_boll_50_3_lb)"
```

```shell
py report_by_query.py -t "Mean Rev LowerBB" -o natr_30 -v -q "(daily_strat_candle.str.contains('.*-green$')) and (last_close < day_0_boll_21_2_lb)"
```

```shell
# boll_21_3_lb -> bollinger ban 21 day MA, 3 Stdev Lowerband
py report_by_query.py -t "Mean Reversion 21 LowerBB" -o natr_30 -v -q "(last_close < day_0_boll_21_3_lb) and (daily_strat_candle.str.contains('.*-green$'))"
```

```shell
py report_by_query.py -t "Squeeze Up" -o natr_30 -v -q "(daily_strat.str.contains('.*-2u$')) and (daily_strat_candle.str.contains('.*-green$')) and (week_1_strat.str.contains('.*-1$')) and (week_1_strat_candle.str.contains('.*-green$'))"
```

```shell
./rbq "(daily_strat.str.contains('.*-2u$')) and (daily_strat_candle.str.contains('.*-green$')) and (week_1_strat.str.contains('.*-1$')) and (week_1_strat_candle.str.contains('.*-green$'))"
```

```shell
py report_by_query.py -t "Momentum Trending" -q "last_close > day_0_ema_3 > day_0_ema_5 > day_0_ema_7 > day_0_ema_9 > day_0_ema_11 > day_0_ema_13 > day_0_ema_30 > day_0_ema_35 > day_0_ema_40 > day_0_ema_45 > day_0_ema_50 > day_0_ema_55 > day_0_ema_60" -o green_candles_30 -v
```

```shell
py report_by_query.py -t "Boomer" -q "(daily_strat.str.contains('.*-1-1$')) and (daily_strat_candle.str.contains('.*-green-green$'))" -o natr_30 -v
```

```shell
py report_by_query.py -t "Boomer" -q "(month_1_strat.str.contains('1-1-1$')) and (month_1_strat_candle.str.contains('.*-green-green$'))" -o natr_30 -v
```

```shell
py report_by_query.py -t "Boomer" -q "(last_volume > 100000) and (month_3_strat.str.contains('.*-1-1$')) and (week_1_strat_candle.str.contains('red-green-green$'))" -o monthly_gains_1 -v
```

```shell
py report_by_query.py -t "KC inside BB Channel" -o natr_30 -v -q "(boll_ub < kc_ub) and (boll_lb > kc_lb) and (vol_ema_3 > vol_ema_5 > vol_ema_7) and (daily_strat.str.contains('.*-2u$')) and (daily_strat_candle.str.contains('.*-green$'))"
```

```shell
# Read symbols from file and generate report
QUERY=$(SYMBOLS=$(cat file.csv | awk -F\, '{print $1}' | grep -v symbol | while read line; do echo "'$line'"; done | tr '\n' ','); echo "(symbol in ($SYMBOLS))"); ./rbq $QUERY
```

```shell
py report_by_query.py -t "BB lb (oversold)" -o natr_30 -v -q "(day_5_low < day_4_boll_21_2_lb) and (day_4_low < day_3_boll_21_2_lb) and (day_3_low < day_2_boll_21_2_lb) and (last_low > day_0_boll_21_2_lb) and (daily_strat_candle.str.contains('.*-green$'))"
```

```shell
# Few days down in a row
py report_by_query.py -t "9 Days Down in a row" -o natr_30 -v -q "(day_2_low < day_3_low < day_4_low < day_5_low < day_6_low < day_7_low < day_8_low < day_9_low < day_10_low)"
```

```shell
# Parabolic moves
py report_by_query.py -t "Month Change" -o month_1_close_change_delta_1 -v -q "(month_1_close_change_delta_1 > 50)" 
```

```shell
py report_by_query.py -o smooth_30 -t "4RSI" -v -q "(last_close < 100) and (last_close > day_0_ma_50) and (monthly_gains_3 > 0) and (day_0_rsi_2 < 10)"
```

```shell
py report_by_query.py -o smooth_30 -t "AllRSI" -v -q "(day_0_rsi_2 < 10) and (day_0_rsi_4 < 10) and (day_0_rsi_9 < 10) and (last_close > 10)"
```

```shell
py report_by_query.py -o smooth_30 -t "RSI3 Bounce" -v -q "last_close > 10 and week_1_rsi_3 < 5 and week_0_rsi_3 > 5 and week_0_rsi_3 < 10"
py report_by_query.py -o smooth_30 -t "RSI4 Bounce" -v -q "last_close > 10 and day_2_rsi_4 < 15 and day_1_rsi_4 > 15 and day_0_rsi_4 > 15"
```

```shell
py report_by_query.py -o smooth_90 -v -t "Long Key Reversal" -q "((day_2_low < day_3_low) and (last_close > day_3_high) and (last_close > day_2_high)) and (daily_strat_candle.str.contains('red-red-green$')) and (last_close > day_0_ema_8 > day_0_ema_21) and (week_1_strat_candle.str.contains('.*-green$'))"
```

```shell
py report_by_query.py -o smooth_90 -v -t "Long Key Reversal 2" -q "((week_2_low < week_3_low) and (last_close > week_3_high) and (last_close > week_2_high))"
```

```shell
py report_by_query.py -o smooth_90 -v -t "Long base and Breakout" -q "(last_volume < day_2_volume) and (last_low < day_2_high) and (last_close > month_1_high) and (last_close > month_2_high) and (last_close > month_3_high) and (day_2_volume < last_close)"
```

```shell
py report_by_query.py -t "MMA Breakout" -q "(last_close > day_0_ema_3 > day_0_ema_5 > day_0_ema_7 > day_0_ema_9 > day_0_ema_11 > day_0_ema_13) and (last_close < day_0_ema_30 < day_0_ema_35 < day_0_ema_40 < day_0_ema_45 < day_0_ema_50 < day_0_ema_55 < day_0_ema_60)" -o green_candles_30 -v
```

```shell
# last_candle is 3x previous candle, last_volume is 3x previous candle volume
./rbq "(last_close > 10) and (abs(last_high - last_close) < 3 * abs(day_2_high - day_2_low)) and (last_volume > day_2_volume * 3) and (daily_strat_candle.str.contains('.*-green-green$')) and (daily_strat.str.contains('.*-2u$'))"
```

```shell
# Volume/Price divergence/convergence
./rbq "(vol_ma_3 > vol_ma_5 > vol_ma_7 > vol_ma_9 > vol_ma_11 > vol_ma_13 > vol_ma_15 > vol_ma_17 > vol_ma_19 > vol_ma_21) and (day_0_ma_3 < day_0_ma_5 < day_0_ma_7 < day_0_ma_9 < day_0_ma_11 < day_0_ma_13 < day_0_ma_15)"
```

```shell
./rbq "(day_2_volume > day_3_volume > day_4_volume > day_5_volume > day_6_volume) and (day_2_close < day_3_close < day_4_close < day_5_close < day_6_close < day_7_close)"
```

S&P Equal Weighted ETFs
```shell
QUERY=$(SYMBOLS=$(cat data/equal-weighted.csv | awk -F\, '{print $1}' | grep -v symbol | while read line; do echo "'$line'"; done | tr '\n' ','); echo "(symbol in ($SYMBOLS))"); ./rbq $QUERY
```

S&P Sector ETFs
```shell
QUERY=$(SYMBOLS=$(cat data/sector-etfs.csv | awk -F\, '{print $1}' | grep -v symbol | while read line; do echo "'$line'"; done | tr '\n' ','); echo "(symbol in ($SYMBOLS))"); ./rbq $QUERY
```


QUERY=$(SYMBOLS=$(cat combined_output.csv | awk -F\, '{print $1}' | grep -v symbol | while read line; do echo "'$line'"; done | tr '\n' ','); echo "(symbol in ($SYMBOLS))"); ./rbq $QUERY
