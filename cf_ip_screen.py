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

# 第三方优选列表
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
        cmd = ["ping", "-c", "2", "-W", "4", ip] if ":" not in ip else ["ping", "-c", "2", "-W", "4", "-6", ip]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=10).decode()
        loss = 100.0
        latency = 9999.0
        if "packet loss" in output.lower():
            loss = float([line for line in output.splitlines() if "packet loss" in line][0].split("%")[0].split()[-1])
        if ("rtt" in output.lower() or "avg" in output.lower()) and "ms" in output:
            rtt_line = [line for line in output.splitlines() if ("rtt" in line.lower() or "avg" in line.lower()) and "ms" in line][0]
            latency = float(rtt_line.split("/")[-3])
        return round(latency, 2), round(loss, 1)
    except:
        return 8888.0, 85.0

def test_download_speed(ip):
    try:
        url = f"http://{ip}/__down?bytes=8000000"
        start = time.time()
        r = requests.get(url, timeout=12, headers={"Host": "speed.cloudflare.com"})
        elapsed = time.time() - start
        speed = (len(r.content) / 1024 / 1024) / elapsed if elapsed > 0 else 0.0
        return round(speed, 2)
    except:
        return 0.0

def main():
    log("V2RayN实用版 CF优选IP筛选启动 (800个IP，每小时运行)")
    all_ips = set()
    
    for cidr_list in [CF_IPV4_RANGES, CF_IPV6_RANGES]:
        for cidr in cidr_list:
            try:
                net = ipaddress.ip_network(cidr)
                for _ in range(100):
                    all_ips.add(str(net[random.randint(0, len(net)-1)]))
            except:
                pass
    
    third_ips = load_third_party_ips()
    all_ips.update(third_ips)
    
    test_ips = list(all_ips)[:800]
    log(f"总测试IP数量: {len(test_ips)}")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=80) as executor:
        futures = [executor.submit(lambda i=ip: (i, *test_ping(i), test_download_speed(i))) for ip in test_ips]
        for future in concurrent.futures.as_completed(futures):
            ip, latency, loss, speed = future.result()
            if speed > 1.5 or latency < 650:
                score = latency * 0.3 + loss * 2.0 + (100 - speed * 12 if speed > 0 else 180) * 0.6
                family = "IPv6" if ":" in ip else "IPv4"
                results.append((ip, latency, loss, speed, round(score, 2), family))

    results.sort(key=lambda x: x[4])
    top_ips = results[:30]

    with open("best_cf_ips.txt", "w", encoding="utf-8") as f:
        f.write(f"# V2RayN实用 CF优选IP榜单 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f
