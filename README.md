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
| [06 · 未来架构](docs/06-未来架构.md) | 目标分层、五条核心变化、policy/ 与 storage/ 的边界、实施顺序 |
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
| `TEST_CHANNEL` | 测试频道；`SHARE_MODE=test` 时唯一的分享目标 |
| `FURRY_READING` | 兽人阅读频道；`SHARE_MODE=prod` 且评分达标时同时发这里 |
| `FURRY_NOVELS` | 兽人小说频道；`SHARE_MODE=prod` 时所有作品都发这里 |
| `TRANSIT_CHANNEL` | 待审核申请的中转频道；未配置时回退 `TEST_CHANNEL` |
| `SHARE_MODE` | `test`（默认，只发测试频道）/ `prod`（按评分分流到正式频道） |
| `SHARE_SCORE_THRESHOLD` | `prod` 模式下同时发兽人阅读的评分下限，默认 7；未评分按低分处理 |
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
FurryReadingBot/
├─ bot.py                  # 入口：装配 Application，注册 5 个命令 / 2 个消息 / 1 个 callback
├─ config.py               # 从 .env 读配置（频道、分享模式、冷却、缓存 TTL）
├─ keyboards.py            # 全部 InlineKeyboardMarkup（纯展示）
├─ handlers/               # 接入层：命令、私聊消息、图片
│  ├─ start.py             #   /start /help /ping
│  ├─ download.py          #   /down 与私聊链接：解析 → 权限 → 出下载菜单
│  ├─ review.py            #   /review 重推待审申请（仅中转频道管理员）
│  ├─ media.py             #   私聊截图：作者下架材料
│  ├─ callbacks/           #   callback_data 分发与各业务展示
│  │  ├─ router.py         #     action → handler 字典分发
│  │  ├─ download.py       #     dn / ds / dst / dsz / dan
│  │  ├─ apply.py          #     af / afy
│  │  ├─ review.py         #     afa / afr
│  │  ├─ blacklist.py      #     ab / aby / ablock / abdeny
│  │  └─ share.py          #     snp / sna / snn
│  └─ telegram/            #   Telegram 适配：reply / upload / transit / membership / takedown
├─ services/               # 应用层：用例编排，不 import telegram
│  ├─ download_service.py  #   链接检查、权限、缓存、抓取、保存、上传
│  ├─ apply_service.py     #   申请校验、重复待审拦截、送中转频道
│  ├─ review_service.py    #   审核状态 + 名单 + 幂等回滚
│  ├─ blacklist_service.py #   下架受理 / 材料提交 / 核验
│  ├─ share_service.py     #   冷却、并发保护、频道分流、分享记录
│  └─ takedown_service.py  #   按作者删除频道历史分享
├─ policy/                 # 规则层：只回答「能不能」，不读写业务数据
│  ├─ author.py            #   黑名单 / 兽人作者名单 → 能否下载、能否申请
│  └─ admin.py             #   按中转频道成员身份判定管理员
├─ sources/                # 领域层：来源适配
│  ├─ base.py              #   Novel / Series / Author / NovelSource
│  ├─ __init__.py          #   _SOURCES 注册表 + fetch / save / resolve_link
│  ├─ format.py utils.py   #   文本排版、系列合并/分包判断
│  ├─ linpx/               #   Linpx 客户端 / 解析 / URL / 错误（唯一可用来源）
│  └─ pixiv/               #   仅 URL 工具，未接入
├─ storage/                # 存储层：全仓唯一读写 JSON 的地方
│  ├─ json_store.py        #   原子写 + mtime 热加载 + 进程锁 + prune
│  ├─ author_list.py       #   三份名单 + get_lists() 进程内单例
│  ├─ furry_request.py     #   兽人作者申请记录
│  ├─ black_request.py     #   作者下架申请记录
│  ├─ file_cache.py        #   Telegram file_id 缓存（TTL）
│  └─ share_records.py     #   分享记录 / 冷却 / message_id
├─ infra/                  # 基础设施：http / files / archive（zip）
├─ utils/                  # 通用工具：json / json_merge / links / time / timer
├─ data/                   # 运行数据 JSON（部分 gitignore）+ 导入推荐作者脚本
├─ files/novels/           # 下载临时目录（gitignore，上传后删除）
├─ scripts/                # 运维脚本：合并冲突 JSON、三端数据同步
├─ docs/                   # 01~06 设计 / 流程 / 改代码文档
└─ test/                   # pytest 用例（当前 173 passed）
```

分层依赖（单向）：

```text
handlers → services → policy / sources → storage / infra / utils
```

- `services/` 及以下**不 import telegram**，上传 / 删除 / 送审都通过参数注入。
- 只有 `storage/` 读写 JSON；只有 `infra/` 碰文件与网络。
- 新增来源：实现 `NovelSource` + 在 `sources/__init__.py` 的 `_SOURCES` 注册一行。
