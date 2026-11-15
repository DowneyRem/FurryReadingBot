#!/bin/bash

# 数据目录按脚本自身位置推导
DATA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 1
cd "$DATA_DIR" || exit 1

# 0. 互斥锁：服务器定时任务与 Bot 的 /sync 可能同时触发，用 flock 串行，
#    避免 git index.lock / pull --rebase / push 互相竞争。
#    锁文件放在 .git 里，不会出现在 git status 中，也就不会被提交。
#    Git Bash 没有 flock，那里跳过加锁（Windows 上 /sync 走 sync_data.ps1，
#    用的是独占锁文件）。
if command -v flock >/dev/null 2>&1; then
  LOCK_FILE="$DATA_DIR/.git/sync.lock"
  exec 9>"$LOCK_FILE" || exit 1
  if ! flock -w 240 9; then
    echo "等待其他同步任务超时，本次跳过。"
    exit 2
  fi
fi

# 1. 每次同步前自动应用机器人身份
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

# 2. 检查是否有未提交的运营数据更改
if [[ -n $(git status -s) ]]; then
  echo "检测到本地有新的运营数据，正在提交..."

  git add .
  git commit -m "同步运营数据：$(date '+%Y-%m-%d %H:%M:%S')"

  git pull origin main --rebase
  git push origin main

  echo "数据同步到私有仓库成功！"
else
  echo "没有发现数据变动，跳过同步。"
fi
