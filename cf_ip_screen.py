import time
import random
import requests
import re
from datetime import datetime
import concurrent.futures
import ipaddress

# --- 1. 采集源配置 ---
CF_IPV4_RANGES = [
    "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
    "104.16.0.0/13", "104.24.0.0/14", "108.162.192.0/18",
    "131.0.72.0/22", "141.101.64.0/18", "162.158.0.0/15",
    "172.64.0.0/13", "173.245.48.0/20", "188.114.96.0/20",
    "190.93.240.0/20", "197.234.240.0/22", "198.41.128.0/17"
]

THIRD_PARTY_URLS = [
    "https://raw.githubusercontent.com/cmliu/WorkerVless2sub/main/addressesapi.txt",
    "https://addressesapi.090227.xyz/CloudFlareYes",
    "https://raw.githubusercontent.com/gslege/CloudflareIP/main/ipv4.txt",
    "https://raw.githubusercontent.com/sefinek/Cloudflare-IP-Ranges/main/lists/cloudflare_ips_raw.txt",
    "https://raw.githubusercontent.com/muh97is/i-love-this-IP/main/sclaff/best.txt",
    "https://raw.githubusercontent.com/LoveDoLove/cf-best-domain/main/ip.txt",
    "https://cf.090227.xyz/bestip",
    "https://raw.githubusercontent.com/ircfspace/cf-ip-ranges/main/export.ipv4",
    "https://api.uouin.com/cloudflare.html",
    "https://raw.githubusercontent.com/XIU2/CloudflareSpeedTest/master/ip.txt",
    "https://raw.githubusercontent.com/badafans/better-cloudflare-ip/master/ip.txt",
    "https://raw.githubusercontent.com/emptysuns/better-cloudflare-ip-1/master/ip.txt",
    "https://raw.githubusercontent.com/gaomengyu123/Cloudflare-IP/main/ip.txt",
    "https://raw.githubusercontent.com/P3nguin/Cloudflare/main/ip.txt",
    "https://raw.githubusercontent.com/hello-earth/cloudflare-better-ip/main/ip.txt",
    "https://raw.githubusercontent.com/femueller/cloud-ip-ranges/master/cloudflare-v4-ip-ranges.txt",
    "https://raw.githubusercontent.com/disposable/cloud-ip-ranges/master/txt/cloudflare.txt"
]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def fix_ip(ip):
    parts = ip.split('.')
    if parts[-1] in ['0', '255']:
        parts[-1] = str(random.randint(1, 254))
    return ".".join(parts)

def test_ip_stability(ip):
    ip = fix_ip(ip)
    latencies = []
    rounds = 2
    for _ in range(rounds):
        try:
            start = time.time()
            r = requests.get(f"http://{ip}/cdn-cgi/trace", timeout=1.5, headers={"Host": "speed.cloudflare.com"})
            if r.status_code == 200:
                latencies.append((time.time() - start) * 1000)
        except: pass
    if not latencies: return ip, 99999
    avg_lat = sum(latencies) / len(latencies)
    loss_rate = ((rounds - len(latencies)) / rounds) * 100
    score = avg_lat + (loss_rate * 60)
    return ip, score

def main():
    log("🌟 启动精准优选模式 (官方采样: 2500 | 第三方: 全量)...")
    all_ips = set()

    # 1. 第三方源抓取 (高优先级)
    def fetch_url(url):
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            return re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', r.text)
        except: return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as fetcher:
        fetch_results = fetcher.map(fetch_url, THIRD_PARTY_URLS)
        for found_ips in fetch_results:
            for ip in found_ips:
                if not ip.startswith(('10.', '127.', '192.168.')):
                    all_ips.add(fix_ip(ip))
    log(f"第三方源贡献唯一 IP: {len(all_ips)} 个")

    # 2. 官方网段限制采样 (约 2500 个)
    official_pool = []
    for cidr in CF_IPV4_RANGES:
        try:
            net = ipaddress.ip_network(cidr)
            # 每个网段平均分配采样额度
            samples_per_range = 2500 // len(CF_IPV4_RANGES)
            num_samples = min(samples_per_range, net.num_addresses - 2)
            samples = random.sample(range(1, net.num_addresses - 1), num_samples)
            for i in samples: official_pool.append(str(net[0] + i))
        except: continue
    
    for ip in official_pool:
        all_ips.add(fix_ip(ip))
    
    test_pool = list(all_ips)
    random.shuffle(test_pool)
    log(f"总计去重后待测 IP: {len(test_pool)}")

    # 3. 高并发测试
    final_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=120) as executor:
        future_to_ip = {executor.submit(test_ip_stability, ip): ip for ip in test_pool}
        for future in concurrent.futures.as_completed(future_to_ip):
            ip, score = future.result()
            if score < 2000:
                final_results.append((ip, score))

    final_results.sort(key=lambda x: x[1])
    
    # 4. 输出 (目标 850 个存活)
    output_target = 850 
    with open("best_cf_ips.txt", "w", encoding="utf-8") as f:
        for ip, _ in final_results[:output_target]:
            f.write(f"{ip}\n")

    log(f"✅ 任务完成！已从 {len(test_pool)} 个候选地址中筛选出前 {len(final_results[:output_target])} 个优质 IP。")

if __name__ == "__main__":
    main()
