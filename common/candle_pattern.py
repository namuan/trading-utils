def identify_candle_pattern(ticker_df):
    last_candle = ticker_df.iloc[-1]
    c = last_candle.close
    h = last_candle.high
    l = last_candle.low
    o = last_candle.open

    patterns = []
    is_doji = (
        abs(c - o) / (h - l) < 0.1
        and (h - max(c, o)) > (3 * abs(c - o))
        and (min(c, o) - l) > (3 * abs(c - o))
    )

    is_hanging_man = (
        0.3 > abs(c - o) / (h - l) >= 0.1
        and (min(c, o) - l) >= (2 * abs(c - o))
        and (h - max(c, o)) > (0.25 * abs(c - o))
    )

    if is_doji:
        patterns.append("doji")

    if is_hanging_man:
        patterns.append("hanging_man")

    return ",".join(patterns) if patterns else "na"

# For Reference
# // Created by Robert N. 030715
# // Updated 031115
# // Candle labels
# study(title = "Mamona Candles", overlay = true)
#
# data1=(close[1]>open[1] and abs(close[1]-open[1])/(high[1]-low[1])>=0.7 and close<open and abs(close-open)/(high-low)>=0.7 and open>=close[1] and close>open[1] and close<((open[1]+close[1])/2))
# plotshape(data1,title="Dark Cloud Cover",text='DarkCloudCover',color=red, style=shape.arrowdown,location=location.abovebar)
#
# data2=(abs(close-open)/(high-low)<0.1 and (high-max(close,open))>(3*abs(close-open)) and (min(close,open)-low)>(3*abs(close-open)))
# plotshape(data2,title="Doji",text='Doji',color=white, style=shape.circle,location=location.belowbar)
#
# data3=(close[1]>open[1] and abs(close[1]-open[1])/(high[1]-low[1])>=0.7 and abs(close-open)/(high-low)<0.1 and close[1]<close and close[1]<open and (high-max(close,open))>(3*abs(close-open)) and (min(close,open)-low)>(3*abs(close-open)))
# plotshape(data3,title="Doji Star",text='DojiStar',color=red, style=shape.arrowdown,location=location.abovebar)
#
# data4=(abs(close-open)/(high-low)<0.1 and (min(close,open)-low)>(3*abs(close-open)) and (high-max(close,open))<abs(close-open))
# plotshape(data4,title="Dragonfly Doji",text='DragonflyDoji',color=green, style=shape.arrowup,location=location.belowbar)
#
# data5=(close[2]>open[2] and abs(close[2]-open[2])/(high[2]-low[2])>=0.7 and 0.3>abs(close[1]-open[1])/(high[1]-low[1])>=0.1 and close<open and abs(close-open)/(high-low)>=0.7 and close[2]<close[1] and close[2]<open[1] and close[1]>open and open[1]>open and close<close[2])
# plotshape(data5,title="Evening Star",text='EveningStar',color=red, style=shape.arrowdown,location=location.abovebar)
#
# data6=(close[2]>open[2] and abs(close[2]-open[2])/(high[2]-low[2])>=0.7 and abs(close[1]-open[1])/(high[1]-low[1])<0.1 and close<open and abs(close-open)/(high-low)>=0.7 and close[2]<close[1] and close[2]<open[1] and close[1]>open and open[1]>open and close<close[2] and (high[1]-max(close[1],open[1]))>(3*abs(close[1]-open[1])) and (min(close[1],open[1])-low[1])>(3*abs(close[1]-open[1])))
# plotshape(data6,title="Evening Star Doji",text='EveningStarDoji',color=red, style=shape.arrowdown,location=location.abovebar)
#
# data7=(abs(close-open)/(high-low)<0.1 and (high-max(close,open))>(3*abs(close-open)) and (min(close,open)-low)<=abs(close-open))
# plotshape(data7,title="Gravestone Doji",text='GravestoneDoji',color=red, style=shape.arrowdown,location=location.abovebar)
#
# data8=(close<open and 0.3>abs(close-open)/(high-low)>=0.1 and (min(close,open)-low)>=(2*abs(close-open)) and (high-max(close,open))>(0.25*abs(close-open)))
# plotshape(data8,title="Hanging Man Red",text='HangingMan',color=red, style=shape.arrowdown,location=location.abovebar)
#
# data9=(close>open and 0.3>abs(close-open)/(high-low)>=0.1 and (min(close,open)-low)>=(2*abs(close-open)) and (high-max(close,open))>(0.25*abs(close-open)))
# plotshape(data9,title="Hanging Man Green",text='HangingMan',color=red, style=shape.arrowdown,location=location.abovebar)
#
# data10=(close[2]<open[2] and abs(close[2]-open[2])/(high[2]-low[2])>=0.7 and 0.3>abs(close[1]-open[1])/(high[1]-low[1])>=0.1 and close>open and abs(close-open)/(high-low)>=0.7 and close[2]>close[1] and close[2]>open[1] and close[1]<open and open[1]<open and close>close[2])
# plotshape(data10,title="Morning Star",text='MorningStar',color=green, style=shape.arrowup,location=location.belowbar)
#
# data11=(close[2]<open[2] and abs(close[2]-open[2])/(high[2]-low[2])>=0.7 and abs(close[1]-open[1])/(high[1]-low[1])<0.1 and close>open and abs(close-open)/(high-low)>=0.7 and close[2]>close[1] and close[2]>open[1] and close[1]<open and open[1]<open and close>close[2] and (high[1]-max(close[1],open[1]))>(3*abs(close[1]-open[1])) and (min(close[1],open[1])-low[1])>(3*abs(close[1]-open[1])))
# plotshape(data11,title="Morning Star Doji",text='MorningStarDoji',color=green, style=shape.arrowup,location=location.belowbar)
#
# data12=(close[1]<open[1] and abs(close[1]-open[1])/(high[1]-low[1])>=0.7 and close>open and abs(close-open)/(high-low)>=0.7 and open<=close[1] and close<open[1] and close<((open[1]+close[1])/2))
# plotshape(data12,title="Piercieng Pattern",text='PiercingPattern',color=green, style=shape.arrowup,location=location.belowbar)
#
# data13=(close[1]<open[1] and abs(close[1]-open[1])/(high[1]-low[1])>=0.7 and 0.3>abs(close-open)/(high-low)>=0.1 and close[1]>close and close[1]>open)
# plotshape(data13,title="Raindrop",text='Raindrop',color=green, style=shape.arrowup,location=location.belowbar)
#
# data14=(close[1]<open[1] and abs(close[1]-open[1])/(high[1]-low[1])>=0.7 and abs(close-open)/(high-low)<0.1 and close[1]>close and close[1]>open and (high-max(close,open))>(3*abs(close-open)) and (min(close,open)-low)>(3*abs(close-open)))
# plotshape(data14,title="Raindrop Doji",text='RaindropDoji',color=green, style=shape.arrowup,location=location.belowbar)
#
# data15=(close<open and 0.3>abs(close-open)/(high-low)>=0.1 and (high-max(close,open))>=(2*abs(close-open)) and (min(close,open)-low)<=(0.25*abs(close-open)))
# plotshape(data15,title="Inverted Hammer Red",text='InvertedHammer',color=green, style=shape.arrowup,location=location.belowbar)
#
# data16=(close>open and 0.3>abs(close-open)/(high-low)>=0.1 and (high-max(close,open))>=(2*abs(close-open)) and (min(close,open)-low)<=(0.25*abs(close-open)))
# plotshape(data16,title="Inverted Hammer Green",text='InvertedHammer',color=green, style=shape.arrowup,location=location.belowbar)
#
# data17=(close[1]>open[1] and abs(close[1]-open[1])/(high[1]-low[1])>=0.7 and 0.3>abs(close-open)/(high-low)>=0.1 and close[1]<close and close[1]<open)
# plotshape(data17,title="Star",text='Star',color=red, style=shape.arrowdown,location=location.abovebar)
#
# data18=(close[1]>open[1] and abs(close[1]-open[1])/(high[1]-low[1])>=0.7 and close<open and abs(close-open)/(high-low)>=0.7 and open>=close[1] and close<close[1] and close>=((open[1]+close[1])/2))
# plotshape(data18,title="Bearish Thrusting",text='BearishThrusting',color=red, style=shape.arrowdown,location=location.abovebar)
#
# data19=(close[1]<open[1] and abs(close[1]-open[1])/(high[1]-low[1])>=0.7 and close>open and abs(close-open)/(high-low)>=0.7 and open<=close[1] and close>close[1] and close<=((open[1]+close[1])/2))
# plotshape(data19,title="Bullish Thrusting Pattern",text='BullishThrusting',color=green, style=shape.arrowup,location=location.belowbar)
#
# data20=(close[1]<open[1] and abs(close[1]-open[1])/(high[1]-low[1])>=0.7 and close<open and 0.3>abs(close-open)/(high-low)>=0.1 and abs(low/low[1]-1)<0.05 and abs(close-open)<2*(min(close,open)-low))
# plotshape(data20,title="Tweezers Bottom",text='TweezersBottom',color=green, style=shape.arrowup,location=location.belowbar)
#
# data21=(close[1]>open[1] and abs(close[1]-open[1])/(high[1]-low[1])>=0.7 and close>open and 0.3>abs(close-open)/(high-low)>=0.1 and abs(high/high[1]-1)<0.05 and abs(close[1]-open[1])<2*(high[1]-max(close[1],open[1])))
# plotshape(data21,title="Tweezers Top",text='TweezersTop',color=red, style=shape.arrowdown,location=location.abovebar)
#
# data22=(close[3]<open[3] and abs(close[3]-open[3])/(high[3]-low[3])>=0.7 and close[2]>open[2] and 0.3>abs(close[2]-open[2])/(high[2]-low[2])>=0.1 and close[1]>open[1] and 0.3>abs(close[1]-open[1])/(high[1]-low[1])>=0.1 and close>open and abs(close-open)/(high-low)>=0.7 and close[2]>close[1] and close[1]>close[3] and open[2]<close[3] and open[1]<close[3] and close>((open[3]+close[3])/2))
# plotshape(data22,title="Tower Bottom",text='TowerBottom',color=green, style=shape.arrowup,location=location.belowbar)
#
# data23=(close[3]>open[3] and abs(close[3]-open[3])/(high[3]-low[3])>=0.7 and close[2]<open[2] and 0.3>abs(close[2]-open[2])/(high[2]-low[2])>=0.1 and close[1]<open[1] and 0.3>abs(close[1]-open[1])/(high[1]-low[1])>=0.1 and close<open and abs(close-open)/(high-low)>=0.7 and close[2]<close[1] and close[1]<close[3] and open[2]>close[3] and open[1]>close[3] and close<((open[3]+close[3])/2))
# plotshape(data23,title="Tower Top",text='TowerTop',color=red, style=shape.arrowdown,location=location.abovebar)
#
# data24=(close[1]<open[1] and 0.7>abs(close[1]-open[1])/(high[1]-low[1])>=0.3 and close>open and 0.7>abs(close-open)/(high-low)>=0.3 and close<=close[1] and close>low[1])
# plotshape(data24,title="Bullish In Neck",text='BullishInNeck',color=green, style=shape.arrowup,location=location.belowbar)
#
# data25=(close[1]>open[1] and 0.7>abs(close[1]-open[1])/(high[1]-low[1])>=0.3 and close<open and 0.7>abs(close-open)/(high-low)>=0.3 and close>=close[1] and close<high[1])
# plotshape(data25,title="Bearish In Neck",text='BearishInNeck',color=red, style=shape.arrowdown,location=location.abovebar)
#
# data26=(close[1]>open[1] and 0.7>abs(close[1]-open[1])/(high[1]-low[1])>=0.3 and close<open and 0.7>abs(close-open)/(high-low)>=0.3 and open<=open[1] and open>low[1])
# plotshape(data26,title="Bullish Separating Lines",text='BullishSeparatingLines',color=green, style=shape.arrowup,location=location.belowbar)
#
# data27=(close[1]<open[1] and 0.7>abs(close[1]-open[1])/(high[1]-low[1])>=0.3 and close>open and 0.7>abs(close-open)/(high-low)>=0.3 and open>=open[1] and open<high[1])
# plotshape(data27,title="Bearish Separating Lines",text='BearishSeparatingLines',color=red, style=shape.arrowdown,location=location.abovebar)
#
# data28=(close[1]<open[1] and abs(close[1]-open[1])/(high[1]-low[1])>=0.7 and 0.3>abs(close-open)/(high-low)>=0.1 and high<open[1] and low>close[1])
# plotshape(data28,title="Bullish Harami",text='BullishHarami',color=green, style=shape.arrowup,location=location.belowbar)
#
# data29=(close[1]>open[1] and abs(close[1]-open[1])/(high[1]-low[1])>=0.7 and 0.3>abs(close-open)/(high-low)>=0.1 and high<close[1] and low>open[1])
# plotshape(data29,title="Bearish Harami",text='BearishHarami',color=red, style=shape.arrowdown,location=location.abovebar)
#
# data30=(close[1]<open[1] and 0.3>abs(close[1]-open[1])/(high[1]-low[1])>=0.1 and close>open and abs(close-open)/(high-low)>=0.7 and high[1]<close and low[1]>open)
# plotshape(data30,title="Bullish Engulfing",text='BullishEngulfing',color=green, style=shape.arrowup,location=location.belowbar)
#
# data31=(close[1]>open[1] and 0.3>abs(close[1]-open[1])/(high[1]-low[1])>=0.1 and close<open and abs(close-open)/(high-low)>=0.7 and high[1]<open and low[1]>close)
# plotshape(data31,title="Bearish Engulfing",text='BearishEngulfing',color=red, style=shape.arrowdown,location=location.abovebar)
#
# data32=(abs(close[1]-open[1])/(high[1]-low[1])<0.1 and close>open and abs(close-open)/(high-low)>=0.7 and high[1]<close and low[1]>open and (high[1]-max(close[1],open[1]))>(3*abs(close[1]-open[1])) and (min(close[1],open[1])-low[1])<=abs(close[1]-open[1]))
# plotshape(data32,title="Doji Bullish Engulfing",text='DojiBullishEngulfing',color=green, style=shape.arrowup,location=location.belowbar)
#
# data33=(abs(close[1]-open[1])/(high[1]-low[1])<0.1 and close<open and abs(close-open)/(high-low)>=0.7 and high[1]<open and low[1]>close and (high[1]-max(close[1],open[1]))>(3*abs(close[1]-open[1])) and (min(close[1],open[1])-low[1])<=abs(close[1]-open[1]))
# plotshape(data31,title="Doji Bearish Engulfing",text='DojiBearishEngulfing',color=red, style=shape.arrowdown,location=location.abovebar)
