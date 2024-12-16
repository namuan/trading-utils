import backtrader as bt


def pretty_print(format, *args):
    print(format.format(*args))


def exists(object, *properties):
    for property in properties:
        if property not in object:
            return False
        object = object.get(property)
    return True


def print_trade_analysis(cerebro, initial_investment, analyzers):
    format = "  {:<24} : {:<24}"
    NA = "-"

    print("Backtesting Results")
    if hasattr(analyzers, "ta"):
        ta = analyzers.ta.get_analysis()

        openTotal = ta.total.open if exists(ta, "total", "open") else None
        closedTotal = ta.total.closed if exists(ta, "total", "closed") else None
        wonTotal = ta.won.total if exists(ta, "won", "total") else None
        lostTotal = ta.lost.total if exists(ta, "lost", "total") else None

        streakWonLongest = (
            ta.streak.won.longest if exists(ta, "streak", "won", "longest") else None
        )
        streakLostLongest = (
            ta.streak.lost.longest if exists(ta, "streak", "lost", "longest") else None
        )

        pnlNetTotal = ta.pnl.net.total if exists(ta, "pnl", "net", "total") else None
        pnlNetAverage = (
            ta.pnl.net.average if exists(ta, "pnl", "net", "average") else None
        )

        pretty_print(format, "Open Positions", openTotal or NA)
        pretty_print(format, "Closed Trades", closedTotal or NA)
        pretty_print(format, "Winning Trades", wonTotal or NA)
        pretty_print(format, "Loosing Trades", lostTotal or NA)
        print("\n")

        pretty_print(format, "Longest Winning Streak", streakWonLongest or NA)
        pretty_print(format, "Longest Loosing Streak", streakLostLongest or NA)
        pretty_print(
            format,
            "Strike Rate (Win/closed)",
            (wonTotal / closedTotal) * 100 if wonTotal and closedTotal else NA,
        )
        print("\n")

        pretty_print(
            format, "Initial Portfolio Value", "${}".format(initial_investment)
        )
        pretty_print(
            format, "Final Portfolio Value", "${}".format(cerebro.broker.getvalue())
        )
        pretty_print(
            format,
            "Net P/L",
            "${}".format(round(pnlNetTotal, 2)) if pnlNetTotal else NA,
        )
        pretty_print(
            format,
            "P/L Average per trade",
            "${}".format(round(pnlNetAverage, 2)) if pnlNetAverage else NA,
        )
        print("\n")

    if hasattr(analyzers, "drawdown"):
        pretty_print(
            format,
            "Drawdown",
            "${}".format(analyzers.drawdown.get_analysis()["drawdown"]),
        )
    if hasattr(analyzers, "sharpe"):
        pretty_print(
            format, "Sharpe Ratio:", analyzers.sharpe.get_analysis()["sharperatio"]
        )
    if hasattr(analyzers, "vwr"):
        pretty_print(format, "VRW", analyzers.vwr.get_analysis()["vwr"])
    if hasattr(analyzers, "sqn"):
        pretty_print(format, "SQN", analyzers.sqn.get_analysis()["sqn"])
    print("\n")

    print("Transactions")
    format = "  {:<24} {:<24} {:<16} {:<8} {:<8} {:<16}"
    pretty_print(format, "Date", "Amount", "Price", "SID", "Symbol", "Value")
    for key, value in analyzers.txn.get_analysis().items():
        pretty_print(
            format,
            key.strftime("%Y/%m/%d %H:%M:%S"),
            value[0][0],
            value[0][1],
            value[0][2],
            value[0][3],
            value[0][4],
        )


def add_trade_analyzers(cerebro):
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="ta")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(
        bt.analyzers.SharpeRatio,
        _name="sharpe",
        riskfreerate=0.0,
        annualize=True,
        timeframe=bt.TimeFrame.Minutes,
    )
    cerebro.addanalyzer(bt.analyzers.VWR, _name="vwr")
    cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")
    cerebro.addanalyzer(bt.analyzers.Transactions, _name="txn")
