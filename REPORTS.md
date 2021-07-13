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

```shell
py report_by_query.py -t "EMA Bounce" -q "(ema_60 < ema_50 < ema_45 < ema_40 < ema_35 < last_close < ema_30) and (adx_14 > 35) and (daily_strat.str.contains('.*-2d-2d')) and (daily_strat_candle.str.contains('.*-red-green$'))" -o "natr_30" -v

py report_by_query.py -t "EMA 8x21 Pullback" -q "(ema_60 < ema_50 < ema_45 < ema_40 < ema_35 < ema_21 < ema_8) and (vol_ema_3 > vol_ema_5 > vol_ema_7) and (last_low > ema_21) and (last_low < ema_8) and (adx_14 < 30) and (adx_9 > adx_14 > adx_21)" -o "natr_30" -v


py report_by_query.py -t "UpTrend" -q "(ema_3 > ema_5 > ema_7 > ema_9 > ema_11 > ema_13 > ema_15 > ema_21 > ema_30 > ema_35 > ema_40 > ema_45 > ema_50 > ema_60)" -o "smooth_30" -v

# 21 x 50
py report_by_query.py -t "UpTrend" -q "(ema_21 > ema_50) and (last_high > ema_8) and (last_low < ema_8)" -o "smooth_30" -v

py report_by_query.py -t "Ema21 Bounce" -q "(ema_8 > ema_21) and (ema_8 > ema_21) and (last_high < ema_8) and (last_low > ema_21) and (daily_strat_candle.str.contains('.*-red-green$'))" -o "smooth_30" -v
```

```shell
py report_by_query.py -t "Power of 3 Daily" -q "(power_of_3_daily == True)" -o natr_30 -v
py report_by_query.py -t "Power of 3 Weekly" -q "(power_of_3_week_1 == True) and (last_close < boll)" -o natr_30 -v
```

```shell
py report_by_query.py -t "⬆ 5D Volume" -o natr_30 -v -q "(last_volume > day_2_before_last_volume > day_3_before_last_volume > day_4_before_last_volume > day_5_before_last_volume > day_6_before_last_volume > day_7_before_last_volume > day_8_before_last_volume > day_9_before_last_volume)"
py report_by_query.py -t "⬆ 4D Vol/R-G-G Candles" -o natr_30 -v -q "(last_volume > day_2_before_last_volume > day_3_before_last_volume > day_4_before_last_volume) and (daily_strat_candle.str.contains('red-green-green$'))"
py report_by_query.py -t "⬆ 2W Vol/GG Candles" -o natr_30 -v -q "(week_0_volume > week_1_volume > week_2_volume > week_3_volume and (week_1_strat.str.contains('2d-2d-2u$')) and (week_1_strat_candle.str.contains('.*-green-green$')))"
```

```shell
py report_by_query.py -t "123 Pullbacks(Daily)" -q "(adx_14 > 35) and (pdi_14 > mdi_14) and (daily_strat.str.contains('2d-2d-2u$'))" -o natr_30 -v

# Track - Buy when cross-up week high
py report_by_query.py -t "123 Pullbacks(week_1)" -q "(adx_14 > 35) and (pdi_14 > mdi_14) and (week_1_strat.str.contains('2d-2d-2u$'))" -o natr_30 -v
```

```shell
# Oversold and mean reversion
py report_by_query.py -t "Mean Rev 50 LowerBB" -o natr_30 -v -q "(daily_strat_candle.str.contains('.*-red-green$')) and (last_close < boll_50_3_lb)"
py report_by_query.py -t "Mean Rev LowerBB" -o natr_30 -v -q "(daily_strat_candle.str.contains('.*-green$')) and (last_close < boll_lb)"
# boll_21_3_lb -> bollinger ban 21 day MA, 3 Stdev Lowerband
py report_by_query.py -t "Mean Reversion 21 LowerBB" -o natr_30 -v -q "(last_close < boll_21_3_lb) and (daily_strat_candle.str.contains('.*-green$'))"
```

```shell
py report_by_query.py -t "Squeeze Up" -o natr_30 -v -q "(daily_strat.str.contains('.*-2u$')) and (daily_strat_candle.str.contains('.*-green$')) and (week_1_strat.str.contains('.*-1$')) and (week_1_strat_candle.str.contains('.*-green$'))"
```

```shell
./rbq "(daily_strat.str.contains('.*-2u$')) and (daily_strat_candle.str.contains('.*-green$')) and (week_1_strat.str.contains('.*-1$')) and (week_1_strat_candle.str.contains('.*-green$'))"
```

