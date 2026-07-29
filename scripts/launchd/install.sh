#!/usr/bin/env bash
# launchd 자동 실행 등록: 대시보드(부팅시+죽으면재시작) + 페이퍼(매일 15시, 잠자기 후 깨면 캐치업)
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p ~/Library/LaunchAgents "/Users/wjd/프로젝트/coin/logs"
cp "$DIR/com.coin.dashboard.plist" "$DIR/com.coin.paper.plist" ~/Library/LaunchAgents/
# 기존 cron 페이퍼 제거 (중복 실행 방지)
( crontab -l 2>/dev/null | grep -v "run_paper.sh" || true ) | crontab - 2>/dev/null || true
for p in com.coin.dashboard com.coin.paper; do
  launchctl unload ~/Library/LaunchAgents/$p.plist 2>/dev/null || true
  launchctl load -w ~/Library/LaunchAgents/$p.plist
done
echo "설치 완료. 상태:"
launchctl list | grep coin || true
