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

# 第三方 IP 接口源
THIRD_PARTY_URLS = [
    "https://api.uouin.com/cloudflare.html",  # 你要求的网站
    "https://raw.githubusercontent.com/cmliu/WorkerVless2sub/main/addressesapi.txt",
    "https://addressesapi.090227.xyz/CloudFlareYes",
    "https://raw.githubusercontent.com/gslege/CloudflareIP/main/ipv4.txt",
    "https://raw.githubusercontent.com/sefinek/Cloudflare-IP-Ranges/main/lists/cloudflare_ips_raw.txt",
    "https://cf.090227.xyz/bestip",
    "https://raw.githubusercontent.com/muh97is/i-love-this-IP/main/sclaff/best.txt"
]

def test_ip_latency(ip):
    """
    通过 HTTP 探测延迟
    """
    try:
        start_t = time.time()
        r = requests.get(f"http://{ip}/cdn-cgi/trace", timeout=4, headers={"Host": "speed.cloudflare.com"})
        if r.status_code == 200:
            latency = (time.time() - start_t) * 1000
            return ip, round(latency, 2)
    except:
        pass
    return ip, 9999.0

def main():
    log("全指标筛选启动 (已集成 uouin 接口)...")
    
    all_ips = set()
    for url in THIRD_PARTY_URLS:
        try:
            # 增加超时时间到 15 秒，防止 GitHub 访问某些接口太慢
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                # 专门提取 IPv4 的正则表达式
                found = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', r.text)
                before_count = len(all_ips)
                for ip in found:
                    # 简单过滤掉内网和非法 IP
                    if not ip.startswith(('10.', '192.', '127.', '0.')):
                        all_ips.add(ip)
                log(f"接口 {url.split('/')[2]} 贡献了 {len(all_ips) - before_count} 个新 IP")
        except Exception as e:
            log(f"接口 {url} 访问失败: {e}")
            
    test_list = list(all_ips)
    random.shuffle(test_list)
    # 限制最大测试数量为 1000，防止 GitHub Action 运行超时
    test_list = test_list[:1000]
    
    log(f"去重后待测 IP 总数: {len(test_list)} 个")
    
    results = []
    # 增加线程数到 50，加快速度
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(test_ip_latency, ip) for ip in test_list]
        for future in concurrent.futures.as_completed(futures):
            ip, lat = future.result()
            if lat < 5000:
                results.append((ip, lat))

    # 排序
    results.sort(key=lambda x: x[1])
    top_results = results[:100] # 输出前 100 个 IP

    # 写入文件
    with open("best_cf_ips.txt", "w", encoding="utf-8") as f:
        f.write(f"# 优选榜单 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# 待测总数: {len(test_list)} | 连通数量: {len(results)}\n\n")
        f.write(f"{'IP地址':<18} | {'延迟'}\n")
        f.write("-" * 35 + "\n")
        if not top_results:
            f.write("没有找到有效 IP，请检查接口是否被封或网络状态。")
        else:
            for ip, lat in top_results:
                f.write(f"{ip:<18} | {lat:>6} ms\n")

    log(f"任务结束，共保存 {len(top_results)} 个 IP 到文件")

if __name__ == "__main__":
    main()
