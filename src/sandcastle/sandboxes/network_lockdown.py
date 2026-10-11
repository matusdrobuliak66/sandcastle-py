"""Network egress lockdown for the Docker sandbox.

Design: block everything outbound except loopback and one allowlisted
IP:port (the self-hosted model endpoint). No DNS rule is added or needed —
the allowed destination is a raw IP, and the default-deny OUTPUT policy
correctly blocks any other DNS/TCP/UDP attempt. Applied via a root-level
`docker exec --user 0:0` immediately after the container starts, before any
hook or agent work — see DockerSandboxProvider.create().

Rejected alternatives (see PLAN.md for the full reasoning): a proxy-sidecar
container (same mechanism, more moving parts), a host-level macOS firewall
rule (not container-specific, blocks all Docker traffic), `pi --offline`
(only suppresses pi's own update check, not a sandboxing control).
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass


@dataclass(frozen=True)
class NetworkLockdown:
    allow_host: str
    allow_port: int
    protocol: str = "tcp"

    def __post_init__(self) -> None:
        # Enforced by design: the allowed destination must be a raw IP, not
        # a hostname, because DNS lookups are not permitted under the
        # lockdown. A hostname here would silently never resolve.
        ipaddress.ip_address(self.allow_host)
        if not (0 < self.allow_port < 65536):
            raise ValueError(f"invalid port: {self.allow_port}")
        if self.protocol not in ("tcp", "udp"):
            raise ValueError(f"invalid protocol: {self.protocol}")

    def build_script(self) -> str:
        """Shell script to run as root inside the container, once, right
        after it starts and before anything else touches it."""
        return (
            "iptables -A OUTPUT -o lo -j ACCEPT && "
            f"iptables -A OUTPUT -p {self.protocol} -d {self.allow_host} "
            f"--dport {self.allow_port} -j ACCEPT && "
            "iptables -P OUTPUT DROP"
        )
