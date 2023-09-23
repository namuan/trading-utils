## {{ now().strftime('%d %B %Y') }} - {{title}}

Query: {{ stocks["query"] }}

Sort By: {{ stocks["sort_by"] }}

{% for stock in stocks["report_data"] %}

### {{ stock['symbol'] }}

![]({{ stock['chart_link'] }})

|         |                                            |
| ------------- | ----------------------------------------------- |
| **Current Price** | {{ '%0.2f' % stock['last_close'] }} on {{ stock['last_close_date'] }}|
| ATR(20) | {{ '%0.2f' % stock['atr_20'] }} |
| 💹 1 Month Gain | {{ '%0.2f' % stock['monthly_gains_1'] }}% |
| 💹 💹 3 Months Gain | {{ '%0.2f' % stock['monthly_gains_3'] }}% |
| 🔢 Position Size (based on ~1% risk along with SL below) | {{ '%0.2f' % stock['position_size'] }} |
| 💸 Purchase Price | {{ '%0.2f' % (stock['position_size']|float * stock['last_close']|float) }} |
| **1 ATR(20)** | |
| ▶️ Trailing Stop Loss | {{ '%0.2f' % stock['atr_20'] }} | 
| ▶️ Fixed Stop Loss | {{ '%0.2f' % (stock['last_close']|float - stock['atr_20']|float) }} |
| ▶️ Max Loss (Based on buy at last close) | {{ '%0.2f' % ((stock['last_close']|float - stock['atr_20']|float) * stock['position_size']|float - (stock['position_size']|float * stock['last_close']|float)) }} |
| **2 ATR(20)** | |
| ▶️ Trailing Stop Loss | {{ '%0.2f' % (2 * stock['atr_20']|float) }} | 
| ▶️ Fixed Stop Loss | {{ '%0.2f' % (stock['last_close']|float - (2 * stock['atr_20']|float)) }} |
| ▶️ Max Loss (Based on buy at last close) | {{ '%0.2f' % ((stock['last_close']|float - (2 * stock['atr_20']|float)) * stock['position_size']|float - (stock['position_size']|float * stock['last_close']|float)) }} |


[LazyTrader](https://namuan.github.io/lazy-trader/?symbol={{ stock['symbol'] }})

___


{% endfor %}

> Risk Warning: We do not guarantee accuracy and will not accept liability for any loss or damage which arise directly or indirectly from use of or reliance on information contained within these reports. We may provide general commentary which is not intended as investment advice and must not be construed as such. Trading/Investments carries a risk of losses in excess of your deposited funds and may not be suitable for all investors. Please ensure that you fully understand the risks involved.