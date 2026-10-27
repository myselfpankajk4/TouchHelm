"""Authenticate the route, not a supplied IP/forwarded header."""
import ipaddress
from urllib.parse import urlsplit
from .local_link import adapter_networks


def lan_pair(local,peer,networks=None):
    try:
        local,peer=ipaddress.ip_address(local),ipaddress.ip_address(peer)
        if local.version!=peer.version:return False
        if local.is_loopback:return peer.is_loopback
        if peer.is_loopback or local.is_unspecified or peer.is_unspecified:return False
        allowed=[ipaddress.ip_network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','fc00::/7')]
        if not any(local in n and peer in n for n in allowed if n.version==local.version):return False
        return any(local in n and peer in n for value in (adapter_networks() if networks is None else networks)
                   if (n:=ipaddress.ip_network(value)).version==local.version)
    except (ValueError,TypeError):return False


def local_request(request):
    try:
        transport=request.transport
        endpoint=transport.get_extra_info('sockname');peer=transport.get_extra_info('peername')
        if not endpoint or not peer or not lan_pair(endpoint[0],peer[0]):return False
        host=urlsplit(f'http://{request.host}')
        expected=ipaddress.ip_address(endpoint[0])
        if host.hostname=='localhost':
            if not expected.is_loopback:return False
        elif ipaddress.ip_address(host.hostname)!=expected:return False
        return (host.port or (443 if request.scheme=='https' else 80))==endpoint[1]
    except (ValueError,TypeError,AttributeError):return False
