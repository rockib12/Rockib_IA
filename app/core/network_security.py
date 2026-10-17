"""Module de sécurité réseau et protection contre le SSRF (Server-Side Request Forgery).

Valide les URLs avant toute requête HTTP externe :
- Schéma http/https obligatoire
- Résolution DNS préalable de tous les enregistrements A et AAAA
- Rejet strict des adresses de boucle locale (127.0.0.0/8, ::1)
- Rejet strict des plages privées RFC 1918 (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
- Rejet strict du link-local et des métadonnées cloud (169.254.0.0/16, fe80::/10, 169.254.169.254)
- Rejet des adresses réservées, broadcast et multicast
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from typing import List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SSRFSecurityViolation(ValueError):
    """Exception levée en cas de tentative d'accès à une ressource réseau interne/privée."""
    pass


def _check_ip_safety(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    """Vérifie qu'une adresse IP ne cible aucun réseau interne, réservé ou de métadonnées."""
    if ip.is_loopback:
        raise SSRFSecurityViolation(f"Accès refusé : l'adresse {ip} est une adresse de boucle locale (loopback).")
    if ip.is_private:
        raise SSRFSecurityViolation(f"Accès refusé : l'adresse {ip} appartient à une plage IP privée.")
    if ip.is_link_local:
        raise SSRFSecurityViolation(f"Accès refusé : l'adresse {ip} est link-local (métadonnées cloud / link-local).")
    if ip.is_reserved or ip.is_multicast or ip.is_unspecified:
        raise SSRFSecurityViolation(f"Accès refusé : l'adresse {ip} est réservée ou multicast.")
    # Contrôle explicite pour les endpoints d'instance cloud (AWS, GCP, Azure, etc.)
    if str(ip) == "169.254.169.254":
        raise SSRFSecurityViolation("Accès refusé : endpoint de métadonnées d'instance cloud détecté.")


def validate_url_for_ssrf(url: str) -> List[str]:
    """Valide de manière exhaustive l'URL contre les risques SSRF (DNS + IP).

    Retourne la liste des adresses IP valides résolues en cas de succès,
    ou lève SSRFSecurityViolation en cas de violation.
    """
    if not url or not isinstance(url, str):
        raise SSRFSecurityViolation("URL non fournie ou invalide.")

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFSecurityViolation(
            f"Schéma '{parsed.scheme}' non autorisé (seuls http et https sont acceptés)."
        )

    hostname = parsed.hostname
    if not hostname:
        raise SSRFSecurityViolation("Impossible d'extraire le nom d'hôte de l'URL.")

    # 1. Vérification si l'hôte est directement une adresse IP littérale (IPv4 ou IPv6)
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None = None
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        pass  # Nom d'hôte DNS à résoudre

    if ip is not None:
        _check_ip_safety(ip)
        return [str(ip)]

    # 2. Résolution DNS stricte AVANT l'émission de la requête
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise SSRFSecurityViolation(f"Échec de résolution DNS pour l'hôte '{hostname}': {e}")

    if not addr_info:
        raise SSRFSecurityViolation(f"Aucune adresse IP résolue pour '{hostname}'.")

    resolved_ips: List[str] = []
    # 3. Contrôle de toutes les adresses IP résolues
    for entry in addr_info:
        sockaddr = entry[4]
        ip_str = sockaddr[0]
        ip = ipaddress.ip_address(ip_str)
        _check_ip_safety(ip)
        resolved_ips.append(ip_str)

    return resolved_ips


import httpcore
import httpx


class PinnedIPBackend(httpcore.AnyIOBackend):
    """Backend réseau AnyIO épinglant la connexion TCP sur une adresse IP pré-validée.

    Neutralise les attaques de type DNS Rebinding (TOCTOU) :
    Même si l'attaquant modifie l'enregistrement DNS de son domaine entre l'étape de validation
    et l'émission de la requête HTTP, la connexion TCP s'établit exclusivement sur l'adresse IP
    validée sans aucune nouvelle résolution DNS. Le SNI (TLS) et les en-têtes Host d'origine
    restent parfaitement préservés.
    """

    def __init__(self, pinned_ip: str):
        super().__init__()
        self.pinned_ip = pinned_ip

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ):
        return await super().connect_tcp(
            host=self.pinned_ip,
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


def create_pinned_async_transport(pinned_ip: str, **kwargs) -> httpx.AsyncHTTPTransport:
    """Crée un AsyncHTTPTransport httpx dont le pool de connexions est épinglé sur pinned_ip."""
    transport = httpx.AsyncHTTPTransport(**kwargs)
    transport._pool._network_backend = PinnedIPBackend(pinned_ip)
    return transport

