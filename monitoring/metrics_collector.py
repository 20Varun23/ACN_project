"""Stream C: live metrics sampler.

Runs inside the scenario (needs Mininet host objects) and every
SAMPLE_INTERVAL_S appends one row to results/<run>/samples.csv:

    t, voip_rtt_ms, video_rtt_ms, bulk_rtt_ms, q0_tx_bytes, q1_tx_bytes, q2_tx_bytes

Each sender runs one long-lived `ping` whose output is read by its own
thread; the sampler records the most recent RTT seen. Per-queue byte
counters come from `ovs-ofctl queue-stats` on the bottleneck port and are
differenced by analyze.py to get per-class bandwidth.

Node.cmd() is deliberately not used here: it shares one shell pipe per node
with the main thread (which starts the iperf3 generators) and asserts when
two threads talk to the same node.
"""
import csv
import os
import re
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common import config as cfg

RTT_RE = re.compile(r"time=([\d.]+)\s*ms")
# OF1.3 prints "queue 0: bytes=...", OF1.0 "queue 0: tx_bytes=..."
QSTAT_RE = re.compile(r"queue\s+(\d+):\s*(?:tx_)?bytes=(\d+)")


class _PingReader(threading.Thread):
    """Continuous ping from one host; exposes the latest RTT."""

    def __init__(self, host, target, interval):
        super().__init__(daemon=True)
        self.latest = float("nan")
        self.proc = host.popen(
            ["ping", "-n", "-i", str(interval), target],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            universal_newlines=True,
        )

    def run(self):
        for line in self.proc.stdout:
            m = RTT_RE.search(line)
            if m:
                self.latest = float(m.group(1))

    def stop(self):
        self.proc.terminate()


def queue_bytes(switch, port):
    """{queue_id: tx_bytes} for one port, read from the root namespace."""
    out = subprocess.run(
        ["ovs-ofctl", "-O", "OpenFlow13", "queue-stats", switch, port],
        capture_output=True, universal_newlines=True,
    ).stdout
    return {int(qid): int(b) for qid, b in QSTAT_RE.findall(out)}


class MetricsCollector:
    def __init__(self, net, run_dir, port, switch="s1"):
        self.net = net
        self.port = port
        self.switch = switch
        self.path = os.path.join(run_dir, "samples.csv")
        self.latest = None  # most recent sample dict, read by the adaptive manager
        self._pings = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        for name in cfg.SENDER_IPS:
            reader = _PingReader(self.net.get(name), cfg.SERVER_IP, cfg.SAMPLE_INTERVAL_S)
            reader.start()
            self._pings[name] = reader
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5)
        for reader in self._pings.values():
            reader.stop()

    def _loop(self):
        t0 = time.time()
        with open(self.path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t", "voip_rtt_ms", "video_rtt_ms", "bulk_rtt_ms",
                        "q0_tx_bytes", "q1_tx_bytes", "q2_tx_bytes"])
            while not self._stop.is_set():
                t = round(time.time() - t0, 2)
                rtts = [self._pings[n].latest for n in ("voip", "video", "bulk")]
                q = queue_bytes(self.switch, self.port)
                qb = [q.get(i, 0) for i in (0, 1, 2)]
                w.writerow([t, *rtts, *qb])
                f.flush()
                self.latest = {
                    "t": t,
                    "voip_rtt_ms": rtts[0],
                    "video_rtt_ms": rtts[1],
                    "bulk_rtt_ms": rtts[2],
                    "q_tx_bytes": {0: qb[0], 1: qb[1], 2: qb[2]},
                }
                self._stop.wait(cfg.SAMPLE_INTERVAL_S)
