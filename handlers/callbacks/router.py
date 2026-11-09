"""Callback 路由：只负责分发，不实现具体业务。"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from handlers.callbacks._common import reply
# from handlers.callbacks.apply import handle_apply_furry, handle_confirm_furry
from handlers.callbacks.download import download
from handlers.callbacks.share import share_private, share_public, share_reject


logger = logging.getLogger(__name__)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	query = update.callback_query
	if query is None or not query.data:
		return

	await query.answer()
	try:
		await query.edit_message_reply_markup(reply_markup=None)
	except Exception:
		pass

	data = query.data
	action, _, rest = data.partition(";")

	if action in {"ignore", "not_furry", "nfa"}:
		try:
			await query.delete_message()
		except Exception:
			pass
		return

	handlers = {
		# 下载
		"dn": download,
		"ds": download,
		"dst": download,
		"dsz": download,
		"dan": download,
		# # 申请 / 审核
		# "af": handle_apply_furry,
		# "ifa": handle_confirm_furry,
		# 分享
		"snp": share_public,
		"sna": share_private,
		"snn": share_reject,
	}

	handler = handlers.get(action)
	if handler is None:
		await reply(update, context, "暂不支持该操作。")
		return

	try:
		await handler(update, context, action=action, rest=rest, data=data)
	except FileNotFoundError:
		await reply(update, context, "抱歉，未找到生成的文件")
	except NotImplementedError as e:
		await reply(update, context, str(e))
	except Exception as e:
		logger.exception("callback 失败 action=%s", action)
		await reply(update, context, f"处理失败：{e}")
