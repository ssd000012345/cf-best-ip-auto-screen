import time
import random
import requests
import re
from datetime import datetime
import os
import concurrent.futures

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")

# 第三方 IP 接口源 (这些源已经过筛选)
THIRD_PARTY_URLS = [
    "https://raw.githubusercontent.com/cmliu/WorkerVless2sub/main/addressesapi.txt",
    "https://addressesapi.090227.xyz/CloudFlareYes",
    "https://raw.githubusercontent.com/gslege/CloudflareIP/main/ipv4.txt",
    "https://raw.githubusercontent.com/sefinek/Cloudflare-IP-Ranges/main/lists/cloudflare_ips_raw.txt",
    "https://cf.090227.xyz/bestip"
]

def test_ip_latency(ip):
    """
    不使用系统 Ping，直接用 HTTP 握手测延迟，最稳。
    """
    try:
        start_t = time.time()
        # 访问 Cloudflare 自身的 trace 接口
        r = requests.get(f"http://{ip}/cdn-cgi/trace", timeout=3, headers={"Host": "speed.cloudflare.com"})
        if r.status_code == 200:
            latency = (time.time() - start_t) * 1000
            return ip, round(latency, 2)
    except:
        pass
    return ip, 9999.0

def main():
    log("极简保底版启动 (已移除下载测试)...")
    
    # 1. 采集 IP
    all_ips = set()
    for url in THIRD_PARTY_URLS:
        try:
            r = requests.get(url, timeout=10)
            found = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', r.text)
            all_ips.update(found)
        except:
            continue
            
    test_list = list(all_ips)
    random.shuffle(test_list)
    test_list = test_list[:300] # 缩小范围，确保 100% 成功
    
    log(f"待测 IP: {len(test_list)} 个")
    
    results = []
    # 2. 并发测试延迟
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        futures = [executor.submit(test_ip_latency, ip) for ip in test_list]
        for future in concurrent.futures.as_completed(futures):
            ip, lat = future.result()
            if lat < 5000: # 只要能通就记录
                results.append((ip, lat))

    # 3. 排序
    results.sort(key=lambda x: x[1])
    top_results = results[:50]

    # 4. 强制写入文件
    with open("best_cf_ips.txt", "w", encoding="utf-8") as f:
        f.write(f"# 纯延迟优选榜单 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# 总计测通: {len(results)} 个 IP\n\n")
        f.write(f"{'IP地址':<18} | {'HTTP延迟'}\n")
        f.write("-" * 35 + "\n")
        if not top_results:
            f.write("警告：本次运行未发现可连通的 IP，请检查 GitHub 网络环境。")
        else:
            for ip, lat in top_results:
                f.write(f"{ip:<18} | {lat:>6} ms\n")

    log(f"任务结束，发现有效 IP {len(results)} 个")

if __name__ == "__main__":
    main()
