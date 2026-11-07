"""Restricción del panel a redes autorizadas.

Por defecto FaceGuard AI solo acepta conexiones desde el propio equipo y desde
redes privadas (LAN): 127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16,
169.254.0.0/16 y sus equivalentes IPv6. Así, aunque la Raspberry Pi escuche en
0.0.0.0 o alguien abra un puerto en el router por error, una conexión desde una
IP pública de Internet recibe 403.

FACEGUARD_ALLOWED_NETWORKS acepta:
  local     loopback + redes privadas (predeterminado)
  loopback  solo este equipo (lo usa FaceGuard AI Desktop)
  all       sin restricción (solo detrás de un proxy/VPN que ya filtre)
  CIDR,...  lista explícita, p. ej. "127.0.0.1/32,192.168.1.0/24"
"""
from __future__ import annotations

import ipaddress
import logging

log = logging.getLogger("faceguard.network")

Network = ipaddress.IPv4Network | ipaddress.IPv6Network

LOOPBACK = ["127.0.0.0/8", "::1/128"]
PRIVATE = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "100.64.0.0/10",
           "fc00::/7", "fe80::/10"]


def parse_networks(spec: str) -> list[Network] | None:
    """Convierte la configuración en redes. None significa "sin restricción"."""
    spec = (spec or "local").strip().lower()
    if spec == "all":
        return None
    if spec == "local":
        items = LOOPBACK + PRIVATE
    elif spec == "loopback":
        items = list(LOOPBACK)
    else:
        items = [s.strip() for s in spec.split(",") if s.strip()] + LOOPBACK
    nets: list[Network] = []
    for item in items:
        try:
            nets.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            log.error("Red no válida en FACEGUARD_ALLOWED_NETWORKS: %r (se ignora)", item)
    return nets


def ip_allowed(host: str | None, networks: list[Network] | None) -> bool:
    if networks is None:
        return True
    if not host:
        return False
    try:
        addr = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return any(addr in net for net in networks if net.version == addr.version)


def is_loopback(host: str | None) -> bool:
    return ip_allowed(host, parse_networks("loopback"))
