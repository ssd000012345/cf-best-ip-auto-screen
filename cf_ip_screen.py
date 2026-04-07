import time
import random
import requests
import re
from datetime import datetime
import os
import concurrent.futures
import ipaddress

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")

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

def fix_ip(ip):
    """
    如果 IP 以 .0 结尾，将其转换为该段内随机的一个有效 IP (1-254)
    """
    if ip.endswith(".0"):
        prefix = ".".join(ip.split(".")[:-1])
        return f"{prefix}.{random.randint(1, 254)}"
    return ip

def test_ip_latency(ip):
    try:
        # 再次确保测试的是具体 IP 而不是网段
        ip = fix_ip(ip)
        start_t = time.time()
        r = requests.get(f"http://{ip}/cdn-cgi/trace", timeout=3, headers={"Host": "speed.cloudflare.com"})
        if r.status_code == 200:
            latency = (time.time() - start_t) * 1000
            return ip, round(latency, 2)
    except:
        pass
    return ip, 9999.0

def main():
    log("全指标筛选启动 (修复 .0 结尾问题)...")
    all_ips = set()

    # 1. 官方网段随机抽样 (避开 .0)
    for cidr in CF_IPV4_RANGES:
        try:
            net = ipaddress.ip_network(cidr)
            # 随机抽 50 个地址
            for _ in range(50):
                # 随机生成主机地址，ipaddress 库会自动避开网段首尾
                random_ip = str(net.network_address + random.randint(1, net.num_addresses - 2))
                all_ips.add(random_ip)
        except: continue

    # 2. 抓取第三方接口并修正
    for url in THIRD_PARTY_URLS:
        try:
            r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
            found = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', r.text)
            for ip in found:
                if not ip.startswith(('10.', '192.', '127.')):
                    all_ips.add(fix_ip(ip)) # 抓到 .0 自动修正
        except: continue
            
    test_list = list(all_ips)
    random.shuffle(test_list)
    test_list = test_list[:1500] 
    
    log(f"待测具体有效 IP 总数: {len(test_list)} 个")
    
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=80) as executor:
        futures = [executor.submit(test_ip_latency, ip) for ip in test_list]
        for future in concurrent.futures.as_completed(futures):
            ip, lat = future.result()
            if lat < 4000:
                results.append((ip, lat))

    results.sort(key=lambda x: x[1])
    
    with open("best_cf_ips.txt", "w", encoding="utf-8") as f:
        f.write(f"# 优选榜单 (已修复 .0 结尾无效 IP) - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"{'IP地址':<18} | {'HTTP延迟'}\n")
        f.write("-" * 35 + "\n")
        for ip, lat in results[:100]:
            f.write(f"{ip:<18} | {lat:>6} ms\n")

    log("任务结束，已过滤并修正网段地址。")

if __name__ == "__main__":
    main()