```shell
py report_by_query.py -t "Momentum Trending" -q "last_close > ema_3 > ema_5 > ema_7 > ema_9 > ema_11 > ema_13 > ema_30 > ema_35 > ema_40 > ema_45 > ema_50 > ema_55 > ema_60" -o week_1_close_change_delta_1 -v
```

```shell
py report_by_query.py -t "Boomer" -q "(daily_strat.str.contains('.*-1-1$')) and (daily_strat_candle.str.contains('.*-green-green$'))" -o natr_30 -v
py report_by_query.py -t "Boomer" -q "(month_1_strat.str.contains('1-1-1$')) and (month_1_strat_candle.str.contains('.*-green-green$'))" -o natr_30 -v
py report_by_query.py -t "Boomer" -q "(last_volume > 100000) and (month_3_strat.str.contains('.*-1-1$')) and (week_1_strat_candle.str.contains('red-green-green$'))" -o monthly_gains_1 -v
```

```shell
py report_by_query.py -t "KC inside BB Channel" -o natr_30 -v -q "(boll_ub < kc_ub) and (boll_lb > kc_lb) and (vol_ema_3 > vol_ema_5 > vol_ema_7) and (daily_strat.str.contains('.*-2u$')) and (daily_strat_candle.str.contains('.*-green$'))"
```

```shell
py report_by_query.py -t "Strat near prev week high" -o natr_30 -v -q "(week_1_strat.str.contains('.*-1$')) and (last_close > ema_50 > ema_200 ) and (((week_2_high - week_1_close)/(week_2_high - week_2_low)) < 0.1)"
```

```shell
# Read symbols from file and generate report
QUERY=$(SYMBOLS=$(cat file.csv | awk -F\, '{print $1}' | grep -v symbol | while read line; do echo "'$line'"; done | tr '\n' ','); echo "(symbol in ($SYMBOLS))"); ./rbq $QUERY
```

```shell
py report_by_query.py -t "BB lb (oversold)" -o natr_30 -v -q "(day_5_before_last_low < boll_4_day_before_last_21_2_lb) and (day_4_before_last_low < boll_3_day_before_last_21_2_lb) and (day_3_before_last_low < boll_2_day_before_last_21_2_lb) and (last_low > boll_lb) and (daily_strat_candle.str.contains('.*-green$'))"
```

```shell
# Few days down in a row
py report_by_query.py -t "9 Days Down in a row" -o natr_30 -v -q "(day_2_before_last_low < day_3_before_last_low < day_4_before_last_low < day_5_before_last_low < day_6_before_last_low < day_7_before_last_low < day_8_before_last_low < day_9_before_last_low < day_10_before_last_low)"
```

```shell
# Parabolic moves
py report_by_query.py -t "Month Change" -o month_1_close_change_delta_1 -v -q "(month_1_close_change_delta_1 > 50)" 
```

```shell
py report_by_query.py -o smooth_30 -t "4RSI" -v -q "(last_close < 100) and (last_close > ma_50) and (monthly_gains_3 > 0) and (rsi_2 < 10)"
```

```shell
py report_by_query.py -o smooth_90 -v -t "Long Key Reversal" -q "((day_2_before_last_low < day_3_before_last_low) and (last_close > day_3_before_last_high) and (last_close > day_2_before_last_high)) and (daily_strat_candle.str.contains('red-red-green$')) and (last_close > ema_8 > ema_21) and (week_1_strat_candle.str.contains('.*-green$'))"
```

```shell
py report_by_query.py -o smooth_90 -v -t "Long base and Breakout" -q "(last_volume < day_2_before_last_volume) and (last_low < day_2_before_last_high) and (last_close > month_1_high) and (last_close > month_2_high) and (last_close > month_3_high) and (day_2_before_last_close < last_close)"
```

```shell
# last_candle is 3x previous candle, last_volume is 3x previous candle volume
./rbq "(abs(last_high - last_close) < 3 * abs(day_2_before_last_high - day_2_before_last_low)) and (last_volume > day_2_before_last_volume * 3) and (daily_strat_candle.str.contains('.*-green-green$')) and (daily_strat.str.contains('.*-2u$'))"
```

```shell
# Volume/Price divergence/convergence
./rbq "(vol_ma_3 > vol_ma_5 > vol_ma_7 > vol_ma_9 > vol_ma_11 > vol_ma_13 > vol_ma_15 > vol_ma_17 > vol_ma_19 > vol_ma_21) and (ma_3 < ma_5 < ma_7 < ma_9 < ma_11 < ma_13 < ma_15)"
./rbq "(day_2_before_last_volume > day_3_before_last_volume > day_4_before_last_volume > day_5_before_last_volume > day_6_before_last_volume) and (day_2_before_last_close < day_3_before_last_close < day_4_before_last_close < day_5_before_last_close < day_6_before_last_close < day_7_before_last_close)"
```