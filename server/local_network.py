"""Authenticate the route, not a supplied IP/forwarded header."""
import ipaddress
from urllib.parse import urlsplit

PRIVATE=(ipaddress.ip_network('10.0.0.0/8'),ipaddress.ip_network('172.16.0.0/12'),
         ipaddress.ip_network('192.168.0.0/16'),ipaddress.ip_network('fc00::/7'))


def adapter_networks():
    import ifaddr
    networks=[]
    for adapter in ifaddr.get_adapters():
        for item in adapter.ips:
            address=item.ip if isinstance(item.ip,str) else item.ip[0]
            try:
                host=ipaddress.ip_address(address)
                if any(host.version==network.version and host in network for network in PRIVATE):
                    networks.append(str(ipaddress.ip_network(f'{host}/{item.network_prefix}',strict=False)))
            except ValueError:pass
    return networks


def lan_pair(local,peer,networks=None):
    try:
        local,peer=ipaddress.ip_address(local),ipaddress.ip_address(peer)
        if local.version!=peer.version:return False
        if local.is_loopback:return peer.is_loopback
        if peer.is_loopback or local.is_unspecified or peer.is_unspecified:return False
        if not any(local in n and peer in n for n in PRIVATE if n.version==local.version):return False
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
