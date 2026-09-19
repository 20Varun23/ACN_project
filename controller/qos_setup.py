"""Stream B: create/clear static OVS QoS queues on the bottleneck port.

OpenFlow can only *reference* queues, so they are created out-of-band with
ovs-vsctl. Phase 2's adaptive manager will reuse update_queue() to change
rates at runtime.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common import config as cfg


def _sh(cmd):
    return subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True).stdout.strip()


def apply_static_qos(port):
    clear_qos(port)
    q = cfg.STATIC_QOS["queues"]
    queue_refs = " ".join(f"queues:{qid}=@q{qid}" for qid in q)
    queue_defs = " ".join(
        f"-- --id=@q{qid} create queue "
        f"other-config:min-rate={spec['min_rate']} "
        f"other-config:max-rate={spec['max_rate']} "
        f"other-config:priority={spec['priority']}"
        for qid, spec in q.items()
    )
    _sh(
        f"ovs-vsctl -- set port {port} qos=@newqos "
        f"-- --id=@newqos create qos type=linux-htb "
        f"other-config:max-rate={cfg.STATIC_QOS['max_rate']} {queue_refs} "
        f"{queue_defs}"
    )


def update_queue(port, queue_id, min_rate=None, max_rate=None):
    qos_uuid = _sh(f"ovs-vsctl get port {port} qos")
    queue_uuid = _sh(f"ovs-vsctl get qos {qos_uuid} queues:{queue_id}")
    if min_rate is not None:
        _sh(f"ovs-vsctl set queue {queue_uuid} other-config:min-rate={min_rate}")
    if max_rate is not None:
        _sh(f"ovs-vsctl set queue {queue_uuid} other-config:max-rate={max_rate}")


def clear_qos(port):
    subprocess.run(f"ovs-vsctl clear port {port} qos", shell=True, capture_output=True)
    subprocess.run("ovs-vsctl --all destroy qos", shell=True, capture_output=True)
    subprocess.run("ovs-vsctl --all destroy queue", shell=True, capture_output=True)


def queue_stats(switch):
    """Raw `ovs-ofctl queue-stats` output for Stream C to parse."""
    return _sh(f"ovs-ofctl -O OpenFlow13 queue-stats {switch}")


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("apply", "clear"):
        print("usage: qos_setup.py apply|clear <port>")
        sys.exit(1)
    (apply_static_qos if sys.argv[1] == "apply" else clear_qos)(sys.argv[2])
    print(_sh("ovs-vsctl list queue"))
