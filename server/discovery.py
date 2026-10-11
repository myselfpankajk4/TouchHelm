"""
TouchHelm - Local Network Discovery Service
Broadcasts UDP beacons so Android devices on the same Wi-Fi
can instantly discover and connect to the Windows PC.
"""

import socket
import json
import time
import threading

DISCOVERY_PORT = 53317
BROADCAST_INTERVAL = 2.0  # seconds


def get_local_ip_addresses():
    """Returns detected IPv4 addresses of this Windows machine."""
    ips = []
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        primary_ip = s.getsockname()[0]
        if not primary_ip.startswith("127."):
            ips.append(primary_ip)
    except Exception:
        pass
    finally:
        if s is not None:
            s.close()

    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127.") and ":" not in ip and ip not in ips:
                ips.append(ip)
    except Exception:
        pass

    return ips or ["127.0.0.1"]


class DiscoveryBeaconService:
    def __init__(self, port: int, has_pin: bool = False, server_name: str = None):
        self.port = port
        self.has_pin = has_pin
        self.hostname = server_name or socket.gethostname()
        self.running = False
        self.thread = None
        self.listener_thread = None

    def _broadcast_loop(self):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(0.5)
        except OSError:
            if sock is not None:
                sock.close()
            return

        while self.running:
            try:
                ips = get_local_ip_addresses()
                payload = json.dumps({
                    "service": "touchhelm",
                    "version": "1.0.0",
                    "hostname": self.hostname,
                    "ips": ips,
                    "primary_ip": ips[0] if ips else "127.0.0.1",
                    "port": self.port,
                    "has_pin": self.has_pin() if callable(self.has_pin) else self.has_pin,
                    "timestamp": time.time()
                }).encode("utf-8")

                sock.sendto(payload, ("255.255.255.255", DISCOVERY_PORT))
            except Exception:
                pass

            for _ in range(int(BROADCAST_INTERVAL * 10)):
                if not self.running:
                    break
                time.sleep(0.1)

        sock.close()

    def _listen_queries_loop(self):
        """Responds directly to search queries from mobile clients."""
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", DISCOVERY_PORT))
            sock.settimeout(1.0)
        except Exception:
            if sock is not None:
                sock.close()
            return

        while self.running:
            try:
                data, addr = sock.recvfrom(2048)
                msg = json.loads(data.decode("utf-8", errors="ignore"))
                if msg.get("query") == "touchhelm_discover":
                    ips = get_local_ip_addresses()
                    reply = json.dumps({
                        "service": "touchhelm",
                        "hostname": self.hostname,
                        "ips": ips,
                        "primary_ip": ips[0] if ips else "127.0.0.1",
                        "port": self.port,
                        "has_pin": self.has_pin() if callable(self.has_pin) else self.has_pin
                    }).encode("utf-8")
                    sock.sendto(reply, addr)
            except socket.timeout:
                continue
            except Exception:
                pass

        sock.close()

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self.thread.start()
        self.listener_thread = threading.Thread(target=self._listen_queries_loop, daemon=True)
        self.listener_thread.start()

    def stop(self):
        self.running = False
        for thread in (self.thread, self.listener_thread):
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=2.0)
