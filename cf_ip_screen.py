import time
import random
import subprocess
import concurrent.futures
import requests
import re
from datetime import datetime
import os
import ipaddress

# 配置：输出日志带时间戳
def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")

# 官方 Cloudflare IPv4 范围
CF_IPV4_RANGES = [
    "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
    "104.16.0.0/13", "104.24.0.0/14", "108.162.192.0/18",
    "131.0.72.0/22", "141.101.64.0/18", "162.158.0.0/15",
    "172.64.0.0/13", "173.245.48.0/20", "188.114.96.0/20",
    "190.93.240.0/20", "197.234.240.0/22", "198.41.128.0/17"
]

# 官方 Cloudflare IPv6 范围 (注意：GitHub Actions 默认不支持 IPv6，测速会跳过)
CF_IPV6_RANGES = [
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32",
    "2405:b500::/32", "2405:8100::/32", "2a06:98c0::/29"
]

# 第三方优选 IP 来源
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
    log("正在从第三方接口获取 IP...")
    for url in THIRD_PARTY_URLS:
        try:
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                continue
            # 通用匹配：寻找类似 IP 地址的字符串
            found = re.findall(r'(?:\d{1,3}\.){3}\d{1,3}|(?:[a-fA-F0-9]{1,4}:){2,7}[a-fA-F0-9]{1,4}', r.text)
            for ip in found:
                if len(ip) > 6:
                    ips.add(ip.strip())
        except Exception as e:
            log(f"读取接口 {url} 出错: {e}")
    return list(ips)

def test_ping(ip):
    """测试延迟和丢包，适配 Linux (GitHub Actions)"""
    try:
        is_ipv6 = ":" in ip
        # GitHub Actions Runner 通常没 IPv6，如果检测到是 IPv6 直接跳过
        if is_ipv6:
            return 8888.0, 100.0

        # -c 2: 发送2个包; -W 2: 等待2秒
        cmd = ["ping", "-c", "2", "-W", "2", ip]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode(errors='ignore')
        
        # 使用正则表达式提取丢包率
        loss_match = re.search(r'(\d+)% packet loss', output)
        loss = float(loss_match.group(1)) if loss_match else 100.0
        
        # 使用正则表达式提取平均延迟 (rtt min/avg/max/mdev)
        latency_match = re.search(r'min/avg/max/mdev = [\d.]+/([\d.]+)/', output)
        latency = float(latency_match.group(1)) if latency_match else 9999.0
        
        return round(latency, 2), round(loss, 1)
    except:
        return 8888.0, 100.0

def test_download_speed(ip):
    """测试下载速度，带内存保护"""
    try:
        # IPv6 URL 需要加方括号
        target = f"[{ip}]" if ":" in ip else ip
        url = f"http://{target}/__down?bytes=10000000" # 10MB 测试
        
        start = time.time()
        # stream=True 避免一次性载入内存，Host 头部是必须的
        with requests.get(url, timeout=6, headers={"Host": "speed.cloudflare.com"}, stream=True) as r:
            if r.status_code != 200:
                return 0.0
            content_length = 0
            for chunk in r.iter_content(chunk_size=1024*512): # 每次读 512KB
                content_length += len(chunk)
                # 如果下载超过 8 秒，直接中断（太慢了没意义）
                if time.time() - start > 8:
                    break
        
        elapsed = time.time() - start
        speed = (content_length / 1024 / 1024) / elapsed if elapsed > 0 else 0.0
        return round(speed, 2)
    except:
        return 0.0

def main():
    log("CF 优选 IP 脚本开始运行...")
    all_ips = set()
    
    # 1. 随机抽取官方 IP 段
    for cidr_list in [CF_IPV4_RANGES]: # 考虑到 GitHub 环境，暂时只测 IPv4
        for cidr in cidr_list:
            try:
                net = ipaddress.ip_network(cidr)
                num_samples = 30 if net.num_addresses > 30 else net.num_addresses
                # 随机选几个 IP
                indices = random.sample(range(net.num_addresses), num_samples)
                for i in indices:
                    all_ips.add(str(net[i]))
            except:
                continue
    
    # 2. 加入第三方采集的 IP
    third_ips = load_third_party_ips()
    all_ips.update(third_ips)
    
    test_ips = list(all_ips)
    random.shuffle(test_ips) # 打乱顺序
    test_ips = test_ips[:800] # 限制测试 800 个 IP，防止 Action 运行超时
    
    log(f"待测试 IP 总数: {len(test_ips)}")

    results = []
    # 使用 50 个并行线程进行测速
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(lambda i=ip: (i, *test_ping(i), test_download_speed(i))): ip for ip in test_ips}
        for future in concurrent.futures.as_completed(futures):
            try:
                ip, latency, loss, speed = future.result()
                # 筛选掉完全不通或延迟极高的
                if loss < 50 and latency < 1000:
                    # 评分公式：延迟占 30%，丢包占 40%，速度占 30%
                    # 速度越快分越低（这里是越小越排在前面）
                    speed_score = (100 - speed * 10) if speed < 10 else 0
                    score = latency * 0.3 + loss * 5.0 + speed_score * 0.5
                    family = "IPv6" if ":" in ip else "IPv4"
                    results.append((ip, latency, loss, speed, round(score, 2), family))
            except:
                continue

    # 按评分排序 (从小到大)
    results.sort(key=lambda x: x[4])
    top_ips = results[:30] # 取前 30 名

    # 3. 输出到文件
    output_file = "best_cf_ips.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"# 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# 总共测试: {len(test_ips)} | 达标 IP: {len(results)}\n\n")
        f.write(f"{'IP 地址':<20} | {'延迟':<8} | {'丢包':<5} | {'下载速度':<10} | {'类型'}\n")
        f.write("-" * 65 + "\n")
        for ip, latency, loss, speed, score, family in top_ips:
            f.write(f"{ip:<20} | {latency:>6}ms | {loss:>4}% | {speed:>6} MB/s | {family}\n")

    log(f"成功！已将最优的 {len(top_ips)} 个 IP 保存到 {output_file}")

if __name__ == "__main__":
    main()
