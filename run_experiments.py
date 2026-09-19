"""Run the full none / static / adaptive comparison in one go.

    sudo python3 run_experiments.py --repeats 3

Each mode is run --repeats times under the identical congestion timeline,
then monitoring/compare.py aggregates them into results/comparison/.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mininet.log import setLogLevel

from common import config as cfg
from monitoring.compare import compare
from scenario import MODES, run

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--t-cong", type=int, default=15)
    p.add_argument("--t-end", type=int, default=45)
    p.add_argument("--modes", nargs="+", choices=MODES, default=MODES)
    args = p.parse_args()
    setLogLevel("warning")

    run_dirs = []
    for i in range(args.repeats):
        for mode in args.modes:
            print(f"\n=== repeat {i + 1}/{args.repeats} mode={mode} ===")
            run_dirs.append(run(mode, args.t_cong, args.t_end, tag=f"r{i + 1}"))
            time.sleep(2)  # let OVS/tc settle between runs

    compare(run_dirs, os.path.join(cfg.RESULTS_DIR, "comparison"))
