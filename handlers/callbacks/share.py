"""分享类 callback：snp / sna / snn（Telegram 展示层）。"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from config import FURRY_READING
from handlers.callbacks.common import reply
from handlers.callbacks.upload import upload_file
from services import ShareRequest, ShareService


def format_remaining(seconds: float) -> str:
	"""把剩余冷却秒数格式化为「x 天 y 小时」/「x 小时 y 分钟」。"""
	minutes = int(seconds // 60) + (1 if seconds % 60 else 0)
	days, minutes = divmod(minutes, 24 * 60)
	hours, minutes = divmod(minutes, 60)
	if days:
		return f"{days} 天 {hours} 小时" if hours else f"{days} 天"
	if hours:
		return f"{hours} 小时 {minutes} 分钟" if minutes else f"{hours} 小时"
	return f"{max(minutes, 1)} 分钟"


async def share(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str, public: bool) -> bool:
	"""把缓存中的文件分享到目标频道：成功返回 True，失败返回 False。"""
	parts = data.split(";")
	# data 如 "snp;{kind};{item_id};{file_type}"
	if len(parts) < 3:
		await reply(update, context, "分享参数不完整")
		return False

	kind, item_id = parts[1], parts[2]
	file_type = parts[3] if len(parts) > 3 else "txt"
	query = update.callback_query
	user = query.from_user if query else None
	request = ShareRequest(
		kind=kind,
		item_id=item_id,
		file_type=file_type,
		public=public,
		user_id=user.id if user else None,
		user_name=(user.first_name or "") if user else "",
	)

	async def send(artifact) -> None:
		await upload_file(
			update, context,
			file_id=artifact.file_id,
			filename=artifact.filename,
			chat_id=artifact.channels,
			caption=artifact.caption,
			cache_key=artifact.cache_key,
		)

	result = await ShareService().share(request, upload=send)
	if result.status == "inflight":
		await reply(update, context, "该作品正在分享中，请稍候再试")
		return False
	if result.status == "cooldown":
		await reply(
			update, context,
			f"该作品刚刚已经分享过，{format_remaining(result.remaining_seconds)}后可再次分享")
		return False
	if result.status == "cache_missing":
		await reply(update, context, "缓存已失效，请重新下载后再分享")
		return False
	if result.status == "no_channel":
		await reply(update, context, "未配置分享频道")
		return False
	return True


async def share_public(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	if await share(update, context, data=data, public=True):
		await reply(update, context, f"已经公开分享至 {FURRY_READING}")


async def share_private(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, data: str) -> None:
	if await share(update, context, data=data, public=False):
		await reply(update, context, f"已经匿名分享至 {FURRY_READING}")


async def share_reject(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		**kwargs) -> None:
	query = update.callback_query
	if query is not None:
		await query.edit_message_reply_markup(reply_markup=None)
