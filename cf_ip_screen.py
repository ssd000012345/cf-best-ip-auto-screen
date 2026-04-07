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

# 官方 CF IP 范围（保持不变）
CF_IPV4_RANGES = [ ... ]   # 你之前的官方段
CF_IPV6_RANGES = [ ... ]

THIRD_PARTY_URLS = [ ... ]  # 你之前的第三方列表（含 uouin）

def load_third_party_ips():
    # （保持你之前的 load_third_party_ips 函数不变）
    ...

def test_ping(ip, count=3):   # 减少 ping 次数，加快速度
    try:
        cmd = ["ping", "-c", str(count), "-W", "3", ip] if ":" not in ip else ["ping", "-c", str(count), "-W", "3", "-6", ip]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=8).decode()
        loss = 100.0
        latency = 9999.0
        if "packet loss" in output.lower():
            loss = float([line for line in output.splitlines() if "packet loss" in line][0].split("%")[0].split()[-1])
        if "rtt" in output.lower() or "avg" in output.lower():
            try:
                rtt_line = [line for line in output.splitlines() if ("rtt" in line.lower() or "avg" in line.lower()) and "ms" in line][0]
                latency = float(rtt_line.split("/")[-3])
            except:
                pass
        return round(latency, 2), round(loss, 1)
    except:
        return 9999.0, 100.0

def test_download_speed(ip, timeout=6):   # 缩短超时时间
    try:
        url = f"http://{ip}/__down?bytes=5000000"   # 减少测试数据量，加快速度
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
    # 官方采样 + 第三方
    for cidr_list in [CF_IPV4_RANGES, CF_IPV6_RANGES]:
        for cidr in cidr_list:
            try:
                net = ipaddress.ip_network(cidr)
                for _ in range(200):
                    all_ips.add(str(net[random.randint(0, len(net)-1)]))
            except:
                pass

    third_ips = load_third_party_ips()
    all_ips.update(third_ips)

    test_ips = list(all_ips)[:1200]   # 控制数量，避免超时
    log(f"总测试IP数量: {len(test_ips)}")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        futures = [executor.submit(lambda i=ip: (i, *test_ping(i), test_download_speed(i))) for ip in test_ips]
        for future in concurrent.futures.as_completed(futures):
            ip, latency, loss, speed = future.result()
            # 放宽条件：只要延迟 < 800ms 或有速度就保留
            if latency < 800 or speed > 0.5:
                score = latency * 0.45 + loss * 2.5 + (100 - speed * 6 if speed > 0 else 100) * 0.3
                family = "IPv6" if ":" in ip else "IPv4"
                results.append((ip, latency, loss, speed, round(score, 2), family))

    results.sort(key=lambda x: x[4])
    top_ips = results[:30]

    # 输出文件
    with open("best_cf_ips.txt", "w", encoding="utf-8") as f:
        f.write(f"# Cloudflare 优选IP 全指标榜单（按三网分类） - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# 测试总量: {len(results)} | 前30综合\n\n")

        f.write("=== 综合最优 Top 30 ===\n")
        if not top_ips:
            f.write("警告：本次测试没有找到可用IP，请检查网络或放宽测试条件。\n")
        for ip, latency, loss, speed, score, family in top_ips:
            f.write(f"{ip:<18} | {latency:>6.2f}ms | {loss:>5.1f}% | {speed:>8.2f} MB/s | {score:>8.2f} | {family}\n")

    log(f"✅ 筛选完成！找到 {len(results)} 个可用IP")
    if top_ips:
        log("前5名示例：")
        for item in top_ips[:5]:
            print(f"   {item[0]} | {item[1]}ms | {item[2]}% | {item[3]} MB/s")

if __name__ == "__main__":
    main()
