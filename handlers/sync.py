"""管理员命令：`/sync` 把 `data/` 里的运营数据提交到私有仓库。

权限与 `/review` 一致：只认**中转频道**的 `creator` / `administrator`
（`AdminPolicy`，默认拒绝）。这样改管理员只需在 Telegram 里调频道权限。
"""

from __future__ import annotations

import html
import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.telegram import transit_admin_policy
from services import SyncDataService, SyncResult


logger = logging.getLogger(__name__)

# Telegram 单条消息上限 4096，给说明文字留余量
MAX_OUTPUT = 1500
# 非管理员的统一回复；与 `/review` 的措辞保持一致
DENIED = "⚠️ 仅中转频道管理员可以同步运营数据"


def format_sync_result(result: SyncResult) -> str:
	"""把同步结果翻译成 Telegram HTML 文案。"""
	if result.timed_out:
		return "❌ 数据同步超时，可能正有另一个同步任务在跑，请稍后再试。" + _output(result.output)
	if result.ok and result.skipped:
		return "✅ 没有数据变动，已跳过同步。"
	if result.ok:
		return "✅ 运营数据已同步到私有仓库。" + _output(result.output)
	return (
		f"❌ 数据同步失败（退出码 {result.returncode}），可稍后重试。"
		+ _output(result.output)
	)


def _output(text: str) -> str:
	"""把脚本输出包进 <pre>；转义 HTML 并截断超长内容。"""
	body = (text or "").strip() or "（脚本没有输出）"
	if len(body) > MAX_OUTPUT:
		body = body[:MAX_OUTPUT] + "\n…（输出过长，已截断）"
	return f"\n<pre>{html.escape(body)}</pre>"


async def sync(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""/sync：管理员把运营数据提交到私有仓库。"""
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

	notice = await message.reply_text("⏳ 正在同步运营数据到私有仓库…")
	result = await SyncDataService().sync()
	logger.info(
		"数据同步请求 user=%s ok=%s code=%s skipped=%s",
		user.id, result.ok, result.returncode, result.skipped,
	)

	text = format_sync_result(result)
	if notice is not None:
		try:
			await notice.edit_text(text, parse_mode="HTML")
			return
		except Exception:
			logger.warning("编辑同步结果消息失败，改为新消息", exc_info=True)
	await message.reply_text(text, parse_mode="HTML")
