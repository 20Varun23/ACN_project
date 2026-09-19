"""Stream B: adaptive QoS manager (the Phase 2 contribution).

Control loop, once per sample:
    sample  -> CongestionDetector -> policy decision -> ovs-vsctl queue update

Policy:
  * CONGESTED  : halve bulk's max-rate each tick (down to bulk_floor) and
                 raise VoIP / video min-rate guarantees to protected levels.
  * CLEAR      : restore bulk's max-rate by bulk_restore_step per tick until
                 it is back at the static value, then drop guarantees back.

Every decision is appended to results/<run>/decisions.csv so Stream C can
overlay policy changes on the metric graphs and compute recovery time.
"""
import csv
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common import config as cfg
from controller import qos_setup
from monitoring.congestion_detector import CongestionDetector

Q_BULK, Q_VOIP, Q_VIDEO = (cfg.CLASS_QUEUE[c] for c in ("bulk", "voip", "video"))
STATIC_Q = cfg.STATIC_QOS["queues"]


class AdaptiveQoSManager:
    def __init__(self, port, collector, run_dir, logger=print):
        self.port = port
        self.collector = collector
        self.log = logger
        self.path = os.path.join(run_dir, "decisions.csv")
        self.detector = CongestionDetector()

        self.bulk_max = STATIC_Q[Q_BULK]["max_rate"]
        self.voip_min = STATIC_Q[Q_VOIP]["min_rate"]
        self.video_min = STATIC_Q[Q_VIDEO]["min_rate"]
        self._protected = False

        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._last_t = None

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5)

    def _loop(self):
        with open(self.path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t", "congested", "reason", "action",
                        "bulk_max_rate", "voip_min_rate", "video_min_rate"])
            while not self._stop.is_set():
                sample = self.collector.latest
                if sample and sample["t"] != self._last_t:
                    self._last_t = sample["t"]
                    congested, reason = self.detector.update(sample)
                    action = self._decide(congested)
                    w.writerow([sample["t"], int(congested), reason, action,
                                self.bulk_max, self.voip_min, self.video_min])
                    f.flush()
                    if action != "hold":
                        self.log(f"[adaptive] t={sample['t']} {reason} -> {action} "
                                 f"bulk_max={self.bulk_max/1e6:.2f}M")
                self._stop.wait(cfg.SAMPLE_INTERVAL_S / 2)

    def _decide(self, congested):
        a = cfg.ADAPTIVE
        if congested:
            new_bulk = max(a["bulk_floor"], int(self.bulk_max * a["bulk_shrink_factor"]))
            changed = new_bulk != self.bulk_max
            self.bulk_max = new_bulk
            if not self._protected:
                self.voip_min = a["voip_protect_min"]
                self.video_min = a["video_protect_min"]
                self._protected = True
                changed = True
            if changed:
                self._apply()
                return "shrink_bulk+protect"
            return "hold"

        static_bulk = STATIC_Q[Q_BULK]["max_rate"]
        if self.bulk_max < static_bulk:
            self.bulk_max = min(static_bulk, self.bulk_max + a["bulk_restore_step"])
            self._apply()
            return "restore_bulk"
        if self._protected:
            self.voip_min = STATIC_Q[Q_VOIP]["min_rate"]
            self.video_min = STATIC_Q[Q_VIDEO]["min_rate"]
            self._protected = False
            self._apply()
            return "unprotect"
        return "hold"

    def _apply(self):
        qos_setup.update_queue(self.port, Q_BULK, max_rate=self.bulk_max)
        qos_setup.update_queue(self.port, Q_VOIP, min_rate=self.voip_min)
        qos_setup.update_queue(self.port, Q_VIDEO, min_rate=self.video_min)
