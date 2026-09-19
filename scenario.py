"""Integration: run one congestion scenario end-to-end.

Timeline (seconds):
    0        start voip + video (steady state)
    T_CONG   start bulk flows  -> bottleneck saturates
    T_END    everything stops, analysis runs

Usage (inside the container, with ryu-manager already running):
    sudo python3 scenario.py --mode none      # no QoS: raw congestion
    sudo python3 scenario.py --mode static    # static OVS queues
    sudo python3 scenario.py --mode adaptive  # static queues + adaptive manager
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mininet.log import setLogLevel

from common import config as cfg
from controller import qos_setup
from controller.adaptive_manager import AdaptiveQoSManager
from monitoring.analyze import analyze
from monitoring.metrics_collector import MetricsCollector
from topology.topo import bottleneck_port, build_net
from traffic import generators as gen

MODES = ["none", "static", "adaptive"]


def run(mode, t_cong, t_end, tag=""):
    name = f"{datetime.now():%Y%m%d-%H%M%S}-{mode}{('-' + tag) if tag else ''}"
    run_dir = os.path.join(cfg.RESULTS_DIR, name)
    os.makedirs(run_dir, exist_ok=True)

    net = build_net()
    net.start()
    port = bottleneck_port(net)
    print(f"[scenario] mode={mode} bottleneck_port={port} run_dir={run_dir}")

    if mode in ("static", "adaptive"):
        qos_setup.apply_static_qos(port)
    else:
        qos_setup.clear_qos(port)

    # Let the controller learn MACs before measurements begin.
    net.pingAll()

    server = net.get("server")
    gen.start_servers(server, run_dir)
    time.sleep(1)

    collector = MetricsCollector(net, run_dir)
    collector.start()

    manager = None
    if mode == "adaptive":
        manager = AdaptiveQoSManager(port, collector, run_dir)
        manager.start()

    gen.start_voip(net.get("voip"), run_dir, t_end)
    gen.start_video(net.get("video"), run_dir, t_end)
    print(f"[scenario] steady state for {t_cong}s")
    time.sleep(t_cong)

    print(f"[scenario] injecting bulk traffic for {t_end - t_cong}s")
    gen.start_bulk(net.get("bulk"), run_dir, t_end - t_cong)
    time.sleep(t_end - t_cong + 2)

    if manager:
        manager.stop()
    collector.stop()
    gen.stop_all(net)
    qos_setup.clear_qos(port)
    net.stop()

    with open(os.path.join(run_dir, "run_meta.json"), "w") as f:
        json.dump({"mode": mode, "t_cong": t_cong, "t_end": t_end}, f)

    print("[scenario] analysing")
    analyze(run_dir)
    print(f"[scenario] done -> {run_dir}/metrics.png")
    return run_dir


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=MODES, default="static")
    p.add_argument("--t-cong", type=int, default=15, help="seconds before bulk starts")
    p.add_argument("--t-end", type=int, default=45, help="total run length")
    p.add_argument("--tag", default="", help="suffix for the run directory")
    args = p.parse_args()
    setLogLevel("info")
    run(args.mode, args.t_cong, args.t_end, args.tag)
