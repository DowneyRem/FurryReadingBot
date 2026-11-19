#!/bin/bash

# 脚本在 <repo>/script/ 下，数据仓库是同级的 <repo>/data/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 1
DATA_DIR="$(cd "$SCRIPT_DIR/../data" 2>/dev/null && pwd)" || {
  echo "数据目录不存在：$SCRIPT_DIR/../data"
  exit 1
}
if [[ ! -d "$DATA_DIR/.git" ]]; then
  echo "数据目录不是 git 仓库，无法同步：$DATA_DIR"
  exit 1
fi
cd "$DATA_DIR" || exit 1

# 无人值守：git 不能停下来等账号密码
export GIT_TERMINAL_PROMPT=0
export GCM_INTERACTIVE=never

# 0. 互斥锁：定时任务与 /sync 可能同时触发，用 flock 串行，
#    避免 git index.lock / pull --rebase / push 互相竞争。
#    锁文件放在 .git 里，不会出现在 git status 中，也就不会被提交。
if command -v flock >/dev/null 2>&1; then
  LOCK_FILE="$DATA_DIR/.git/sync.lock"
  exec 9>"$LOCK_FILE" || exit 1
  if ! flock -w 60 9; then
    echo "等待其他同步任务超时，本次跳过。"
    exit 2
  fi
else
  # 没有 flock 时不加锁，但把风险提示出来，别静默继续
  echo "警告：当前环境没有 flock，本次同步不会加锁。" >&2
fi

# 1. 检查是否有未提交的运营数据更改（只认 data/*.json）
if ! changes=$(git status -s -- ':(glob)*.json'); then
  echo "读取仓库状态失败。"
  exit 3
fi

if [[ -n "$changes" ]]; then
  echo "检测到本地有新的运营数据，正在提交..."
  git add -- ':(glob)*.json' || exit 3

  # 2. 提交：bot 身份只用于本次提交，不写进仓库配置
  git -c user.name="github-actions[bot]" \
      -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
      commit -m "同步运营数据：$(date '+%Y-%m-%d %H:%M:%S')" || exit 3
elif [[ -z "$(git log --oneline origin/main..HEAD 2>/dev/null)" ]]; then
  echo "没有发现数据变动，跳过同步。"
  exit 0
else
  # 上次 push 失败时本地会留下提交；没有新数据也要把它推上去
  echo "没有新的数据变动，但本地有未推送的提交，继续推送。"
fi

# 3. 先拉远端（rebase）再推；拉取失败就回滚，本地提交仍然保留
if ! git pull origin main --rebase; then
  echo "拉取远端数据失败，本次同步已放弃（本地提交仍然保留）。"
  git rebase --abort 2>/dev/null
  exit 4
fi

if ! git push origin main; then
  echo "推送到私有仓库失败，请检查网络或凭据配置。"
  exit 5
fi

echo "数据同步到私有仓库成功！"
