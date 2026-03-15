#!/usr/bin/env bash
# mac_worker_guard.sh — worker 守卫进程
# 确保 mac_worker.sh 一直在跑，崩了自动重启
#
# 启动：
#   nohup bash ~/Auto-Grasp-Pipeline/scripts/mac_worker_guard.sh >> ~/mac_worker.log 2>&1 &

WORKER="$HOME/Auto-Grasp-Pipeline/scripts/mac_worker.sh"

echo "[guard] 启动守卫 PID=$$  $(date)"

while true; do
  if ! pgrep -f "mac_worker.sh" > /dev/null 2>&1; then
    echo "[guard] $(date '+%H:%M:%S') worker 未运行，正在重启..."
    bash "$WORKER" &
  fi
  sleep 30
done
