## {{ now().strftime('%d %B %Y') }} - {{title}}

Query: {{ stocks["query"] }}

Sort By: {{ stocks["sort_by"] }}

{% for stock in stocks["report_data"] %}

### {{ stock['symbol'] }}

<img src="{{ stock['chart_link'] }}" />

[comment]: <> (data_row["fixed_stop_loss_1_atr_20"] * data_row["position_size"] - total_purchase_price)

|         |                                            |
| ------------- | ----------------------------------------------- |
| **Current Price** | {{ '%0.2f' % stock['last_close'] }} on {{ stock['last_close_date'] }}|
| ATR(20) | {{ '%0.2f' % stock['atr_20'] }} |
| 💹 1 Month Gain | {{ '%0.2f' % stock['monthly_gains_1'] }}% |
| 💹 💹 3 Months Gain | {{ '%0.2f' % stock['monthly_gains_3'] }}% |
| 🔢 Position Size (based on 10K/~1% risk) | {{ '%0.2f' % stock['position_size'] }} |
| 💸 Purchase Price | {{ '%0.2f' % (stock['position_size']|float * stock['last_close']|float) }} |
| **1 ATR(20)** | |
| ▶️ Trailing Stop Loss | {{ '%0.2f' % stock['atr_20'] }} | 
| ▶️ Fixed Stop Loss | {{ '%0.2f' % (stock['last_close']|float - stock['atr_20']|float) }} |
| ▶️ Max Loss (Based on buy at last close) | {{ '%0.2f' % ((stock['last_close']|float - stock['atr_20']|float) * stock['position_size']|float - (stock['position_size']|float * stock['last_close']|float)) }} |
| **2 ATR(20)** | |
| ▶️ Trailing Stop Loss | {{ '%0.2f' % (2 * stock['atr_20']|float) }} | 
| ▶️ Fixed Stop Loss | {{ '%0.2f' % (stock['last_close']|float - (2 * stock['atr_20']|float)) }} |
| ▶️ Max Loss (Based on buy at last close) | {{ '%0.2f' % ((stock['last_close']|float - (2 * stock['atr_20']|float)) * stock['position_size']|float - (stock['position_size']|float * stock['last_close']|float)) }} |

[BarChart](https://www.barchart.com/stocks/quotes/{{ stock['symbol'] }}/options)
| [StockInvest](https://stockinvest.us/technical-analysis/{{ stock['symbol'] }})
| [TradingView](https://www.tradingview.com/chart/?symbol={{ stock['symbol'] }})
| [FinViz](https://www.finviz.com/quote.ashx?t={{ stock['symbol'] }})
| [StockTwits](https://stocktwits.com/symbol/{{ stock['symbol'] }})
| [SwingTradeBot](https://swingtradebot.com/equities/{{ stock['symbol'] }})
| [MacroAxis](https://www.macroaxis.com/forecast/{{ stock['symbol'] }})
| [Y Options](https://finance.yahoo.com/quote/{{ stock['symbol'] }}/options?straddle=true)
| [Straddle](https://optionstrat.com/build/straddle/{{ stock['symbol'] }})
| [Short Put](https://optionstrat.com/build/short-put/{{ stock['symbol'] }})
| [Credit Spread](https://optionstrat.com/build/bull-put-spread/{{ stock['symbol'] }})
| [OAI Earnings](https://tools.optionsai.com/earnings/{{ stock['symbol'] }})


___


{% endfor %}

> Risk Warning: We do not guarantee accuracy and will not accept liability for any loss or damage which arise directly or indirectly from use of or reliance on information contained within these reports. We may provide general commentary which is not intended as investment advice and must not be construed as such. Trading/Investments carries a risk of losses in excess of your deposited funds and may not be suitable for all investors. Please ensure that you fully understand the risks involved.