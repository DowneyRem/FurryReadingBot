"""Callback 路由：只负责分发，不实现具体业务。"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.telegram import reply
from handlers.callbacks.apply import apply_furry, apply_furry_confirm
from handlers.callbacks.blacklist import (
	blacklist_approve,
	blacklist_reject,
	request_blacklist,
	request_blacklist_confirm,
)
from handlers.callbacks.review import apply_approve, apply_reject
from handlers.callbacks.download import download
from handlers.callbacks.share import share_private, share_public, share_reject
from handlers.callbacks.author import see_author


logger = logging.getLogger(__name__)

# 只删消息、不进业务的 action
CANCEL_ACTIONS = {
	"ignore",
	"afn",
	"abn",
}

# action -> handler：keyboards.py 产出的 action 必须在这里或 CANCEL_ACTIONS 中
HANDLERS = {
	# 下载
	"dn": download,
	"ds": download,
	"dst": download,
	"dsz": download,
	"dan": download,
	# 查看作者，sa -> dan;
	"sa": see_author,
	"ba": back_author,
	# 申请兽人作者：af 告知后果，afy 确认提交
	"af": apply_furry,
	"afy": apply_furry_confirm,
	# 作者申请下架：ab 告知后果，aby 受理并回材料清单
	"ab": request_blacklist,
	"aby": request_blacklist_confirm,
	# 中转频道核验兽人作者申请：rfy 通过，rfn 拒绝
	"rfy": apply_approve,
	"rfn": apply_reject,
	# 中转频道核验作者下架申请：rby 拉黑，rbn 拒绝
	"rby": blacklist_approve,
	"rbn": blacklist_reject,
	# 分享
	"snp": share_public,
	"sna": share_private,
	"snn": share_reject,
}


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	query = update.callback_query
	if query is None or not query.data:
		return

	await query.answer()
	# try:
	# 	await query.edit_message_reply_markup(reply_markup=None)
	# except Exception:
	# 	pass

	data = query.data
	action, _, rest = data.partition(";")

	if action in CANCEL_ACTIONS:
		try:
			await query.delete_message()
		except Exception:
			pass
		return

	handler = HANDLERS.get(action)
	if handler is None:
		await reply(update, context, "暂不支持该操作。")
		return

	try:
		await handler(update, context, data=data)
	except FileNotFoundError:
		await reply(update, context, "抱歉，未找到生成的文件")
	except NotImplementedError as e:
		await reply(update, context, str(e))
	except Exception as e:
		logger.exception("callback 失败 action=%s", action)
		await reply(update, context, f"处理失败：{e}")
