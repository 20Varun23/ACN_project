"""Stream C: congestion signal consumed by the adaptive QoS manager.

A link is declared congested when EITHER
  * total bottleneck utilisation exceeds CONGESTION_UTIL_THRESHOLD, or
  * VoIP RTT exceeds CONGESTION_RTT_MS (queueing delay is building up).

It is declared clear only after CLEAR_HOLD_TICKS consecutive samples below
both thresholds, so a single quiet sample doesn't flap the policy.
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common import config as cfg


class CongestionDetector:
    def __init__(self):
        self.congested = False
        self._clear_ticks = 0

    def update(self, sample):
        """Return (congested: bool, reason: str) for the given sample."""
        util = sample["total_mbps"] / cfg.BOTTLENECK_BW_MBPS
        rtt = sample["voip_rtt_ms"]
        rtt_bad = not math.isnan(rtt) and rtt > cfg.CONGESTION_RTT_MS
        util_bad = util > cfg.CONGESTION_UTIL_THRESHOLD

        if util_bad or rtt_bad:
            self.congested = True
            self._clear_ticks = 0
            reason = []
            if util_bad:
                reason.append(f"util={util:.0%}")
            if rtt_bad:
                reason.append(f"voip_rtt={rtt:.1f}ms")
            return True, " ".join(reason)

        if self.congested:
            self._clear_ticks += 1
            if self._clear_ticks >= cfg.CLEAR_HOLD_TICKS:
                self.congested = False
                return False, f"clear for {self._clear_ticks} ticks"
            return True, f"cooling ({self._clear_ticks}/{cfg.CLEAR_HOLD_TICKS})"

        return False, "idle"
