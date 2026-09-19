"""Stream C: live metrics sampler.

Runs inside the scenario (needs Mininet host objects) and every
SAMPLE_INTERVAL_S appends one row to results/<run>/samples.csv:

    t, voip_rtt_ms, video_rtt_ms, bulk_rtt_ms, q0_tx_bytes, q1_tx_bytes, q2_tx_bytes

RTT comes from a single ping per sender; per-queue byte counters come from
`ovs-ofctl queue-stats s1` and are later differenced to get per-class
bandwidth on the bottleneck.
"""
import csv
import os
import re
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common import config as cfg

RTT_RE = re.compile(r"time=([\d.]+) ms")
QSTAT_RE = re.compile(r"queue_id=(\d+).*?tx_bytes=(\d+)", re.S)


def _rtt(host):
    out = host.cmd(f"ping -c 1 -W 1 {cfg.SERVER_IP}")
    m = RTT_RE.search(out)
    return float(m.group(1)) if m else float("nan")


def _queue_bytes(switch):
    out = switch.cmd("ovs-ofctl -O OpenFlow13 queue-stats s1")
    stats = {}
    for block in re.split(r"(?=port)", out):
        for qid, tx in QSTAT_RE.findall(block):
            stats[int(qid)] = max(stats.get(int(qid), 0), int(tx))
    return stats


class MetricsCollector:
    def __init__(self, net, run_dir):
        self.net = net
        self.path = os.path.join(run_dir, "samples.csv")
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5)

    def _loop(self):
        senders = {name: self.net.get(name) for name in cfg.SENDER_IPS}
        s1 = self.net.get("s1")
        t0 = time.time()
        with open(self.path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t", "voip_rtt_ms", "video_rtt_ms", "bulk_rtt_ms",
                        "q0_tx_bytes", "q1_tx_bytes", "q2_tx_bytes"])
            while not self._stop.is_set():
                rtts = [_rtt(senders[n]) for n in ("voip", "video", "bulk")]
                q = _queue_bytes(s1)
                w.writerow([round(time.time() - t0, 2), *rtts,
                            q.get(0, 0), q.get(1, 0), q.get(2, 0)])
                f.flush()
                self._stop.wait(cfg.SAMPLE_INTERVAL_S)
