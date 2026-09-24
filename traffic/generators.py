"""Stream A: per-class traffic generators built on iperf3.

Each generator runs on a Mininet host object and writes iperf3 JSON output
to results/<run>/<class>.json so Stream C can parse throughput/jitter/loss.

    voip  : low-rate UDP, small packets, jitter-sensitive (URLLC-like)
    video : steady mid-rate UDP stream (eMBB-like)
    bulk  : N parallel greedy TCP flows (best effort)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common import config as cfg


def start_servers(server, run_dir):
    """One iperf3 server per class so each class has its own port/queue."""
    for name, port in cfg.CLASS_PORTS.items():
        log = os.path.join(run_dir, f"server_{name}.log")
        server.cmd(f"iperf3 -s -p {port} -i 1 -J > {log} 2>&1 &")


def start_voip(host, run_dir, duration):
    out = os.path.join(run_dir, "voip.json")
    host.cmd(
        f"iperf3 -c {cfg.SERVER_IP} -p {cfg.VOIP_PORT} -u "
        f"-b {cfg.VOIP_RATE} -l {cfg.VOIP_PKT_LEN} -t {duration} -i 1 -J "
        f"> {out} 2>&1 &"
    )


def start_video(host, run_dir, duration):
    out = os.path.join(run_dir, "video.json")
    host.cmd(
        f"iperf3 -c {cfg.SERVER_IP} -p {cfg.VIDEO_PORT} -u "
        f"-b {cfg.VIDEO_RATE} -l {cfg.VIDEO_PKT_LEN} -t {duration} -i 1 -J "
        f"> {out} 2>&1 &"
    )


def start_bulk(host, run_dir, duration):
    out = os.path.join(run_dir, "bulk.json")
    host.cmd(
        f"iperf3 -c {cfg.SERVER_IP} -p {cfg.BULK_PORT} "
        f"-P {cfg.BULK_PARALLEL} -t {duration} -i 1 -J "
        f"> {out} 2>&1 &"
    )


def stop_all(net):
    for h in net.hosts:
        h.cmd("pkill -f iperf3")
        h.cmd("pkill -f 'ping -n'")
