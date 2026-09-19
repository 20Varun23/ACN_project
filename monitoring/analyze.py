"""Stream C: offline analysis of one run directory.

Parses iperf3 JSON (per-second throughput / jitter / loss per class),
samples.csv (RTT + per-queue bandwidth) and, for adaptive runs,
decisions.csv (policy changes). Writes summary.csv and metrics.png.

Recovery time = seconds after bulk injection until VoIP RTT drops back
below CONGESTION_RTT_MS and stays there for CLEAR_HOLD_TICKS samples.

    python3 monitoring/analyze.py results/<run>
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common import config as cfg

CLASSES = ["voip", "video", "bulk"]
QUEUE_NAMES = {qid: spec["name"] for qid, spec in cfg.STATIC_QOS["queues"].items()}


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


def load_run(run_dir):
    meta_path = os.path.join(run_dir, "run_meta.json")
    meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    per_class = {c: iperf_intervals(os.path.join(run_dir, f"{c}.json")) for c in CLASSES}
    samples = pd.read_csv(os.path.join(run_dir, "samples.csv"))
    dec_path = os.path.join(run_dir, "decisions.csv")
    decisions = pd.read_csv(dec_path) if os.path.exists(dec_path) else pd.DataFrame()
    return meta, per_class, samples, decisions


def recovery_time(samples, t_cong):
    """Seconds from t_cong until VoIP RTT is back under threshold and stays."""
    after = samples[samples["t"] >= t_cong].reset_index(drop=True)
    ok = (after["voip_rtt_ms"] < cfg.CONGESTION_RTT_MS).tolist()
    hold = cfg.CLEAR_HOLD_TICKS
    for i in range(len(ok) - hold + 1):
        if all(ok[i:i + hold]):
            return round(after.loc[i, "t"] - t_cong, 1)
    return None


def build_summary(meta, per_class, samples):
    t_cong = meta.get("t_cong", 0)
    during = samples[samples["t"] >= t_cong]
    rows = []
    for c, df in per_class.items():
        if df.empty:
            continue
        df_c = df[df["t"] >= t_cong]
        rows.append({
            "mode": meta.get("mode", "?"),
            "class": c,
            "avg_mbps": df["mbps"].mean(),
            "avg_mbps_congested": df_c["mbps"].mean(),
            "avg_jitter_ms": df["jitter_ms"].mean() if df["jitter_ms"].notna().any() else None,
            "avg_loss_pct": df["loss_pct"].mean() if df["loss_pct"].notna().any() else None,
            "loss_pct_congested": df_c["loss_pct"].mean() if df_c["loss_pct"].notna().any() else None,
            "avg_rtt_ms": samples[f"{c}_rtt_ms"].mean(),
            "avg_rtt_ms_congested": during[f"{c}_rtt_ms"].mean(),
            "max_rtt_ms": samples[f"{c}_rtt_ms"].max(),
        })
    return pd.DataFrame(rows)


def plot_run(run_dir, meta, per_class, samples, decisions):
    t_cong = meta.get("t_cong")
    fig, axes = plt.subplots(4, 1, figsize=(9, 13), sharex=True)

    for c, df in per_class.items():
        if not df.empty:
            axes[0].plot(df["t"], df["mbps"], label=c)
    axes[0].set_ylabel("App throughput (Mbit/s)")

    for c in CLASSES:
        axes[1].plot(samples["t"], samples[f"{c}_rtt_ms"], label=c)
    axes[1].axhline(cfg.CONGESTION_RTT_MS, ls=":", c="grey", label="RTT threshold")
    axes[1].set_ylabel("RTT (ms)")

    for c, df in per_class.items():
        if not df.empty and df["loss_pct"].notna().any():
            axes[2].plot(df["t"], df["loss_pct"], label=c)
    axes[2].set_ylabel("Loss (%)")

    if "q0_mbps" in samples:
        axes[3].stackplot(samples["t"],
                          [samples[f"q{q}_mbps"] for q in (0, 1, 2)],
                          labels=[QUEUE_NAMES[q] for q in (0, 1, 2)], alpha=0.8)
        axes[3].axhline(cfg.BOTTLENECK_BW_MBPS, ls=":", c="grey", label="link capacity")
    axes[3].set_ylabel("Bottleneck queue bw (Mbit/s)")
    axes[3].set_xlabel("Time (s)")

    for ax in axes:
        if t_cong is not None:
            ax.axvline(t_cong, c="red", ls="--", lw=1, label="bulk starts")
        if not decisions.empty:
            for t in decisions.loc[decisions["action"] != "hold", "t"]:
                ax.axvline(t, c="green", ls="-", lw=0.6, alpha=0.4)
        ax.legend(loc="upper right", fontsize=8)

    fig.suptitle(os.path.basename(run_dir.rstrip("/")))
    fig.tight_layout()
    fig.savefig(os.path.join(run_dir, "metrics.png"), dpi=120)
    plt.close(fig)


def analyze(run_dir):
    meta, per_class, samples, decisions = load_run(run_dir)
    summary = build_summary(meta, per_class, samples)
    if "t_cong" in meta:
        summary["recovery_time_s"] = recovery_time(samples, meta["t_cong"])
    if not decisions.empty:
        summary["policy_changes"] = int((decisions["action"] != "hold").sum())
    summary.to_csv(os.path.join(run_dir, "summary.csv"), index=False)
    plot_run(run_dir, meta, per_class, samples, decisions)
    print(summary.to_string(index=False))
    return summary


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: analyze.py results/<run>")
        sys.exit(1)
    analyze(sys.argv[1])
