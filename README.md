<div align="center">

# FurryReadingBot

**把兽人小说打包成 TXT / ZIP 的 Telegram Bot**

按作者名单放行 · 未收录作者走人工核验 · 一键分享到频道 · 上传即删

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![python-telegram-bot](https://img.shields.io/badge/python--telegram--bot-22.8%2B-2CA5E0?logo=telegram&logoColor=white)](https://github.com/python-telegram-bot/python-telegram-bot)
</div>

---

## 这是什么

一个面向**兽人向（furry）小说**的 Telegram 分发 Bot。

用户在私聊里发一条 **Linpx / FurryNovel** 链接，Bot 按「作者」判定是否有下载权限，把作品抓成 `txt`（单篇 / 系列合并）或 `zip`（系列分包 / 作者全量）回传；如果是 `txt`，还能一键分享到频道。未收录的作者不会直接放行，而是走「用户申请 → 中转频道 → 管理员人工核验」，通过后才进名单。作者本人可以带后台截图申请人下架，核验通过后进黑名单并删除频道里的历史分享。


## 功能

**下载**
- 单篇 → `txt`；系列 → 自动判断合并 `txt`（章节标题数字覆盖率 ≥ 75%）或分包 `zip`；作者主页 → 全量 `zip`
- Telegram `file_id` 缓存（默认 7 天），二次下载直接复用，不再重新上传
- 同一作品 `txt` / `zip` 都在缓存里时，让用户自己选格式
- 上传成功后删除本地文件（作者全量下载目前会残留空目录）

**名单与权限**
- 黑名单 → 拒绝下载、拒绝申请；兽人作者名单 → 直接放行；都不命中 → 只能申请
- 判定规则收口在 `policy/author.py`，下载与申请共用同一套逻辑

**申请与审核**
- 申请前明确告知后果 + 二次确认；重复申请只累计次数，不重复送审
- 申请卡片推送到中转频道，管理员点「通过 / 拒绝」→ 改名单 + 私聊通知申请人
- 管理员身份按**中转频道成员权限**判定（`creator` / `administrator`），不维护 ID 名单，撤销即时（≤60 秒）生效
- `/review` 可把历史待审申请重新推一遍

**分享**
- 公开 / 私密 / 拒绝三按钮；同一作品默认 3 天冷却，并发点击有拦截
- `SHARE_MODE=test` 只发测试频道；`prod` 按评分分流到「兽人小说 / 兽人阅读」
- 分享记录带 `message_id`，作者下架时能逐条回溯删除

**版权与下架**
- 作者本人：主页链接 → 确认 → 私聊提交 Pixiv 后台截图 → 中转频道核验
- 核验通过 = 进黑名单 + 移出兽人名单 + 删除该作者的频道历史分享

## 使用

私聊 Bot，直接发一条链接即可（一次一个）：

```text
https://linpx.ink/pixiv/novel/18012577     # 单篇
https://linpx.ink/pixiv/series/16181401    # 系列
https://linpx.ink/pixiv/user/130586197     # 作者全部作品
```

| 命令 | 作用 | 权限 |
|---|---|---|
| `/start` `/help` `/ping` | 欢迎 / 命令列表 / 返回 chat_id 与语言 | 所有人 |
| `/down <链接>` | 等价于直接发链接 | 所有人 |
| `/furry [作者ID/主页链接]` | 申请把作者加入兽人作者名单 | 所有人 |
| `/black [作者ID/主页链接]` | 作者本人申请下架 | 所有人 |
| `/review` | 重推待审申请 | 中转频道管理员 |

完整场景、失败提示与 FAQ 见 [02 · 用户使用流程](docs/02-用户使用流程.md)。


## 快速开始

要求 **Python 3.12+**，推荐 [uv](https://docs.astral.sh/uv/)。

```powershell
git clone https://github.com/<owner>/FurryReadingBot.git
cd FurryReadingBot

uv sync
Copy-Item .env.example .env          # Linux / macOS: cp .env.example .env
# 编辑 .env，至少填 BOT_TOKEN 与 TEST_CHANNEL

New-Item -ItemType Directory -Force -Path data | Out-Null   # Linux / macOS: mkdir -p data
Copy-Item data.example\*.json data\  # 可选：导入示例兽人作者名单
.venv\Scripts\python.exe bot.py
```

> `<owner>` 换成实际仓库地址；Linux / macOS 用 `.venv/bin/python bot.py`，没有 uv 时用 `venv + pip` 装依赖（见 [07 §2](docs/07-配置与部署.md)）。
> 不拷 `data.example` 也能启动：缺失的 JSON 会自动建为空，只是所有作者都要走申请。

安装、频道配置、上线自检、systemd 部署、常见报错：**[07 · 配置与部署](docs/07-配置与部署.md)**。


## 配置

全部配置都在 `.env`，缺失时只有 `BOT_TOKEN` 会明确报错。

| 变量 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `BOT_TOKEN` | ✅ | — | Bot Token，缺失直接退出 |
| `TEST_CHANNEL` | 分享 / 审核必填 | 空 | `SHARE_MODE=test` 时的分享目标，也是中转频道回退值 |
| `TRANSIT_CHANNEL` | 审核必填 | `TEST_CHANNEL` | 待审申请（作者申请 / 下架申请）的中转频道 |
| `SHARE_MODE` | 可选 | `test` | `test` 只发测试频道；`prod` 发正式频道 |
| `FURRY_NOVELS` / `FURRY_READING` | `prod` 必填 | 空 | 兽人小说 / 兽人阅读频道，`prod` 下按评分分流 |
| `SHARE_SCORE_THRESHOLD` | 可选 | `7` | 同时发兽人阅读的评分下限 |
| `SHARE_COOLDOWN_DAYS` / `FILE_CACHE_TTL_DAYS` | 可选 | `3` / `7` | 分享冷却 / `file_id` 缓存天数 |

逐项含义、`prod` 示例、「配了不生效」的变量：见 [07 §4](docs/07-配置与部署.md)。

## 架构一览

单体、事件驱动、分层的 Bot：一个 Python 进程 + 一组 JSON 文件即可运行，没有数据库、没有任务队列、没有 Web 服务。

```text
handlers  →  services  →  policy / sources  →  storage / infra / utils
（接入）      （用例编排）   （规则 / 来源）      （基础设施）
```

三条能当红线用的约定：

- `services/` 及以下**不 import telegram**：上传、删除、送审都通过回调注入。
- **只有 `storage/` 读写业务 JSON**：原子写 + mtime 热加载 + 进程锁。
- 新增来源 = 实现 `NovelSource` + 在 `sources/__init__.py` 的 `_SOURCES` 里注册一行。

分层图、目录树、数据契约、已知越界：见 [03 · 项目架构说明](docs/03-项目架构说明.md)。


## 文档

| 文档 | 内容 |
|---|---|
| [01 · 功能清单与缺口](docs/01-功能清单与缺口.md) | 已实现 / 部分实现 / 未实现（按 P0/P1/P2），死代码、下一步 |
| [02 · 用户使用流程](docs/02-用户使用流程.md) | 六个使用场景、管理员操作、FAQ、使用建议 |
| [03 · 项目架构说明](docs/03-项目架构说明.md) | 分层与依赖、目录职责、数据契约、架构优点与问题、演进建议 |
| [04 · 如何改代码](docs/04-如何改代码.md) | 分层速查、callback action 总表、调用链解剖、依赖红线、测试映射、练习 |
| [05 · 运行时序](docs/05-运行时序.md) | 下载 / 申请审核 / 分享 / 作者下架四条时序图 |
| [06 · 未来架构](docs/06-未来架构.md) | 目标分层、核心变化、`policy/` 与 `storage/` 边界、实施顺序 |
| [07 · 配置与部署](docs/07-配置与部署.md) | 安装、环境变量、数据目录、启动自检、测试、代码风格、部署与运维 |
| [Upgrade.md](Upgrade.md) | 产品改造方案（分流、黑白名单、人工核验）与实施进度 |


## 测试

```powershell
.venv\Scripts\python.exe -m pytest test -q
```

当前基线（2026-11-13）：**220 项 → 217 passed / 3 skipped**，全绿。

| 跑法 | 命令 | 结果 |
|---|---|---|
| 全量 | `pytest test -q` | 217 passed / 3 skipped |
| 跳过真实 API 用例 | `pytest test -q --ignore=test/test_linpx.py` | 209 passed |
| 只跑真实 Linpx API | `$env:LINPX_LIVE="1"` 后 `pytest test/test_linpx.py -q` | 11 passed（3 条真实 API 用例解封） |

测试不需要真实 Bot Token。代码风格由 `test/test_style.py` 守门：**`.py` 一律 Tab 缩进（Tab = 4 列）**，行首缩进出现空格即失败；其余约定见 [07 §6~§7](docs/07-配置与部署.md)。


## 现状与路线图

| 状态 | 内容 |
|---|---|
| ✅ 已落地 | 名单判定、下载与打包、`file_id` 缓存、申请 / 审核、分享分流与冷却、作者下架 + 历史分享清理 |
| ⚠️ 已知缺口 | 配置无启动校验、作者全量下载残留目录、`callback_data` 可伪造、无 lint / Docker / 指标 |
| ❌ 未实现 | 评分（`score` 恒为 `None`）、标签 / 正文自动识别、翻译、授权白名单接入 |

完整清单与优先级见 [01](docs/01-功能清单与缺口.md)，演进方向见 [06](docs/06-未来架构.md)。


## 免责声明
- 作品版权归原作者所有。本项目只做格式转换与临时缓存，文件上传给用户 / 频道后即删除。
- 使用者需自行遵守所在地区法律法规与 Pixiv / Linpx 的服务条款，不得用于商业分发。
- 作者可通过 `/black` 申请下架；维护者应按投诉及时清理内容与名单。
- 本项目按「现状」提供，不对可用性与审核结果作任何保证。

