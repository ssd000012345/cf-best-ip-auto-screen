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

# ==================== 官方 CF IP 范围 ====================
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

# ==================== 第三方列表（含 uouin） ====================
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
    """拉取第三方IP，返回列表（绝不返回 None）"""
    ips = set()
    for url in THIRD_PARTY_URLS:
        try:
            r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                continue

            if "uouin.com" in url:
                ipv4 = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', r.text)
                ipv6 = re.findall(r'\b(?:[0-9a-f]{1,4}:){2,7}[0-9a-f]{1,4}\b', r.text)
                for ip in ipv4 + ipv6:
                    if (ip.count('.') == 3 or ':' in ip) and len(ip) > 6:
                        ips.add(ip.strip())
                log(f"✅ uouin.com 提取到 {len(ipv4)+len(ipv6)} 个IP")
            else:
                for line in r.text.splitlines():
                    line = line.strip()
                    if line and not line.startswith(('#', '//')):
                        ip_part = line.split()[0].split(':')[0] if ':' in line else line
                        if (ip_part.count('.') == 3 or ':' in ip_part) and len(ip_part) > 6:
                            ips.add(ip_part)
        except Exception as e:
            log(f"⚠️ {url} 拉取失败（跳过）: {e}")
    
    result = list(ips)
    log(f"第三方IP总计: {len(result)} 个")
    return result   # 确保返回列表

def test_ping(ip, count=3):
    try:
        cmd = ["ping", "-c", str(count), "-W", "3", ip] if ":" not in ip else ["ping", "-c", str(count), "-W", "3", "-6", ip]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=8).decode()
        loss = 100.0
        latency = 9999.0
        if "packet loss" in output.lower():
            loss = float([line for line in output.splitlines() if "packet loss" in line][0].split("%")[0].split()[-1])
        if ("rtt" in output.lower() or "avg" in output.lower()) and "ms" in output:
            rtt_line = [line for line in output.splitlines() if ("rtt" in line.lower() or "avg" in line.lower()) and "ms" in line][0]
            latency = float(rtt_line.split("/")[-3]) if "/" in rtt_line else 9999
        return round(latency, 2), round(loss, 1)
    except:
        return 9999.0, 100.0

def test_download_speed(ip, timeout=6):
    try:
        url = f"http://{ip}/__down?bytes=3000000"
        start = time.time()
        r = requests.get(url, timeout=timeout, headers={"Host": "speed.cloudflare.com"})
        elapsed = time.time() - start
        speed = (len(r.content) / 1024 / 1024) / elapsed if elapsed > 0 else 0.0
        return round(speed, 2)
    except:
        return 0.0

def main():
    log("🚀 开始 Cloudflare 优选IP 筛选...")

    all_ips = set()

    # 官方采样
    for cidr_list in [CF_IPV4_RANGES, CF_IPV6_RANGES]:
        for cidr in cidr_list:
            try:
                net = ipaddress.ip_network(cidr)
                for _ in range(150):
                    all_ips.add(str(net[random.randint(0, len(net)-1)]))
            except:
                pass

    # 第三方
    third_ips = load_third_party_ips()
    all_ips.update(third_ips)

    test_ips = list(all_ips)[:1200]
    log(f"总测试IP数量: {len(test_ips)}")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        futures = [executor.submit(lambda i=ip: (i, *test_ping(i), test_download_speed(i))) for ip in test_ips]
        for future in concurrent.futures.as_completed(futures):
            ip, latency, loss, speed = future.result()
            if latency < 800 or speed > 0.3:   # 进一步放宽条件
                score = latency * 0.45 + loss * 2.5 + (100 - speed * 6 if speed > 0 else 100) * 0.3
                family = "IPv6" if ":" in ip else "IPv4"
                results.append((ip, latency, loss, speed, round(score, 2), family))

    results.sort(key=lambda x: x[4])
    top_ips = results[:30]

    with open("best_cf_ips.txt", "w", encoding="utf-8") as f:
        f.write(f"# Cloudflare 优选IP 榜单 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# 测试总量: {len(results)} 个可用IP\n\n")
        f.write("=== 综合最优 Top 30 ===\n")
        if not top_ips:
            f.write("本次测试暂无可用IP（GitHub Actions 网络环境限制），请稍后重试或降低测试严格度。\n")
        else:
            for ip, latency, loss, speed, score, family in top_ips:
                f.write(f"{ip:<18} | {latency:>6.2f}ms | {loss:>5.1f}% | {speed:>8.2f} MB/s | {score:>8.2f} | {family}\n")

    log(f"✅ 完成！找到 {len(results)} 个可用IP")

if __name__ == "__main__":
    main()
