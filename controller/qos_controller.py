"""Stream B: Ryu app — learning switch + static QoS.

Phase 1 behaviour:
  * MAC-learning L2 forwarding on every switch (OpenFlow 1.3).
  * On s1, flows destined to a known traffic-class port are steered into
    the matching OVS queue via a set_queue action, so the bottleneck egress
    port enforces the static min/max rates defined in common/config.py.

Queues themselves are created on the OVS port by qos_setup.py (ovs-vsctl),
because OpenFlow cannot create queues, only reference them.

Run:  ryu-manager controller/qos_controller.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib.packet import ethernet, ether_types, ipv4, packet, tcp, udp
from ryu.ofproto import ofproto_v1_3

from common import config as cfg

S1_DPID = 1
PORT_TO_QUEUE = {port: cfg.CLASS_QUEUE[name] for name, port in cfg.CLASS_PORTS.items()}


class QoSController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mac_to_port = {}

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        parser = dp.ofproto_parser
        ofp = dp.ofproto
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        self.add_flow(dp, 0, match, actions)
        self.logger.info("switch dpid=%s connected", dp.id)

    def add_flow(self, dp, priority, match, actions, idle=0):
        parser = dp.ofproto_parser
        ofp = dp.ofproto
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(parser.OFPFlowMod(
            datapath=dp, priority=priority, match=match,
            instructions=inst, idle_timeout=idle,
        ))

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        parser = dp.ofproto_parser
        ofp = dp.ofproto
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        self.mac_to_port.setdefault(dp.id, {})[eth.src] = in_port
        out_port = self.mac_to_port[dp.id].get(eth.dst, ofp.OFPP_FLOOD)

        actions = []
        match = None
        if out_port != ofp.OFPP_FLOOD:
            match, queue = self._classify(parser, pkt, eth, in_port)
            if dp.id == S1_DPID and queue is not None:
                actions.append(parser.OFPActionSetQueue(queue))
        actions.append(parser.OFPActionOutput(out_port))

        if match is not None:
            self.add_flow(dp, 10, match, actions, idle=30)

        data = msg.data if msg.buffer_id == ofp.OFP_NO_BUFFER else None
        dp.send_msg(parser.OFPPacketOut(
            datapath=dp, buffer_id=msg.buffer_id,
            in_port=in_port, actions=actions, data=data,
        ))

    def _classify(self, parser, pkt, eth, in_port):
        """Return (match, queue_id). Queue is None for non-class traffic."""
        ip = pkt.get_protocol(ipv4.ipv4)
        l4 = pkt.get_protocol(udp.udp) or pkt.get_protocol(tcp.tcp)
        if ip is None or l4 is None:
            return parser.OFPMatch(in_port=in_port, eth_dst=eth.dst, eth_src=eth.src), None

        queue = PORT_TO_QUEUE.get(l4.dst_port)
        if queue is None:
            return parser.OFPMatch(in_port=in_port, eth_dst=eth.dst, eth_src=eth.src), None

        fields = dict(
            in_port=in_port, eth_type=ether_types.ETH_TYPE_IP,
            ipv4_src=ip.src, ipv4_dst=ip.dst, ip_proto=ip.proto,
        )
        if isinstance(l4, udp.udp):
            fields["udp_dst"] = l4.dst_port
        else:
            fields["tcp_dst"] = l4.dst_port
        return parser.OFPMatch(**fields), queue
