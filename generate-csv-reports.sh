python3 report_by_query.py -t "SP500 Daily Movers" -q "(is_large_cap == True)" -o "daily_close_change_delta_1" -e
python3 report_by_query.py -t "SP500 Weekly Movers" -q "(is_large_cap == True)" -o "week_1_close_change_delta_1" -e
python3 report_by_query.py -t "SP500 Monthly Movers" -q "(is_large_cap == True)" -o "month_1_close_change_delta_1" -e
python3 report_by_query.py -t "EMA Bounce" -q "(day_0_ema_60 < day_0_ema_50 < day_0_ema_45 < day_0_ema_40 < day_0_ema_35 < last_close < day_0_ema_30) and (adx_14 > 35) and (daily_strat.str.contains('.*-2d-2d')) and (daily_strat_candle.str.contains('.*-red-green$'))" -o "natr_30" -e
python3 report_by_query.py -t "EMA 8x21 Pullback" -q "(day_0_ema_60 < day_0_ema_50 < day_0_ema_45 < day_0_ema_40 < day_0_ema_35 < day_0_ema_21 < day_0_ema_8) and (vol_ema_3 > vol_ema_5 > vol_ema_7) and (last_low > day_0_ema_21) and (last_low < day_0_ema_8) and (adx_14 < 30) and (adx_9 > adx_14 > adx_21)" -o "natr_30" -e
python3 report_by_query.py -t "UpTrend" -q "(day_0_ema_3 > day_0_ema_5 > day_0_ema_7 > day_0_ema_9 > day_0_ema_11 > day_0_ema_13 > day_0_ema_15 > day_0_ema_21 > day_0_ema_30 > day_0_ema_35 > day_0_ema_40 > day_0_ema_45 > day_0_ema_50 > day_0_ema_60)" -o "smooth_30" -e
python3 report_by_query.py -t "UpTrend" -q "(day_0_ema_21 > day_0_ema_50) and (last_high > day_0_ema_8) and (last_low < day_0_ema_8)" -o "smooth_30" -e
python3 report_by_query.py -t "8x21" -q "(last_close > 100) and (last_close > day_0_ema_8) and (day_0_ema_8 > day_0_ema_21) and (day_1_ema_8 < day_1_ema_21)" -o "natr_30" -e
python3 report_by_query.py -t "Ema21 Bounce" -q "(day_0_ema_8 > day_0_ema_21) and (day_0_ema_8 > day_0_ema_21) and (last_high < day_0_ema_8) and (last_low > day_0_ema_21) and (daily_strat_candle.str.contains('.*-red-green$'))" -o "smooth_30" -e
python3 report_by_query.py -t "Power of 3 Daily" -q "(power_of_3_daily == True)" -o natr_30 -e
python3 report_by_query.py -t "Power of 3 Weekly" -q "(power_of_3_week_1 == True) and (last_close < day_0_boll_21_2)" -o natr_30 -e
python3 report_by_query.py -t "⬆ 5D Volume" -o natr_30 -e -q "(last_volume > day_2_volume > day_3_volume > day_4_volume > day_5_volume > day_6_volume > day_7_volume > day_8_volume > day_9_volume)" -e
python3 report_by_query.py -t "⬆ 4D Vol/R-G-G Candles" -o natr_30 -e -q "(last_volume > day_2_volume > day_3_volume > day_4_volume) and (daily_strat_candle.str.contains('red-green-green$'))" -e
python3 report_by_query.py -t "⬆ 2W Vol/GG Candles" -o natr_30 -e -q "(week_0_volume > week_1_volume > week_2_volume > week_3_volume and (week_1_strat.str.contains('2d-2d-2u$')) and (week_1_strat_candle.str.contains('.*-green-green$')))" -e
python3 report_by_query.py -t "123 Pullbacks(Daily)" -q "(adx_14 > 35) and (pdi_14 > mdi_14) and (daily_strat.str.contains('2d-2d-2u$'))" -o natr_30 -e
python3 report_by_query.py -t "123 Pullbacks(week_1)" -q "(adx_14 > 35) and (pdi_14 > mdi_14) and (week_1_strat.str.contains('2d-2d-2u$'))" -o natr_30 -e
python3 report_by_query.py -t "Mean Rev 50 LowerBB" -o natr_30 -e -q "(daily_strat_candle.str.contains('.*-red-green$')) and (last_close < day_0_boll_50_3_lb)" -e
python3 report_by_query.py -t "Mean Rev LowerBB" -o natr_30 -e -q "(daily_strat_candle.str.contains('.*-green$')) and (last_close < day_0_boll_21_2_lb)" -e
python3 report_by_query.py -t "Mean Reversion 21 LowerBB" -o natr_30 -e -q "(last_close < day_0_boll_21_3_lb) and (daily_strat_candle.str.contains('.*-green$'))" -e
python3 report_by_query.py -t "Squeeze Up" -o natr_30 -e -q "(daily_strat.str.contains('.*-2u$')) and (daily_strat_candle.str.contains('.*-green$')) and (week_1_strat.str.contains('.*-1$')) and (week_1_strat_candle.str.contains('.*-green$'))" -e
python3 report_by_query.py -t "Momentum Trending" -q "last_close > day_0_ema_3 > day_0_ema_5 > day_0_ema_7 > day_0_ema_9 > day_0_ema_11 > day_0_ema_13 > day_0_ema_30 > day_0_ema_35 > day_0_ema_40 > day_0_ema_45 > day_0_ema_50 > day_0_ema_55 > day_0_ema_60" -o week_1_close_change_delta_1 -e
python3 report_by_query.py -t "Boomer" -q "(daily_strat.str.contains('.*-1-1$')) and (daily_strat_candle.str.contains('.*-green-green$'))" -o natr_30 -e
