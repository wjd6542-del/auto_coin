#!/usr/bin/env bash
# 페이퍼 트레이딩 1 사이클 실행 (cron용)
#
# 매일 KST 00:30 자동 실행하려면 (crontab -e):
#   30 0 * * * /Users/wjd/프로젝트/coin/scripts/run_paper.sh
set -euo pipefail
PROJECT_DIR="/Users/wjd/프로젝트/coin"
cd "$PROJECT_DIR"
mkdir -p logs
TS="$(date '+%Y-%m-%d %H:%M:%S')"
echo "[$TS] paper run 시작" >> logs/paper.log
"$PROJECT_DIR/.venv/bin/python" main.py --mode paper >> logs/paper.log 2>&1
echo "[$TS] paper run 종료" >> logs/paper.log
