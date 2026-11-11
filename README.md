# FurryReadingBot

面向兽人小说的 Telegram 下载 / 分享 Bot：发送 Linpx 链接即可下载 `txt` / `zip`，支持作者名单校验、用户申请、管理员中转审核与频道分享。

## 文档

| 文档 | 内容 |
|---|---|
| [01 · 功能清单与缺口](docs/01-功能清单与缺口.md) | 能做什么、缺什么（P0/P1/P2）、死代码、下一步、配置速查 |
| [02 · 用户使用流程](docs/02-用户使用流程.md) | 五个使用场景、管理员操作、FAQ、边界 |
| [03 · 项目架构说明](docs/03-项目架构说明.md) | 分层与依赖、目录职责、数据契约、优势与不足、演进路线 |
| [04 · 如何改代码](docs/04-如何改代码.md) | 改代码操作手册：分层速查表、callback action 总表、调用链解剖、依赖红线、测试映射、三个练习 |
| [05 · 运行时序](docs/05-运行时序.md) | 下载 / 申请 / 分享三条时序图，标注每步对应的已知缺陷 |
| [06 · 未来架构](docs/06-未来架构.md) | 目标分层、六条核心变化、policy/ 与 repositories/ 的理由和实施顺序 |
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

当前 `test/test_linpx.py` 已过期，运行时用 `--ignore` 排除：实测状态见 [01 文档](docs/01-功能清单与缺口.md) 第 1 节。

## 代码风格

- **缩进一律 Tab（Tab = 4 列）**：由 `.editorconfig` 约定（含 PyCharm 专有的 `ij_continuation_indent_size` / `ij_smart_tabs`），由 `test/test_style.py` 守门（空格缩进直接失败）；`.idea/` 不提交。说明见 [04 · 如何改代码](docs/04-如何改代码.md) 第 5.4 节。
- 编码 UTF-8，行尾 LF（`core.autocrlf=true`，仓库内存 LF）。
- `__pycache__/`、`*.py[cod]` 已在 `.gitignore`，无需手工清理。

## 目录

```text
bot.py             # 入口
handlers/          # 命令、消息、回调
handlers/telegram/ # 回复/上传/中转适配
services/          # 下载 / 申请 / 审核 / 分享业务编排
policy/            # 名单判定（黑名单 / 兽人作者名单）
sources/           # Linpx 来源适配
storage/           # 名单、申请、缓存、文件、zip
utils/             # 通用工具
data/              # 运行数据（部分 gitignore）
files/novels/      # 下载临时目录（gitignore）
test/              # pytest 用例
```
