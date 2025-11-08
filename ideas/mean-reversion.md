Most traders blow up their mean reversion systems not because of bad entries — but because of clustered risk. Here’s how to fix it 👇

Long mean reversion on stocks is one of the few clean edges a retail trader can still harvest.
The best versions wait for rare oversold setups — fewer trades, higher expectancy.

The hidden danger: risk clusters.
In calm markets, you get a few fills per day.
When markets drop hard, signals fire everywhere — you end up fully loaded just as correlations and gap risk explode.
That’s how big mean reversion drawdowns are born.

My fix: portfolio first, strategies second.

Core idea:
- Treat your long mean reversion as a sleeve inside your overall portfolio.
- Each day cap this sleeve so total exposure never exceeds X% of equity.
- X is dynamic — the higher the VIX (or stress), the smaller the cap.
- Within that cap, allocate only to your best signals.

A simple SPY implementation
(using one instrument to illustrate the framework):

1) Data you need
- SPY daily OHLCV (or at minimum: close, adjusted close, volume).
- VIX daily close.
- Optional but useful: risk-free rate (for Sharpe), SPY dividends (via adjusted close).

2) Signal logic (mean reversion on SPY)
- Use adjusted close.
- Compute a short-term rolling mean and std (e.g. 5-day).
- Define:
  - z-score = (price - rolling_mean) / rolling_std.
  - Mean reversion score = -z-score (higher when SPY is more oversold).
- This is model-agnostic: you can swap in RSI, % drop, etc. The portfolio cap logic stays the same.

3) Dynamic exposure cap via VIX
Map VIX to a maximum notional exposure in the SPY sleeve as a fraction of equity, for example:
- VIX < 15        → cap X = 50% of equity
- 15 ≤ VIX < 25   → cap X = 30% of equity
- VIX ≥ 25        → cap X = 20% of equity

Interpretation:
- As vol and correlation risk rise, your allowed exposure shrinks.
- You are pre-limiting the worst days instead of reacting after a drawdown.

4) From signal to target position
For a single-instrument SPY sleeve:
- Convert the mean reversion score into a scaled signal in [0, 1].
  - Example: scale by rolling percentile of the score (e.g. last 60 days).
- Compute:
  - target_weight = min( X(VIX_today) * scaled_signal, max_leverage, hard_position_cap )
- target_notional = target_weight * account_equity

Execution:
- At each market close:
  - Update SPY and VIX.
  - Compute today’s target_weight.
  - Compare with current SPY exposure.
  - Trade the difference (subject to min size / slippage).
- Long-only, SPY-only, always respecting the portfolio cap.

5) How to run it daily (practical checklist)
To operate this as a daily, rules-based process:

- Data:
  - Automatically fetch latest SPY and VIX after US market close.
- Signal engine:
  - Recompute:
    - Mean reversion signal.
    - VIX-based cap X.
    - target_weight and target_notional.
- Broker wiring:
  - Read:
    - Current account equity.
    - Current SPY position.
  - Send:
    - Order = (target_notional - current_notional) / latest_price.
- Risk safeguards:
  - Enforce:
    - |SPY_position| ≤ X% * equity from the VIX rule.
    - Global max leverage.
    - Min trade size to avoid noise.
    - Sanity checks on data freshness and extreme prices.
- Scheduling:
  - Run once per trading day after the close via cron / task scheduler / simple job runner.
- Monitoring:
  - Log:
    - Date, SPY close, VIX, equity.
    - vix_cap, target_weight, target_notional.
    - Orders sent and any rejects.

6) Why this works
- You are no longer hostage to clustered fills in selloffs.
- The cap is regime-aware (via VIX) and enforced at the portfolio level.
- The entry model can evolve without changing the risk framework.
- Simple enough to implement, audit, and trust.

Key takeaway:
Don’t think in strategies — think in portfolio risk budgets that adapt to market regimes, then let your mean reversion signals compete for that budget.

Do you cap risk for your mean reversion sleeve at the portfolio level — or are you still letting the market decide your worst day?
