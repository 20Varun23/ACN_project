"""Shared constants for topology, controller and monitoring."""

# Traffic classes are identified by destination UDP/TCP port.
VOIP_PORT = 5001
VIDEO_PORT = 5002
BULK_PORT = 5003

CLASS_PORTS = {
    "voip": VOIP_PORT,
    "video": VIDEO_PORT,
    "bulk": BULK_PORT,
}

# Hosts
SENDER_IPS = {
    "voip": "10.0.0.1",
    "video": "10.0.0.2",
    "bulk": "10.0.0.3",
}
SERVER_IP = "10.0.0.10"

# Bottleneck link between s1 and s2 (Mbit/s, ms)
BOTTLENECK_BW_MBPS = 10
BOTTLENECK_DELAY_MS = 5

# Traffic generator rates
VOIP_RATE = "64K"       # ~G.711-ish, 160-byte payloads every 20 ms
VOIP_PKT_LEN = 160
VIDEO_RATE = "4M"       # steady eMBB-like UDP stream
VIDEO_PKT_LEN = 1200
BULK_PARALLEL = 4       # greedy TCP flows used to saturate the link

# Static QoS queues on the bottleneck egress port (bits/s).
# Queue ids double as the OpenFlow set_queue target.
STATIC_QOS = {
    "max_rate": BOTTLENECK_BW_MBPS * 1_000_000,
    "queues": {
        0: {"name": "bulk",  "min_rate": 1_000_000, "max_rate": 10_000_000, "priority": 3},
        1: {"name": "voip",  "min_rate": 500_000,   "max_rate": 1_000_000,  "priority": 1},
        2: {"name": "video", "min_rate": 4_000_000, "max_rate": 6_000_000,  "priority": 2},
    },
}
CLASS_QUEUE = {"bulk": 0, "voip": 1, "video": 2}

# Ryu controller
CONTROLLER_IP = "127.0.0.1"
CONTROLLER_PORT = 6633

# Monitoring
SAMPLE_INTERVAL_S = 1.0
RESULTS_DIR = "results"

# Congestion detection (Stream C). Baseline RTT is ~2x one-way delay.
CONGESTION_UTIL_THRESHOLD = 0.85            # fraction of bottleneck capacity
CONGESTION_RTT_MS = 4 * BOTTLENECK_DELAY_MS  # VoIP RTT above this = congested
CLEAR_HOLD_TICKS = 3                         # samples below threshold before "clear"

# Adaptive policy (Stream B). Rates in bits/s.
ADAPTIVE = {
    "bulk_floor": 500_000,          # never starve bulk completely
    "bulk_shrink_factor": 0.5,      # per congested tick
    "bulk_restore_step": 1_000_000, # per clear tick
    "voip_protect_min": 1_000_000,
    "video_protect_min": 5_000_000,
}
