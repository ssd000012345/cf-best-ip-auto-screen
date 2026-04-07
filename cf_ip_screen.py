import time
import random
import subprocess
import concurrent.futures
import requests
import re
from datetime import datetime
import os
import ipaddress

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")

# 官方 CF IP 范围
CF_IPV4_RANGES = [
    "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
    "104.16.0.0/13", "104.24.0.0/14", "108.162.192.0/18",
    "131.0.72.0/22", "141.101.64.0/18", "162.158.0.0/15",
    "172.64.0.0/13", "173.245.48.0/20", "188.114.96.0/20",
    "190.93.240.0/20", "197.234.240.0/22", "198.41.128.0/17"
]

CF_IPV6_RANGES = [
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32",
    "2405:b500::/32", "2405:8100::/32", "2a06:98c0::/29"
]

THIRD_PARTY_URLS = [
    "https://raw.githubusercontent.com/cmliu/WorkerVless2sub/main/addressesapi.txt",
    "https://raw.githubusercontent.com/cmliu/WorkerVless2sub/main/addressesipv6api.txt",
    "https://addressesapi.090227.xyz/CloudFlareYes",
    "https://raw.githubusercontent.com/gslege/CloudflareIP/main/ipv4.txt",
    "https://raw.githubusercontent.com/sefinek/Cloudflare-IP-Ranges/main/lists/cloudflare_ips_raw.txt",
    "https://raw.githubusercontent.com/muh97is/i-love-this-IP/main/sclaff/best.txt",
    "https://raw.githubusercontent.com/LoveDoLove/cf-best-domain/main/ip.txt",
    "https://cf.090227.xyz/bestip",
    "https://raw.githubusercontent.com/ircfspace/cf-ip-ranges/main/export.ipv4",
    "https://api.uouin.com/cloudflare.html"
]

def load_third_party_ips():
    ips = set()
    for url in THIRD_PARTY_URLS:
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                continue
            if "uouin.com" in url:
                ipv4 = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', r.text)
                ipv6 = re.findall(r'\b(?:[0-9a-f]{1,4}:){2,7}[0-9a-f]{1,4}\b', r.text)
                for ip in ipv4 + ipv6:
                    if len(ip) > 6:
                        ips.add(ip.strip())
            else:
                for line in r.text.splitlines():
                    line = line.strip()
                    if line and not line.startswith(('#', '//')):
                        ip_part = line.split()[0].split(':')[0] if ':' in line else line
                        if len(ip_part) > 6:
                            ips.add(ip_part)
        except:
            pass
    return list(ips)

def test_ping(ip):
    try:
        cmd = ["ping", "-c", "2", "-W", "4", ip] if ":" not in ip
