#!/bin/bash

# Find all CSV files recursively and process each one
find $HOME/workspace/market-data/gamma-calculations -type f -name "*_quotedata.csv" | while read -r file; do
    echo "Processing $file"
    ./gamma-calculations.py --file $file --database data/gamma_calculations.db
done
