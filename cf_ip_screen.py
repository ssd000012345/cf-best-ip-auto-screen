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

# 官方 Cloudflare IPv4 地址段
CF_IPV4_RANGES = [
    "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
    "104.16.0.0/13", "104.24.0.0/14", "108.162.192.0/18",
    "131.0.72.0/22", "141.101.64.0/18", "162.158.0.0/15",
    "172.64.0.0/13", "173.245.48.0/20", "188.114.96.0/20",
    "190.93.240.0/20", "197.234.240.0/22", "198.41.128.0/17"
]

# 第三方 IP 接口源
THIRD_PARTY_URLS = [
    "https://raw.githubusercontent.com/cmliu/WorkerVless2sub/main/addressesapi.txt",
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
    log("正在从第三方接口获取 IPv4...")
    for url in THIRD_PARTY_URLS:
        try:
            r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                # 严格匹配 IPv4 格式，排除 IPv6
                found = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', r.text)
                for ip in found:
                    # 简单校验合法性
                    if not ip.startswith(('0', '127', '255')):
                        ips.add(ip)
        except:
            continue
    return list(ips)

def test_ip_performance(ip):
    """
    针对 GitHub Actions 优化的双重测试逻辑
    """
    latency = 9999.0
    loss = 100.0
    speed = 0.0
    
    # 步骤 1: 延迟测试
    # 优先尝试系统 Ping
    try:
        cmd = ["ping", "-c", "2", "-i", "0.3", "-W", "2", ip]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode(errors='ignore')
        
        loss_match = re.search(r'(\d+)% packet loss', output)
        loss = float(loss_match.group(1)) if loss_match else 100.0
        
        lat_match = re.search(r'min/avg/max/mdev = [\d.]+/([\d.]+)/', output)
        latency = float(lat_match.group(1)) if lat_match else 9999.0
    except:
        # 如果 Ping 报错（权限或环境问题），切换到 HTTP 探测
        try:
            start_t = time.time()
            r = requests.get(f"http://{ip}/cdn-cgi/trace", timeout=2, headers={"Host": "speed.cloudflare.com"})
            if r.status_code == 200:
                latency = round((time.time() - start_t) * 1000, 2)
                loss = 0.0
        except:
            pass

    # 步骤 2: 速度测试 (仅对延迟低于 2500ms 的 IP 进行)
    if latency < 2500:
        try:
            # 下载 5MB 测试数据
            url = f"http://{ip}/__down?bytes=5000000"
            start_t = time.time()
            with requests.get(url, timeout=6, headers={"Host": "speed.cloudflare.com"}, stream=True) as r:
                if r.status_code == 200:
                    downloaded = 0
                    for chunk in r.iter_content(chunk_size=1024*512):
                        downloaded += len(chunk)
                        if time.time() - start_t > 6: break # 超时强制停止
                    
                    duration = time.time() - start_t
                    speed = (downloaded / 1024 / 1024) / duration if duration > 0 else 0.0
        except:
            speed = 0.0

    return ip, round(latency, 2), round(loss, 1), round(speed, 2)

def main():
    log("CF 优选 IP (纯净 IPv4 版) 启动...")
    all_ips = set()
    
    # 1. 抽取官方 IPv4 段 IP (每个段抽 15 个，增加覆盖面)
    for cidr in CF_IPV4_RANGES:
        try:
            net = ipaddress.ip_network(cidr)
            samples = random.sample(range(net.num_addresses), min(15, net.num_addresses))
            for i in samples:
                all_ips.add(str(net[i]))
        except: continue
        
    # 2. 加入第三方 IPv4
    third_ips = load_third_party_ips()
    all_ips.update(third_ips)
    
    test_list = list(all_ips)
    random.shuffle(test_list)
    # 限制测试总数，防止 Action 运行时间过长被 GitHub 强制中断
    test_list = test_list[:600] 
    
    log(f"待测试 IPv4 总数: {len(test_list)}")
    
    results = []
    # 维持 40-50 线程在 GitHub 环境较为稳定
    with concurrent.futures.ThreadPoolExecutor(max_workers=45) as executor:
        futures = [executor.submit(test_ip_performance, ip) for ip in test_list]
        for future in concurrent.futures.as_completed(futures):
            try:
                ip, lat, loss, speed = future.result()
                # 记录所有能够跑通延迟的 IP
                if lat < 9000:
                    # 评分权重：主要看延迟和速度
                    score = lat * 0.4 + loss * 15 + (100 - speed * 10)
                    results.append((ip, lat, loss, speed, score))
            except:
                continue

    # 按综合评分排序
    results.sort(key=lambda x: x[4])
    top_results = results[:30]

    # 3. 写入文件
    filename = "best_cf_ips.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC)\n")
        f.write(f"# 环境: GitHub Actions | 测试总数: {len(test_list)} | 有效数量: {len(results)}\n\n")
        f.write(f"{'IP地址':<18} | {'延迟':<8} | {'丢包':<5} | {'下载速度'}\n")
        f.write("-" * 55 + "\n")
        for ip, lat, loss, speed, _ in top_results:
            f.write(f"{ip:<18} | {lat:>6}ms | {loss:>4}% | {speed:>6} MB/s\n")

    log(f"任务圆满完成！输出文件: {filename}")

if __name__ == "__main__":
    main()
