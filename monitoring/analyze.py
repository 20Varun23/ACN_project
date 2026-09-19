"""Stream C: offline analysis of one run directory.

Parses iperf3 JSON (per-second throughput / jitter / loss per class) and
samples.csv (RTT + queue counters), writes summary.csv and plots.

    python3 monitoring/analyze.py results/<run>
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

CLASSES = ["voip", "video", "bulk"]


def iperf_intervals(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    with open(path) as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return pd.DataFrame()
    rows = []
    for iv in data.get("intervals", []):
        s = iv["sum"]
        rows.append({
            "t": round(s["end"]),
            "mbps": s["bits_per_second"] / 1e6,
            "jitter_ms": s.get("jitter_ms"),
            "loss_pct": (s.get("lost_percent")
                         if "lost_percent" in s
                         else 100.0 * s.get("lost_packets", 0) / max(s.get("packets", 1), 1)),
        })
    return pd.DataFrame(rows)


def analyze(run_dir):
    per_class = {c: iperf_intervals(os.path.join(run_dir, f"{c}.json")) for c in CLASSES}
    samples = pd.read_csv(os.path.join(run_dir, "samples.csv"))

    for qid in (0, 1, 2):
        col = f"q{qid}_tx_bytes"
        samples[f"q{qid}_mbps"] = samples[col].diff().fillna(0) * 8 / samples["t"].diff().fillna(1) / 1e6

    summary = []
    for c, df in per_class.items():
        if df.empty:
            continue
        summary.append({
            "class": c,
            "avg_mbps": df["mbps"].mean(),
            "min_mbps": df["mbps"].min(),
            "avg_jitter_ms": df["jitter_ms"].mean() if df["jitter_ms"].notna().any() else None,
            "avg_loss_pct": df["loss_pct"].mean() if df["loss_pct"].notna().any() else None,
            "avg_rtt_ms": samples[f"{c}_rtt_ms"].mean(),
            "max_rtt_ms": samples[f"{c}_rtt_ms"].max(),
        })
    pd.DataFrame(summary).to_csv(os.path.join(run_dir, "summary.csv"), index=False)

    fig, axes = plt.subplots(3, 1, figsize=(9, 10), sharex=True)
    for c, df in per_class.items():
        if not df.empty:
            axes[0].plot(df["t"], df["mbps"], label=c)
    axes[0].set_ylabel("Throughput (Mbit/s)")
    axes[0].legend()

    for c in CLASSES:
        axes[1].plot(samples["t"], samples[f"{c}_rtt_ms"], label=c)
    axes[1].set_ylabel("RTT (ms)")
    axes[1].legend()

    for c, df in per_class.items():
        if not df.empty and df["loss_pct"].notna().any():
            axes[2].plot(df["t"], df["loss_pct"], label=c)
    axes[2].set_ylabel("Loss (%)")
    axes[2].set_xlabel("Time (s)")
    axes[2].legend()

    fig.suptitle(os.path.basename(run_dir.rstrip("/")))
    fig.tight_layout()
    fig.savefig(os.path.join(run_dir, "metrics.png"), dpi=120)
    print(pd.DataFrame(summary).to_string(index=False))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: analyze.py results/<run>")
        sys.exit(1)
    analyze(sys.argv[1])
