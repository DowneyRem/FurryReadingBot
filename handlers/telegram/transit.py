"""Telegram 中转频道适配器。"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import TRANSIT_CHANNEL
from keyboards import review_black_keyboard, review_furry_keyboard
from utils.json import JsonDict


logger = logging.getLogger(__name__)


def transit_author_caption(record: JsonDict) -> str:
	"""中转频道核验消息的文案，管理员据此判断是否为兽人向作者。"""
	message = [
		f"#兽人作者申请",
		f"👤 作者名称：{record.author_name}（#a{record.author_id}）",
		f"🏡 主页链接：{record.link}",
		f"🈸 申请用户：{record.user_name}（#u{record.user_id}）",
		f"🔢 申请次数：{record.count or 1}", "",
		f"请确认其是否为兽人作者",
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
			reply_markup=review_furry_keyboard(record.author_id)
		)
		return True
	except Exception:
		logger.exception("申请 %s 的核验消息发送失败", record.author_id)
		return False


def blacklist_caption(record: JsonDict) -> str:
	"""作者下架申请的核验卡片文案。"""
	message = [
		"#作者申请下架",
		f"👤 作者：{record.author_name}（#a{record.author_id}）",
		f"🏡 主页：{record.author_url}",
		f"🈸 申请人：{record.user_name}（#u{record.user_id}）",
		f"🔢 申请次数：{record.count or 1}", "",
		"请确认截图确实是该作者的账号，再决定是否拉黑",
	]
	return "\n".join(message)


async def send_blacklist_card(
		context: ContextTypes.DEFAULT_TYPE, record: JsonDict) -> bool:
	"""把作者下架申请（含截图）送进中转频道。"""
	if not TRANSIT_CHANNEL:
		logger.warning("未配置中转频道，下架申请 %s 无法送审", record.author_id)
		return False
	if not record.photo_file_id:
		logger.warning("下架申请 %s 没有截图", record.author_id)
		return False

	try:
		await context.bot.send_photo(
			chat_id=TRANSIT_CHANNEL,
			photo=record.photo_file_id,
			caption=blacklist_caption(record)[:1024],
			reply_markup=review_black_keyboard(record.author_id),
		)
		return True
	except Exception:
		logger.exception("下架申请 %s 的核验卡片发送失败", record.author_id)
		return False
