# SDN-Based Adaptive QoS Management for Heterogeneous 5G Traffic

Mininet/OVS testbed with three 5G-style traffic classes (VoIP ~ URLLC,
video ~ eMBB, bulk ~ best effort) sharing one bottleneck link, a Ryu
controller steering each class into its own OVS queue, and three QoS modes
run under an identical congestion timeline:

| Mode | What happens when bulk traffic saturates the link |
|------|---------------------------------------------------|
| `none` | No queues. Everything degrades together. |
| `static` | Fixed HTB queues (VoIP > video > bulk priority). Better, but rates are hand-tuned and never change. |
| `adaptive` | Static queues **plus** a control loop that detects congestion (utilisation / VoIP RTT) and rewrites queue rates live: bulk's max-rate is halved each tick, VoIP/video min-rates are raised, then bulk is restored gradually once the link clears. |

## Layout

| Path | Stream | Purpose |
|------|--------|---------|
| `topology/topo.py` | A | Mininet topology: 3 senders -> s1 ==bottleneck== s2 -> server |
| `traffic/generators.py` | A | iperf3-based VoIP / video / bulk generators |
| `controller/qos_controller.py` | B | Ryu app: L2 learning + per-class `set_queue` on s1 |
| `controller/qos_setup.py` | B | Creates/updates/clears OVS HTB queues via `ovs-vsctl` |
| `controller/adaptive_manager.py` | B | **Adaptive QoS control loop** — the project's contribution |
| `monitoring/metrics_collector.py` | C | Live RTT + per-queue bandwidth sampler -> `samples.csv` |
| `monitoring/congestion_detector.py` | C | Congestion state machine with hysteresis |
| `monitoring/analyze.py` | C | Per-run graphs, summary, QoS recovery time |
| `monitoring/compare.py` | C | none vs static vs adaptive comparison graphs/table |
| `scenario.py` | all | One run: topology -> QoS mode -> traffic -> congestion -> analysis |
| `run_experiments.py` | all | All modes x N repeats -> `results/comparison/` |
| `common/config.py` | all | Ports, IPs, link limits, queue rates, thresholds |

## Running

```bash
docker compose build
docker compose run --rm testbed
```

Inside the container, two terminals (or `tmux`):

```bash
# terminal 1 — controller
ryu-manager controller/qos_controller.py

# terminal 2 — single run
python3 scenario.py --mode none      # baseline: raw congestion
python3 scenario.py --mode static    # static QoS queues
python3 scenario.py --mode adaptive  # static queues + adaptive manager
python3 monitoring/analyze.py results/<run-dir>   # re-plot later

# terminal 2 — full comparison (the end-sem result)
python3 run_experiments.py --repeats 3
python3 monitoring/compare.py results/<run-a> results/<run-b> ...   # re-compare later
```

Each run writes `results/<timestamp>-<mode>/` containing per-class iperf3
JSON, `samples.csv`, `decisions.csv` (adaptive only), `summary.csv` and
`metrics.png`. `run_experiments.py` additionally writes
`results/comparison/{comparison.csv,comparison.png,timeseries.png}`.

## Metrics reported

Per class, over the congested window (after bulk starts):
throughput, jitter, loss, average/max RTT, and **QoS recovery time** —
seconds after bulk injection until VoIP RTT is back under
`CONGESTION_RTT_MS` for `CLEAR_HOLD_TICKS` consecutive samples. For adaptive
runs the number of policy changes is also reported and each change is drawn
as a green line on the per-run graph.

## Tuning the adaptive policy

All knobs live in `common/config.py`:

* `CONGESTION_UTIL_THRESHOLD`, `CONGESTION_RTT_MS` — when to react
* `CLEAR_HOLD_TICKS` — hysteresis before declaring the link clear
* `ADAPTIVE.bulk_shrink_factor` / `bulk_restore_step` / `bulk_floor` — how hard and how fast bulk is throttled and restored
* `ADAPTIVE.voip_protect_min` / `video_protect_min` — guarantees raised during congestion

The policy logic can be exercised without Mininet by feeding synthetic
samples to `AdaptiveQoSManager._decide()` (see the unit check in git history).

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
