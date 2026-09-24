# SDN-Based Adaptive QoS Management for Heterogeneous 5G Traffic

Phase 1 (mid-sem): Mininet/OVS testbed with three 5G-style traffic classes,
a Ryu controller enforcing static QoS queues on a bottleneck link, and a
metrics pipeline that shows what happens to VoIP/video when bulk traffic
saturates the link.

## Layout

| Path | Stream | Purpose |
|------|--------|---------|
| `topology/topo.py` | A | Mininet topology: 3 senders -> s1 ==bottleneck== s2 -> server |
| `traffic/generators.py` | A | iperf3-based VoIP / video / bulk generators |
| `controller/qos_controller.py` | B | Ryu app: L2 learning + per-class `set_queue` on s1 |
| `controller/qos_setup.py` | B | Creates/updates/clears OVS HTB queues via `ovs-vsctl` |
| `monitoring/metrics_collector.py` | C | Live RTT + queue-counter sampler -> `samples.csv` |
| `monitoring/analyze.py` | C | Parses iperf3 JSON + samples, writes `summary.csv` and `metrics.png` |
| `scenario.py` | all | End-to-end run: topology -> QoS mode -> traffic -> congestion -> analysis |
| `common/config.py` | all | Ports, IPs, link limits, static queue rates |

## Running

```bash
docker compose build
docker compose run --rm testbed
```

Inside the container, two terminals (or `tmux`):

```bash
# terminal 1 — controller
ryu-manager controller/qos_controller.py

# terminal 2 — scenario
python3 scenario.py --mode none      # baseline: raw congestion
python3 scenario.py --mode static    # static QoS queues
python3 monitoring/analyze.py results/<run-dir>   # re-plot later
```

Each run writes `results/<timestamp>-<mode>/` containing per-class iperf3
JSON, `samples.csv`, `summary.csv` and `metrics.png`.

## Verifying each stream in isolation

```bash
# A: topology + traffic
python3 topology/topo.py              # drops into Mininet CLI
mininet> voip iperf3 -c 10.0.0.10 -p 5001 -u -b 64K -l 160 -t 5

# B: queues actually exist on the bottleneck port
python3 controller/qos_setup.py apply s1-eth4
ovs-vsctl list queue
ovs-ofctl -O OpenFlow13 dump-flows s1     # look for set_queue:N

# C: sampler output is sane
head results/<run>/samples.csv
```

## Notes

* The container needs `--privileged` and host networking (set in
  `docker-compose.yml`) because Mininet creates network namespaces and OVS
  talks to the kernel datapath.
* **Do not bump the base image past Ubuntu 20.04.** Ryu is unmaintained
  (last release 2019) and does not run on Python 3.10+: `eventlet==0.30.2`
  fails on 3.10's immutable `TimeoutError`, `dnspython==1.16.0` uses
  `collections.MutableMapping` (removed in 3.10), and upgrading either one
  breaks `ryu/app/wsgi.py`, which imports `eventlet.wsgi.ALREADY_HANDLED`.
  Python 3.8 on 20.04 is the combination Ryu actually works with.
* Phase 2 (adaptive manager) will reuse `qos_setup.update_queue()` and the
  live `samples.csv` stream as its congestion signal.
