#!/bin/bash
set -e

# OVS needs its database + vswitchd running before Mininet can create switches.
service openvswitch-switch start >/dev/null 2>&1 || {
    mkdir -p /var/run/openvswitch /etc/openvswitch
    [ -f /etc/openvswitch/conf.db ] || ovsdb-tool create /etc/openvswitch/conf.db /usr/share/openvswitch/vswitch.ovsschema
    ovsdb-server --remote=punix:/var/run/openvswitch/db.sock \
        --remote=db:Open_vSwitch,Open_vSwitch,manager_options \
        --pidfile --detach
    ovs-vsctl --no-wait init
    ovs-vswitchd --pidfile --detach
}

# Clear any leftover Mininet state from a previous run.
mn -c >/dev/null 2>&1 || true

exec "$@"
