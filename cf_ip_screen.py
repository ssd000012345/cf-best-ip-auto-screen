import time
import random
import requests
import re
from datetime import datetime
import concurrent.futures
import ipaddress

# --- 1. 核心采集源配置 ---
# 官方网段
CF_IPV4_RANGES = [
    "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
    "104.16.0.0/13", "104.24.0.0/14", "108.162.192.0/18",
    "131.0.72.0/22", "141.101.64.0/18", "162.158.0.0/15",
    "172.64.0.0/13", "173.245.48.0/20", "188.114.96.0/20",
    "190.93.240.0/20", "197.234.240.0/22", "198.41.128.0/17"
]

# 整合全网公开接口及 GitHub 维护列表
THIRD_PARTY_URLS = [
    "https://api.uouin.com/cloudflare.html",                   # uouin
    "https://www.wetest.vip/page/cloudflare/address_v4.html",  # wetest
    "https://cf.090227.xyz/bestip",                            # 优质测速源
    "https://addressesapi.090227.xyz/CloudFlareYes",           # 自动汇总源
    "https://raw.githubusercontent.com/cmliu/WorkerVless2sub/main/addressesapi.txt", # cmliu 维护
    "https://raw.githubusercontent.com/vfarid/cf-ip-scanner/main/ips.txt",          # vfarid
    "https://raw.githubusercontent.com/MageSlayer/Cloudflare-IP-Ranges/master/cloudflare_ips.txt",
    "https://raw.githubusercontent.com/fscarmen/warp/main/api",                      # fscarmen
    "https://raw.githubusercontent.com/ymyuuu/IPDB/main/cloudflare.txt",             # ymyuuu
    "https://raw.githubusercontent.com/ircfspace/cf-ip-ranges/main/export.ipv4",     # ircfspace
    "https://ip.164746.xyz/ip_filtered.txt",                                       # 实时过滤源
    "https://www.baipiao.eu.org/cloudflare/ips-v4"                                  # 白嫖公益源
]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def fix_ip(ip):
    """修正无效网段结尾，确保 IP 可用"""
    parts = ip.split('.')
    if parts[-1] in ['0', '255']:
        parts[-1] = str(random.randint(1, 254))
    return ".".join(parts)

def test_ip_stability(ip):
    """
    稳定性测试：针对海量测试优化，采用 2 轮快速探测
    """
    ip = fix_ip(ip)
    latencies = []
    rounds = 2
    for _ in range(rounds):
        try:
            start = time.time()
            # 模拟真实 HTTP 握手
            r = requests.get(f"http://{ip}/cdn-cgi/trace", timeout=1.2, headers={"Host": "speed.cloudflare.com"})
            if r.status_code == 200:
                latencies.append((time.time() - start) * 1000)
        except: pass
    
    if not latencies: return ip, 99999
    
    avg_lat = sum(latencies) / len(latencies)
    loss_rate = ((rounds - len(latencies)) / rounds) * 100
    # 评分公式：延迟 + 丢包惩罚
    score = avg_lat + (loss_rate * 60)
    return ip, score

def main():
    log("🌟 启动全网多源海量优选模式...")
    all_ips = set()

    # 1. 官方网段深度采样 (每个段抽 300 个)
    for cidr in CF_IPV4_RANGES:
        try:
            net = ipaddress.ip_network(cidr)
            num_samples = min(300, net.num_addresses - 2)
            samples = random.sample(range(1, net.num_addresses - 1), num_samples)
            for i in samples: all_ips.add(str(net[0] + i))
        except: continue
    log(f"官方网段初步贡献了 {len(all_ips)} 个候选")

    # 2. 第三方多源并发抓取
    def fetch_url(url):
        try:
            r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
            return re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', r.text)
        except: return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as fetcher:
        results = fetcher.map(fetch_url, THIRD_PARTY_URLS)
        for found_ips in results:
            for ip in found_ips:
                # 过滤私网地址
                if not ip.startswith(('10.', '127.', '192.168.', '172.16.')):
                    all_ips.add(fix_ip(ip))
    
    candidate_list = list(all_ips)
    random.shuffle(candidate_list)
    # 既然额度无限，直接测试前 5000 个 IP
    test_pool = candidate_list[:5000]
    log(f"去重及初筛后，待测 IP 总数: {len(test_pool)}")

    # 3. 超高并发性能筛选
    final_results = []
    # 增加并发到 120，GitHub Actions 能够轻松处理
    with concurrent.futures.ThreadPoolExecutor(max_workers=120) as executor:
        future_to_ip = {executor.submit(test_ip_stability, ip): ip for ip in test_pool}
        for future in concurrent.futures.as_completed(future_to_ip):
            ip, score = future.result()
            if score < 1000: # 剔除完全不通或极其不稳定的
                final_results.append((ip, score))

    # 按综合评分升序排列
    final_results.sort(key=lambda x: x[1])
    
    # 4. 纯净文本输出 (目标 800+ IP)
    output_count = 850  # 稍微多留一点余量
    with open("best_cf_ips.txt", "w", encoding="utf-8") as f:
        for ip, _ in final_results[:output_count]:
            f.write(f"{ip}\n")

    log(f"✅ 优选完成！已筛选出评分最高的 {len(final_results[:output_count])} 个有效 IP。")

if __name__ == "__main__":
    main()
