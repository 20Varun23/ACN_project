# Ubuntu 20.04 (Python 3.8) is deliberate: Ryu is unmaintained since 2019 and
# breaks on Python 3.10+ (eventlet/dnspython/collections.abc removals).
FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    openvswitch-switch \
    openvswitch-common \
    openvswitch-testcontroller \
    python3 \
    python3-pip \
    python3-dev \
    python3-setuptools \
    build-essential \
    git \
    iperf \
    iperf3 \
    iproute2 \
    iputils-ping \
    net-tools \
    psmisc \
    socat \
    tcpdump \
    ethtool \
    kmod \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Focal's `mininet` package only ships Python 2 bindings, so `mn` works but
# `import mininet` fails under python3. Install 2.3.0 from source instead.
RUN git clone --depth 1 --branch 2.3.0 https://github.com/mininet/mininet.git /opt/mininet \
    && cd /opt/mininet \
    && make mnexec \
    && install -m 755 mnexec /usr/local/bin/mnexec \
    && python3 setup.py install \
    && rm -rf /opt/mininet/build

COPY docker/requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
