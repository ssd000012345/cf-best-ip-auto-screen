import time
import random
import requests
import re
from datetime import datetime
import concurrent.futures
import ipaddress

# --- 核心配置 ---
CF_IPV4_RANGES = [
    "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
    "104.16.0.0/13", "104.24.0.0/14", "108.162.192.0/18",
    "131.0.72.0/22", "141.101.64.0/18", "162.158.0.0/15",
    "172.64.0.0/13", "173.245.48.0/20", "188.114.96.0/20",
    "190.93.240.0/20", "197.234.240.0/22", "198.41.128.0/17"
]

THIRD_PARTY_URLS = [
    "https://api.uouin.com/cloudflare.html",
    "https://www.wetest.vip/page/cloudflare/address_v4.html",
    "https://raw.githubusercontent.com/cmliu/WorkerVless2sub/main/addressesapi.txt",
    "https://cf.090227.xyz/bestip"
]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def fix_ip(ip):
    parts = ip.split('.')
    if parts[-1] == '0' or parts[-1] == '255':
        parts[-1] = str(random.randint(1, 254))
    return ".".join(parts)

def test_ip_stability(ip):
    ip = fix_ip(ip)
    latencies = []
    rounds = 3
    for _ in range(rounds):
        try:
            start = time.time()
            r = requests.get(f"http://{ip}/cdn-cgi/trace", timeout=2, headers={"Host": "speed.cloudflare.com"})
            if r.status_code == 200:
                latencies.append((time.time() - start) * 1000)
        except: pass
    if not latencies: return ip, 9999.0, 100.0, 99999.0
    avg_lat = sum(latencies) / len(latencies)
    loss_rate = ((rounds - len(latencies)) / rounds) * 100
    score = avg_lat + (loss_rate * 50)
    return ip, avg_lat, loss_rate, score

def main():
    log("🚀 启动纯净 IP 筛选...")
    all_ips = set()

    # 1. 官方抽样
    for cidr in CF_IPV4_RANGES:
        try:
            net = ipaddress.ip_network(cidr)
            samples = random.sample(range(1, net.num_addresses - 1), min(35, net.num_addresses - 2))
            for i in samples: all_ips.add(str(net[0] + i))
        except: continue

    # 2. 接口采集
    for url in THIRD_PARTY_URLS:
        try:
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            found = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', r.text)
            for ip in found:
                if not ip.startswith(('10.', '127.', '192.168.')): all_ips.add(fix_ip(ip))
        except: continue
    
    test_list = list(all_ips)
    random.shuffle(test_list)
    test_list = test_list[:1000]

    # 3. 性能测试
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=60) as executor:
        futures = [executor.submit(test_ip_stability, ip) for ip in test_list]
        for future in concurrent.futures.as_completed(futures):
            ip, lat, loss, score = future.result()
            if loss < 50: results.append((ip, lat, loss, score))

    results.sort(key=lambda x: x[3])
    
    # 4. 纯净输出
    with open("best_cf_ips.txt", "w", encoding="utf-8") as f:
        for ip, lat, loss, score in results[:100]:
            f.write(f"{ip}\n")

    log(f"✅ 任务结束，{len(results[:100])} 个优选 IP 已写入 best_cf_ips.txt")

if __name__ == "__main__":
    main()
