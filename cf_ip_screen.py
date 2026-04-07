name: CF 优选IP 每1小时全指标自动筛选（V2RayN实用版）

on:
  schedule:
    - cron: '0 * * * *'   # 每小时整点运行（北京时间约每小时00分）
  workflow_dispatch:

jobs:
  screen:
    runs-on: ubuntu-latest
    timeout-minutes: 25
    
    steps:
      - name: 检出仓库代码
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: 设置 Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: 安装依赖
        run: pip install requests

      - name: 运行 CF 优选IP 筛选脚本（800个 + 速度优先 + V2RayN实用）
        run: python cf_ip_screen.py
        env:
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          TZ: Asia/Shanghai

      - name: 提交最新优选IP榜单（防冲突版）
        run: |
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"
          git pull --rebase origin main --strategy-option=theirs
          git add best_cf_ips.txt
          git commit -m "📊 更新 Cloudflare 优选IP 榜单 $(date +'%Y-%m-%d %H:%M:%S')" || echo "No changes"
          git push
        continue-on-error: true

      - name: 上传结果（Artifacts）
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: cf-best-ips
          path: best_cf_ips.txt
          retention-days: 7
