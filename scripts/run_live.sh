#!/usr/bin/env bash
# 실거래 1 사이클 실행 (launchd용). 안전장치(live_enabled 등)는 봇 내부에서 검사.
#
# 매일 KST 15:00 자동 실행 (launchd: com.coin.live).
set -euo pipefail
PROJECT_DIR="/Users/wjd/프로젝트/coin"
cd "$PROJECT_DIR"
mkdir -p logs
TS="$(date '+%Y-%m-%d %H:%M:%S')"
echo "[$TS] live run 시작" >> logs/live.log
"$PROJECT_DIR/.venv/bin/python" main.py --mode live >> logs/live.log 2>&1
echo "[$TS] live run 종료" >> logs/live.log
