#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "scipy",
#   "yfinance",
#   "numpy",
#   "dotmap",
#   "flatten-dict",
#   "python-dotenv",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
# Credit: https://www.youtube.com/watch?v=oW6MHjzxHpU
import argparse
import logging

from earnings_vol_algo import compute_recommendation


def main():
    parser = argparse.ArgumentParser(
        description="Check earnings position for a stock symbol"
    )
    parser.add_argument(
        "-s", "--symbol", type=str, help="Stock symbol to analyze", required=True
    )
    args = parser.parse_args()

    try:
        result = compute_recommendation(args.symbol)
        avg_volume_threshold_passed = result["avg_volume"]
        iv30_rv30_threshold_passed = result["iv30_rv30"]
        ts_slope_threshold_passed = result["ts_slope_0_45"]
        expected_move = result["expected_move"]
        recommendation = result["recommendation"]

        print(f"\nRecommendation: {recommendation}")
        print(f"avg_volume: {'PASS' if avg_volume_threshold_passed else 'FAIL'}")
        print(f"iv30_rv30: {'PASS' if iv30_rv30_threshold_passed else 'FAIL'}")
        print(f"ts_slope_0_45: {'PASS' if ts_slope_threshold_passed else 'FAIL'}")
        print(f"Expected Move: {expected_move}")

    except Exception as e:
        logging.exception(e)
        raise


if __name__ == "__main__":
    main()
