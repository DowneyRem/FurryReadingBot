"""管理员命令：`/sync` 抓 Linpx 推荐作者 + 把 `data/` 里的运营数据提交到私有仓库。

权限与 `/review` 一致：只认**中转频道**的 `creator` / `administrator`
（`AdminPolicy`，默认拒绝）。这样改管理员只需在 Telegram 里调频道权限。

推荐作者只在这里抓：服务器定时任务直接调 `script/sync_data.sh` 提交，
不联网，也不会碰名单。
"""

from __future__ import annotations

import html
import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.telegram import transit_admin_policy
from services import ImportAuthorResult, SyncDataService, SyncResult


logger = logging.getLogger(__name__)

# Telegram 单条消息上限 4096，给说明文字留余量
MAX_OUTPUT = 1500
# 非管理员的统一回复；与 `/review` 的措辞保持一致
DENIED = "⚠️ 仅中转频道管理员可以同步运营数据"
# 两步（抓推荐作者 + 提交）都在同一个「⏳」消息里等，先说清楚在做什么
NOTICE = "⏳ 正在抓取 Linpx 推荐作者并同步运营数据到私有仓库…"


def format_sync_result(result: SyncResult) -> str:
	"""把同步结果翻译成 Telegram HTML 文案。"""
	head = _linpx_line(result.linpx)
	if result.timed_out:
		return head + "❌ 数据同步超时，可能正有另一个同步任务在跑，请稍后再试。" + _output(result.output)
	if result.ok and result.skipped:
		return head + "✅ 没有数据变动，已跳过同步。"
	if result.ok:
		return head + "✅ 运营数据已同步到私有仓库。" + _output(result.output)
	# 脚本缺失时 returncode 是 0，别回一句「退出码 0」让人以为脚本跑过了
	detail = f"（退出码 {result.returncode}）" if result.returncode else ""
	return (
		head
		+ f"❌ 数据同步失败{detail}，可稍后重试。"
		+ _output(result.output)
	)


def _linpx_line(linpx: ImportAuthorResult | None) -> str:
	"""推荐作者合并结果的提示；自动同步（不抓取）时为空串。"""
	if linpx is None:
		return ""
	if not linpx.ok:
		return (
			f"⚠️ Linpx 推荐作者抓取失败：{html.escape(linpx.error)}。"
			"（继续提交本地已有数据）\n"
		)
	if not linpx.added:
		return f"✅ Linpx 推荐作者：共 {linpx.total} 个，没有新增。\n"
	return f"✅ Linpx 推荐作者：共 {linpx.total} 个，新增 {linpx.added} 个。\n"


def _output(text: str) -> str:
	"""把脚本输出包进 <pre>；转义 HTML 并截断超长内容。"""
	body = (text or "").strip() or "（脚本没有输出）"
	if len(body) > MAX_OUTPUT:
		body = body[:MAX_OUTPUT] + "\n…（输出过长，已截断）"
	return f"\n<pre>{html.escape(body)}</pre>"


async def sync(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""/sync：仅限管理员，先合并 Linpx 推荐作者，再把运营数据提交到私有仓库。"""
	message = update.effective_message
	user = update.effective_user
	if message is None or user is None:
		return

	decision = await transit_admin_policy(context.bot).check(user.id)
	if not decision.allowed:
		logger.warning(
			"非管理员尝试同步运营数据 user=%s status=%s", user.id, decision.status)
		await message.reply_text(DENIED)
		return

	notice = await message.reply_text(NOTICE)
	result = await SyncDataService().sync(import_author=True)
	linpx = result.linpx
	logger.info(
		"数据同步请求 user=%s ok=%s code=%s skipped=%s linpx=%s/%s",
		user.id, result.ok, result.returncode, result.skipped,
		linpx.added if linpx else "-", "ok" if (linpx and linpx.ok) else "fail",
	)

	text = format_sync_result(result)
	if notice is not None:
		try:
			await notice.edit_text(text, parse_mode="HTML")
			return
		except Exception:
			logger.warning("编辑同步结果消息失败，改为新消息", exc_info=True)
	await message.reply_text(text, parse_mode="HTML")
