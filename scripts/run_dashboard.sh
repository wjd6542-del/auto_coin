#!/usr/bin/env bash
# 대시보드를 세션과 분리된(detached) 프로세스로 실행한다.
# VS Code나 터미널을 닫아도 계속 살아있다.
#
# 시작:  ./scripts/run_dashboard.sh
# 종료:  pkill -f "streamlit run dashboard/app.py"
PROJECT_DIR="/Users/wjd/프로젝트/coin"
PORT="${1:-8501}"
cd "$PROJECT_DIR"
mkdir -p logs

# 기존 인스턴스 종료
pkill -f "streamlit run dashboard/app.py" 2>/dev/null && sleep 1

# nohup + disown 으로 부모 세션에서 완전히 분리
nohup "$PROJECT_DIR/.venv/bin/streamlit" run dashboard/app.py \
  --server.headless true --server.port "$PORT" \
  >> logs/dashboard.log 2>&1 &
disown
echo "대시보드 시작됨 (PID $!, 포트 $PORT). 세션 닫아도 유지됨."
echo "종료하려면: pkill -f 'streamlit run dashboard/app.py'"
