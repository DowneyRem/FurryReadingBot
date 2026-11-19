# 数据同步脚本：供 /sync 与定时任务调用。
# 由 services/sync_service.py 以
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File script/sync_data.ps1
# 执行；也可以手动在仓库根目录跑同一个命令。
# 数据目录固定为脚本上一级的 data/（脚本自己进去 git add / commit / push）。
#
# 注意：本文件必须保存成「UTF-8 带 BOM」——Windows PowerShell 5.1 会把没有 BOM
# 的文件按系统 ANSI 代码页读，中文提示会变成乱码。

# 输出统一按 UTF-8 回传，Bot 侧也按 UTF-8 解码
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$ErrorActionPreference = 'Stop'
# 无人值守：git 不能停下来等账号密码
$env:GIT_TERMINAL_PROMPT = '0'
$env:GCM_INTERACTIVE = 'never'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$dataDir = Join-Path $scriptDir '..\data'
if (-not (Test-Path -LiteralPath $dataDir)) {
    Write-Output "数据目录不存在：$dataDir"
    exit 1
}
$dataDir = (Resolve-Path -LiteralPath $dataDir).Path
Set-Location -LiteralPath $dataDir

if (-not (Test-Path -LiteralPath (Join-Path $dataDir '.git'))) {
    Write-Output "数据目录不是 git 仓库，无法同步：$dataDir"
    exit 1
}

# 0. 互斥锁：定时任务与 /sync 可能同时触发，用「独占打开锁文件」串行，等不到就跳过。
#    锁文件放在 .git 里，不会出现在 git status 中，也就不会被提交。
$lockPath = Join-Path $dataDir '.git\sync.lock'
$deadline = (Get-Date).AddSeconds(60)
$lock = $null
while (-not $lock) {
    try {
        $lock = [System.IO.File]::Open(
            $lockPath, 'OpenOrCreate', 'ReadWrite', 'None')
    }
    catch [System.IO.IOException] {
        if ((Get-Date) -ge $deadline) {
            Write-Output '等待其他同步任务超时，本次跳过。'
            exit 2
        }
        Start-Sleep -Seconds 2
    }
}

try {
    # 1. 检查是否有未提交的运营数据更改（只认 data/*.json）
    $changes = git status -s -- ':(glob)*.json'
    if ($LASTEXITCODE -ne 0) {
        Write-Output "读取仓库状态失败（git status 退出码 $LASTEXITCODE）。"
        exit 3
    }
    if ($changes) {
        Write-Output '检测到本地有新的运营数据，正在提交...'
        git add -- ':(glob)*.json'
        if ($LASTEXITCODE -ne 0) { exit 3 }

        $message = '同步运营数据：' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
        # 2. 提交：bot 身份只用于本次提交，不写进仓库配置
        git -c 'user.name=github-actions[bot]' -c 'user.email=41898282+github-actions[bot]@users.noreply.github.com' commit -m $message
        if ($LASTEXITCODE -ne 0) { exit 3 }
    }
    else {
        $unpushed = ''
        try { $unpushed = git log --oneline 'origin/main..HEAD' 2>$null } catch { $unpushed = '' }
        if (-not $unpushed) {
            Write-Output '没有发现数据变动，跳过同步。'
            exit 0
        }
        # 上次 push 失败时本地会留下提交；没有新数据也要把它推上去
        Write-Output '没有新的数据变动，但本地有未推送的提交，继续推送。'
    }

    # 3. 先拉远端（rebase）再推；拉取失败就回滚，本地提交仍然保留
    git pull origin main --rebase
    if ($LASTEXITCODE -ne 0) {
        Write-Output '拉取远端数据失败，本次同步已放弃（本地提交仍然保留）。'
        # rebase 可能根本没开始（例如远端不存在）；失败不能盖掉 exit 4
        try { git rebase --abort 2>$null } catch { }
        exit 4
    }

    git push origin main
    if ($LASTEXITCODE -ne 0) {
        Write-Output '推送到私有仓库失败，请检查网络或凭据配置。'
        exit 5
    }

    Write-Output '数据同步到私有仓库成功！'
}
finally {
    if ($lock) { $lock.Dispose() }
}
