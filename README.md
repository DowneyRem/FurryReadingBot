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

- **下载**：单篇 `txt`；系列按章节标题数字覆盖率 ≥ 75% 自动合并 `txt`，否则分包 `zip`；作者主页全量 `zip`。`file_id` 缓存 7 天，交付后整目录删除
- **名单与权限**：黑名单拒绝下载与申请 → 兽人作者名单放行 → 其余只能申请；判定收口在 `policy/author.py`
- **申请与审核**：后果告知 + 二次确认 + 重复待审拦截；中转频道人工核验；管理员按频道权限判定（撤销 ≤60 秒生效）；`/review` 重推
- **分享**：公开 / 私密 / 拒绝；3 天冷却 + 并发拦截；`SHARE_MODE` 决定目标频道；记录带 `message_id` 供下架回溯
- **数据同步**：`/sync` 跑 `data/sync_data.sh`，脚本内 `flock` 与定时任务串行，无变动直接跳过
- **版权与下架**：作者主页 → 后台截图 → 中转频道核验 → 进黑名单 + 移出兽人名单 + 删除历史分享

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
| `/sync` | 把运营数据同步到私有仓库 | 所有人 |

完整场景、失败提示与 FAQ 见 [02 · 用户使用流程](docs/02-用户使用流程.md)。


## 跑起来

最短路径：`git clone` → `uv sync` → 填 `.env` → `.venv\Scripts\python.exe bot.py`（要求 Python 3.12+）。

| 想知道 | 看哪节 |
|---|---|
| 安装（uv / venv+pip）、数据目录与示例名单 | [07 §2~§3](docs/07-配置与部署.md) |
| `.env` 每个变量、`test` / `prod` 示例 | [07 §4](docs/07-配置与部署.md) |
| 启动方式、上线自检清单 | [07 §5](docs/07-配置与部署.md) |
| 测试基线与跑法、代码风格 | [07 §6~§7](docs/07-配置与部署.md) |
| systemd 部署、运维清单、常见报错 | [07 §8~§9](docs/07-配置与部署.md) |


## 架构

单体、事件驱动、四层：一个 Python 进程 + 一组 JSON 文件，没有数据库 / 任务队列 / Web 服务。

```text
handlers  →  services  →  policy / sources  →  storage / infra / utils
（接入）      （用例编排）   （规则 / 来源）      （基础设施）
```

红线一句话：`services/` 及以下**不 import telegram**；**只有 `storage/` 读写业务 JSON**；新增来源 = 实现 `NovelSource` + 在 `_SOURCES` 注册一行。分层图、目录树、数据契约见 [03](docs/03-项目架构说明.md)。


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


## 现状与路线图

| 状态 | 内容 |
|---|---|
| ✅ 已落地 | 名单判定、下载与打包、`file_id` 缓存、申请 / 审核、分享分流与冷却、作者下架 + 历史分享清理 |
| ⚠️ 已知缺口 | `callback_data` 可伪造、无 lint / Docker / 指标、白名单未接入判定 |
| ❌ 未实现 | 评分（`score` 恒为 `None`）、标签 / 正文自动识别、翻译、授权白名单接入 |

测试基线：`pytest test -q` → **253 passed / 3 skipped**（跑法与代码风格见 [07 §6~§7](docs/07-配置与部署.md)）。完整清单与优先级见 [01](docs/01-功能清单与缺口.md)，演进方向见 [06](docs/06-未来架构.md)。


## 免责声明
- 作品版权归原作者所有。本项目只做格式转换与临时缓存，文件上传给用户 / 频道后即删除。
- 使用者需自行遵守所在地区法律法规与 Pixiv / Linpx 的服务条款，不得用于商业分发。
- 作者可通过 `/black` 申请下架；维护者应按投诉及时清理内容与名单。
- 本项目按「现状」提供，不对可用性与审核结果作任何保证。

