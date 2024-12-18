# Options Analysis Toolkit

## Import Data

Extract all contents from compressed files into a designated folder.
The following script can read nested folders, allowing them to be accessed without being placed at the root level.

```shell
uvr optionsdx-data-importer.py --input $(pwd)/data/spy_eod --output data/spy_eod.db -v
```

## Strategies

### Vol check, Profit Take 15%, Stop Loss 100% of Credit

```shell
for dte in {7..60}; do
    echo "Running for DTE: $dte"
    uvr --no-progress options-straddle-low-vol-trades.py --db-path data/spx_eod.db --dte $dte --profit-take 15 --stop-loss 100
done
```

```shell
cp data/spx_eod.db data/spx_eod_vol_filter.db
```

```shell
uvr options-straddle-simple-report.py --database data/spx_eod_vol_filter.db --weeks 4 --dte 45
```

```shell
uvr options-straddle-simple-equity-graph.py --db-path data/spx_eod_vol_filter.db
```

### What if we keep all trades with given profit take and stop loss

```shell
for dte in {7..60}; do
    echo "Running for DTE: $dte"
    uvr --no-progress options-straddle-profit-take-stop-loss-adjustment.py --db-path data/spx_eod.db --dte $dte --profit-take 15 --stop-loss 50
done
```

```shell
cp data/spx_eod.db data/spx_eod_profit_loss_adjustment.db
```

```shell
uvr options-straddle-simple-report.py --database data/spx_eod_profit_loss_adjustment.db --weeks 4 --dte 45
```

```shell
uvr options-straddle-simple-equity-graph.py --db-path data/spx_eod_profit_loss_adjustment.db
```

### What if we keep all trades all the time

```shell
for dte in {7..60}; do
    echo "Running for DTE: $dte"
    uvr --no-progress options-straddle-simple.py --db-path data/spx_eod.db --dte $dte
done
```

```shell
cp data/spx_eod.db data/spx_eod_simple.db
```

```shell
uvr options-straddle-simple-report.py --database data/spx_eod_simple.db --weeks 4 --dte 45
```

```shell
uvr options-straddle-simple-equity-graph.py --db-path data/spx_eod_simple.db
```
