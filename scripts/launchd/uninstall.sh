#!/usr/bin/env bash
# launchd 자동 실행 해제
for p in com.coin.dashboard com.coin.paper; do
  launchctl unload ~/Library/LaunchAgents/$p.plist 2>/dev/null || true
  rm -f ~/Library/LaunchAgents/$p.plist
done
echo "해제 완료."
