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

# 1. 官方 Cloudflare IPv4 网段
CF_IPV4_RANGES = [
    "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
    "104.16.0.0/13", "104.24.0.0/14", "108.162.192.0/18",
    "131.0.72.0/22", "141.101.64.0/18", "162.158.0.0/15",
    "172.64.0.0/13", "173.245.48.0/20", "188.114.96.0/20",
    "190.93.240.0/20", "197.234.240.0/22", "198.41.128.0/17"
]

# 2. 增强后的第三方接口列表
THIRD_PARTY_URLS = [
    "https://api.uouin.com/cloudflare.html",
    "https://www.wetest.vip/page/cloudflare/address_v4.html", # 你要求加入的
    "https://raw.githubusercontent.com/cmliu/WorkerVless2sub/main/addressesapi.txt",
    "https://addressesapi.090227.xyz/CloudFlareYes",
    "https://raw.githubusercontent.com/gslege/CloudflareIP/main/ipv4.txt",
    "https://raw.githubusercontent.com/sefinek/Cloudflare-IP-Ranges/main/lists/cloudflare_ips_raw.txt",
    "https://cf.090227.xyz/bestip",
    "https://raw.githubusercontent.com/ircfspace/cf-ip-ranges/main/export.ipv4"
]

def test_ip_latency(ip):
    """使用 HTTP 探测延迟，这种方式在 GitHub Actions 最稳"""
    try:
        start_t = time.time()
        # 增加 headers 模拟浏览器，防止被 CF 拦截
        r = requests.get(f"http://{ip}/cdn-cgi/trace", timeout=3, headers={"Host": "speed.cloudflare.com", "User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            latency = (time.time() - start_t) * 1000
            return ip, round(latency, 2)
    except:
        pass
    return ip, 9999.0

def main():
    log("全指标筛选启动 (官方网段 + 增强第三方)...")
    
    all_ips = set()

    # --- 第一步：强制抽取官方网段 IP ---
    log("正在从官方网段随机抽样...")
    for cidr in CF_IPV4_RANGES:
        try:
            net = ipaddress.ip_network(cidr)
            # 每个官方子网随机抽取 30 个 IP，确保覆盖面
            sample_size = min(30, net.num_addresses)
            indices = random.sample(range(net.num_addresses), sample_size)
            for i in indices:
                all_ips.add(str(net[i]))
        except Exception as e:
            continue
    log(f"官方网段贡献了 {len(all_ips)} 个基础 IP")

    # --- 第二步：抓取第三方接口 ---
    for url in THIRD_PARTY_URLS:
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            if r.status_code == 200:
                found = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', r.text)
                before_count = len(all_ips)
                for ip in found:
                    if not ip.startswith(('10.', '192.', '127.', '0.')):
                        all_ips.add(ip)
                log(f"接口 {url[:30]}... 贡献了 {len(all_ips) - before_count} 个新 IP")
        except:
            log(f"接口 {url[:30]}... 访问超时")
            
    test_list = list(all_ips)
    random.shuffle(test_list)
    # GitHub Actions 建议测试 1500 个以内，否则容易超时挂掉
    test_list = test_list[:1500]
    
    log(f"去重后总待测 IP: {len(test_list)} 个")
    
    results = []
    # 增加并发到 80，GitHub 机器性能足够处理
    with concurrent.futures.ThreadPoolExecutor(max_workers=80) as executor:
        futures = [executor.submit(test_ip_latency, ip) for ip in test_list]
        for future in concurrent.futures.as_completed(futures):
            ip, lat = future.result()
            if lat < 4000:
                results.append((ip, lat))

    # 排序
    results.sort(key=lambda x: x[1])
    top_results = results[:100]

    # --- 第三步：输出文件 ---
    with open("best_cf_ips.txt", "w", encoding="utf-8") as f:
        f.write(f"# 优选榜单 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# 待测总数: {len(test_list)} | 连通数量: {len(results)}\n\n")
        f.write(f"{'IP地址':<18} | {'HTTP延迟'}\n")
        f.write("-" * 35 + "\n")
        for ip, lat in top_results:
            f.write(f"{ip:<18} | {lat:>6} ms\n")

    log(f"任务结束，共保存 {len(top_results)} 个 IP 到文件")

if __name__ == "__main__":
    main()
