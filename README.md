# Market Trading Analysis Utilities/Scripts

Collection of scripts and utilities for stock market analysis, strategies etc

## Setup virtual environment

```shell
make setup
```

## Update dependencies

```shell
make deps
```

## Running scripts

All available scripts should provide a basic description and options to run appropriately

For eg.

```shell
./venv/bin/python3 download_stocklist.py --help
```

I suggest setting up a quick alias to run the python version in the virtual environment. 
This will save you remembering to activate the virtual environment. 
There are other options where you can override the `cd` command, but I find this simple and transparent.

```
alias py=./venv/bin/python3
```

Now you can run the same script as 

```shell
py download_stocklist.py --help
```
