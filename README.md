# FurryReadingBot

面向兽人小说的 Telegram 下载 / 分享 Bot：发送 Linpx 链接即可下载 `txt` / `zip`，支持作者名单校验、用户申请、管理员中转审核与频道分享。

## 文档

| 文档 | 内容 |
|---|---|
| [01 · 功能清单与缺口](docs/01-功能清单与缺口.md) | 已实现功能、实测结果、P0/P1/P2 缺口、推进建议 |
| [02 · 用户使用流程](docs/02-用户使用流程.md) | 普通用户下载 / 申请 / 分享流程，管理员审核流程，FAQ |
| [03 · 项目架构说明](docs/03-项目架构说明.md) | 架构图、时序图、逐文件职责、优势与不足、演进建议 |
| [Upgrade.md](Upgrade.md) | 产品改造方案（分流、黑白名单、人工核验） |

## 快速开始

要求：Python 3.12+，推荐使用 [uv](https://docs.astral.sh/uv/)。

```powershell
uv sync
Copy-Item .env.example .env
# 编辑 .env，至少填写 BOT_TOKEN
.venv\Scripts\python.exe bot.py
```

必要配置：

| 变量 | 说明 |
|---|---|
| `BOT_TOKEN` | Bot Token，必填 |
| `TEST_CHANNEL` | 测试频道；当前分享的实际目标 |
| `TRANSIT_CHANNEL` | 待审核申请的中转频道；未配置时回退 `TEST_CHANNEL` |
| `SHARE_COOLDOWN_DAYS` | 分享冷却天数，默认 3 |
| `FILE_CACHE_TTL_DAYS` | `file_id` 缓存天数，默认 7 |

## 测试

```powershell
.venv\Scripts\python.exe -m pytest test -q
```

当前测试套件存在过期用例，且 `test/test_list.py` 会写入真实 `data/` 名单文件；运行前请先备份。实测状态见 [01 文档](docs/01-功能清单与缺口.md) 第 3 节。

## 目录

```text
bot.py            # 入口
handlers/         # 命令、消息、回调
services/         # 下载业务编排
sources/          # Linpx 来源适配
storage/          # 名单、申请、缓存、文件、zip
utils/            # 通用工具
data/             # 运行数据（部分 gitignore）
files/novels/     # 下载临时目录（gitignore）
test/             # pytest 用例
```
