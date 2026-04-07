import time
import random
import requests
import re
from datetime import datetime
import concurrent.futures
import ipaddress

# --- 配置区 ---
# 1. 官方 Cloudflare IPv4 网段
CF_IPV4_RANGES = [
    "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
    "104.16.0.0/13", "104.24.0.0/14", "108.162.192.0/18",
    "131.0.72.0/22", "141.101.64.0/18", "162.158.0.0/15",
    "172.64.0.0/13", "173.245.48.0/20", "188.114.96.0/20",
    "190.93.240.0/20", "197.234.240.0/22", "198.41.128.0/17"
]

# 2. 第三方 IP 接口 (包含你要求的 uouin 和 wetest)
THIRD_PARTY_URLS = [
    "https://api.uouin.com/cloudflare.html",
    "https://www.wetest.vip/page/cloudflare/address_v4.html",
    "https://raw.githubusercontent.com/cmliu/WorkerVless2sub/main/addressesapi.txt",
    "https://addressesapi.090227.xyz/CloudFlareYes",
    "https://cf.090227.xyz/bestip",
    "https://raw.githubusercontent.com/ircfspace/cf-ip-ranges/main/export.ipv4"
]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def fix_ip(ip):
    """确保 IP 不是以 .0 或 .255 结尾的网段地址"""
    parts = ip.split('.')
    if parts[-1] == '0' or parts[-1] == '255':
        parts[-1] = str(random.randint(1, 254))
    return ".".join(parts)

def test_ip_stability(ip):
    """
    连续进行 3 轮探测，计算平均延迟和丢包率
    """
    ip = fix_ip(ip)
    latencies = []
    rounds = 3
    headers = {"Host": "speed.cloudflare.com", "User-Agent": "Mozilla/5.0"}
    
    for _ in range(rounds):
        try:
            start = time.time()
            r = requests.get(f"http://{ip}/cdn-cgi/trace", timeout=2.5, headers=headers)
            if r.status_code == 200:
                latencies.append((time.time() - start) * 1000)
        except:
            pass
    
    if not latencies:
        return ip, 9999.0, 100.0, 99999.0
    
    avg_lat = sum(latencies) / len(latencies)
    loss_rate = ((rounds - len(latencies)) / rounds) * 100
    # 评分公式：丢包的惩罚权重极高
    score = avg_lat + (loss_rate * 50)
    return ip, round(avg_lat, 2), round(loss_rate, 1), round(score, 2)

def main():
    log("🚀 开始深度优选程序...")
    all_ips = set()

    # 第一步：官方网段全量抽样 (每个段抽 40 个，确保覆盖)
    log("正在从官方网段抽样...")
    for cidr in CF_IPV4_RANGES:
        try:
            net = ipaddress.ip_network(cidr)
            samples = random.sample(range(1, net.num_addresses - 1), min(40, net.num_addresses - 2))
            for i in samples:
                all_ips.add(str(net[0] + i))
        except: continue
    log(f"官方网段贡献了 {len(all_ips)} 个基础 IP")

    # 第二步：第三方接口抓取
    for url in THIRD_PARTY_URLS:
        try:
            r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
            found = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', r.text)
            for ip in found:
                if not ip.startswith(('10.', '127.', '172.16.', '192.168.')):
                    all_ips.add(fix_ip(ip))
        except: continue
    
    test_list = list(all_ips)
    random.shuffle(test_list)
    test_list = test_list[:1200] # 限制测试总量，保证 Action 在 5 分钟内完成
    log(f"去重后总待测 IP: {len(test_list)}")

    # 第三步：并发稳定性测试
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=60) as executor:
        futures = [executor.submit(test_ip_stability, ip) for ip in test_list]
        for future in concurrent.futures.as_completed(futures):
            ip, lat, loss, score = future.result()
            if loss < 50: # 剔除掉丢包率超过一半的垃圾 IP
                results.append((ip, lat, loss, score))

    # 按综合得分排序
    results.sort(key=lambda x: x[3])
    top_100 = results[:100]

    # 第四步：输出到文件
    with open("best_cf_ips.txt", "w", encoding="utf-8") as f:
        f.write(f"# Cloudflare 优选榜单 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("# 排序标准：综合分 = 平均延迟 + 丢包率 * 50\n")
        f.write("# 丢包率为 0% 且得分最低的 IP 实际体验最好\n\n")
        f.write(f"{'IP地址':<18} | {'平均延迟':<10} | {'丢包率':<8} | {'综合得分'}\n")
        f.write("-" * 60 + "\n")
        for ip, lat, loss, score in top_100:
            f.write(f"{ip:<18} | {lat:>7}ms | {loss:>7}% | {score:>8}\n")

    log(f"✅ 任务完成，成功优选出 {len(top_100)} 个 IP。")

if __name__ == "__main__":
    main()
