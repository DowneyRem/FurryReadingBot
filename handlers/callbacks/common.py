"""callbacks 公共工具：统一回复、申请记录、中转频道。

用户申请（apply）与管理核验（review）共用的工具都放在这里，
两个业务模块只依赖本模块，互不 import。
"""

from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import TRANSIT_CHANNEL
from keyboards import review_author_keyboard
from storage.application import ApplicationStore
from utils.json import JsonDict


logger = logging.getLogger(__name__)
_applications: ApplicationStore | None = None


async def reply(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		text: str, *, delete_after: float=3, **kwargs) -> None:
	"""统一回复；delete_after 秒后自动删除提示消息。"""
	
	if update.effective_message:
		message = await update.effective_message.reply_text(text, **kwargs)
	elif update.effective_chat:
		message = await context.bot.send_message(
			chat_id=update.effective_chat.id, text=text, **kwargs)
	else:
		message = None
		
	if message and delete_after:
		await asyncio.sleep(delete_after)
		await message.delete()


def get_applications() -> ApplicationStore:
	"""申请记录是进程级单例，申请与核验共用同一份数据。"""
	global _applications
	if _applications is None:
		_applications = ApplicationStore()
	return _applications


def guess_kind(link: str) -> str:
	"""从链接猜申请对象类型，用于申请记录与中转文件格式。"""
	if "/series/" in link:
		return "series"
	if "/novel/" in link or "/pn/" in link:
		return "novel"
	if "/user/" in link or "/pu/" in link:
		return "author"
	return ""


def transit_author_caption(record: JsonDict) -> str:
	"""中转频道核验消息的文案，管理员据此判断是否为兽人向作者。"""
	message = [
		f"#兽人作者申请",
		f"👤 作者名称：{record.author_name}（#a{record.author_id}）",
		f"🏡 主页链接：{record.link}",
		f"🈸 申请用户：{record.user_name}（#u{record.user_id}）",
		f"🔢 申请次数：{record.count or 1}",
		# "",
        # f"✅ 通过申请 ❌ 拒绝申请",
		# f"🈲 拒绝申请并加入作者黑名单",
		]
	return "\n".join(message)


async def send_to_transit(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		record: JsonDict) -> bool:
	"""把申请的作品送进中转频道（暂用测试频道），返回是否发送成功。"""
	if not TRANSIT_CHANNEL:
		logger.warning("未配置中转频道，申请 %s 无法送审", record.author_id)
		return False

	try:
		await context.bot.send_message(
			chat_id=TRANSIT_CHANNEL,
			text=transit_author_caption(record),
			disable_web_page_preview=True,
			reply_markup=review_author_keyboard(record.author_id)
		)
		return True
	except Exception:
		logger.exception("申请 %s 的核验消息发送失败", record.author_id)
		return False

