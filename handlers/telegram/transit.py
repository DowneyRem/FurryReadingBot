"""Telegram 中转频道适配器。"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import TRANSIT_CHANNEL
from keyboards import review_author_keyboard
from utils.json import JsonDict


logger = logging.getLogger(__name__)


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
	"""把申请的作品送进中转频道，返回是否发送成功。"""
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
