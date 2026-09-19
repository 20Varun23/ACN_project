"""Stream A: Mininet topology with a single bottleneck link.

    voip ---+                        +--- server
    video --+-- s1 ===bottleneck=== s2
    bulk ---+

Run directly to drop into the Mininet CLI, or import build_net() from
the scenario runner.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.topo import Topo

from common import config as cfg


class QoSTopo(Topo):
    def build(self):
        s1 = self.addSwitch("s1", protocols="OpenFlow13")
        s2 = self.addSwitch("s2", protocols="OpenFlow13")

        for name, ip in cfg.SENDER_IPS.items():
            h = self.addHost(name, ip=f"{ip}/24")
            self.addLink(h, s1)

        server = self.addHost("server", ip=f"{cfg.SERVER_IP}/24")
        self.addLink(server, s2)

        self.addLink(
            s1, s2,
            bw=cfg.BOTTLENECK_BW_MBPS,
            delay=f"{cfg.BOTTLENECK_DELAY_MS}ms",
            max_queue_size=100,
        )


def build_net():
    net = Mininet(
        topo=QoSTopo(),
        switch=OVSSwitch,
        link=TCLink,
        controller=None,
        autoSetMacs=True,
    )
    net.addController(
        "c0",
        controller=RemoteController,
        ip=cfg.CONTROLLER_IP,
        port=cfg.CONTROLLER_PORT,
    )
    return net


def bottleneck_port(net):
    """Name of s1's interface that faces s2 (where QoS queues are attached)."""
    s1, s2 = net.get("s1"), net.get("s2")
    for intf in s1.intfList():
        link = intf.link
        if link and (link.intf1.node is s2 or link.intf2.node is s2):
            return intf.name
    raise RuntimeError("s1-s2 link not found")


if __name__ == "__main__":
    setLogLevel("info")
    net = build_net()
    net.start()
    print(f"Bottleneck egress port on s1: {bottleneck_port(net)}")
    CLI(net)
    net.stop()
