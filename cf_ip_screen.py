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
    "https://cf.090227.xyz/bestip"
]

def get_ip_isp(ip):
    """通过 API 获取 IP 运营商归属"""
    try:
        # 使用 ip-api (不带 key 每分钟 45 次请求，所以这里仅对排名前列的进行识别)
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=isp,asname", timeout=2)
        data = r.json()
        info = (data.get('isp', '') + data.get('asname', '')).lower()
        if 'china mobile' in info or 'cmcc' in info: return "移动"
        if 'china unicom' in info or 'unicom' in info: return "联通"
        if 'china telecom' in info or 'telecom' in info: return "电信"
    except:
        pass
    return "通用/其他"

def test_ip_performance(ip):
    latency, loss, speed = 9999.0, 100.0, 0.0
    try:
        # Ping 测试
        cmd = ["ping", "-c", "2", "-W", "2", ip]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode(errors='ignore')
        loss_match = re.search(r'(\d+)% packet loss', output)
        loss = float(loss_match.group(1)) if loss_match else 100.0
        lat_match = re.search(r'min/avg/max/mdev = [\d.]+/([\d.]+)/', output)
        latency = float(lat_match.group(1)) if lat_match else 9999.0
    except:
        pass

    if latency < 2000:
        try:
            url = f"http://{ip}/__down?bytes=5000000"
            start_t = time.time()
            with requests.get(url, timeout=5, headers={"Host": "speed.cloudflare.com"}, stream=True) as r:
                size = 0
                for chunk in r.iter_content(chunk_size=1024*256):
                    size += len(chunk)
                    if time.time() - start_t > 5: break
                duration = time.time() - start_t
                speed = (size / 1024 / 1024) / duration if duration > 0 else 0.0
        except: pass

    return ip, round(latency, 2), round(loss, 1), round(speed, 2)

def main():
    log("CF 三网优选版启动...")
    all_ips = set()
    # 随机抽样
    for cidr in CF_IPV4_RANGES:
        try:
            net = ipaddress.ip_network(cidr)
            samples = random.sample(range(net.num_addresses), min(10, net.num_addresses))
            for i in samples: all_ips.add(str(net[i]))
        except: continue
    
    # 接口采集
    for url in THIRD_PARTY_URLS:
        try:
            r = requests.get(url, timeout=10)
            found = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', r.text)
            all_ips.update(found)
        except: continue
        
    test_list = list(all_ips)[:500]
    results = []
    log(f"开始测试 {len(test_list)} 个 IP...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(test_ip_performance, ip) for ip in test_list]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res[1] < 5000: results.append(res)

    # 排序并识别三网归属 (仅对前 60 名进行识别，节省 API 限制)
    results.sort(key=lambda x: x[1] * 0.5 + x[2] * 20 - x[3] * 2) 
    top_candidates = results[:60]
    
    categorized = {"移动": [], "联通": [], "电信": [], "通用": []}
    
    log("正在识别运营商归属...")
    for item in top_candidates:
        isp = get_ip_isp(item[0])
        if "移动" in isp: categorized["移动"].append(item)
        elif "联通" in isp: categorized["联通"].append(item)
        elif "电信" in isp: categorized["电信"].append(item)
        else: categorized["通用"].append(item)

    # 输出文件
    with open("best_cf_ips.txt", "w", encoding="utf-8") as f:
        f.write(f"# 三网分类优选 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("# 注意：Actions 环境测速偏高，请优先参考丢包率和三网分类\n\n")
        
        for key in ["移动", "联通", "电信", "通用"]:
            f.write(f"=== {key} 推荐 ===\n")
            # 每个运营商取前 8 个
            for ip, lat, loss, speed in categorized[key][:8]:
                f.write(f"{ip:<18} | {lat:>6}ms | {loss:>4}% | {speed:>6} MB/s\n")
            f.write("\n")

    log("三网分类完成！")

if __name__ == "__main__":
    main()
