from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Iterable

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from sources import fetch, save


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	query = update.callback_query
	if query is None:
		return
	# await query.answer()
	await query.edit_message_reply_markup(reply_markup=None)
	
	action, separator, link = query.data.partition(";")
	if action in {"ignore", "not_furry"}:
		await query.delete_message()
		return

	if query.data.startswith("apply_fa"):
		link =query.data.split(";")[1]
		author_id = query.data.split(";")[2]
		# path = await down_novels(link, update)
		# await update.message.get_bot().send_document()
	
	jobs = {
		"dn": lambda: save(link),
		"ds": lambda: save(link),
		"dst": lambda: save(link, "txt"),
		"dsz": lambda: save(link, "zip"),
		"dz": lambda: save(link),
		"dzn": lambda: save(link),
	}
	# if action == "dsn":
	# 	await query.edit_message_text("作者作品的勾选下载尚未实现，请使用「全部下载」。")
	# 	return
	
	job = jobs.get(action)
	if job is None:
		await query.edit_message_text("暂不支持该下载操作。")
		return
	
	try:
		await query.edit_message_text("正在获取文件，请稍候……")
		path = await job()
		await upload_file(path, update, context)
		await query.edit_message_text("还请去源网站，给作者一个收藏/评论，以表支持")
		await asyncio.sleep(10)
		await query.delete_message()
	except FileNotFoundError:
		await _reply(update, context, "抱歉，未找到生成的文件")
	except NotImplementedError as e:
		await _reply(update, context, str(e))
	except Exception as e:
		await _reply(update, context, str(e))



async def _reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
	message = update.effective_message
	if message is not None:
		await message.reply_text(text)
	elif update.effective_chat is not None:
		await context.bot.send_message(chat_id=update.effective_chat.id, text=text)


async def upload_file(
	path: str | Path,
	update: Update,
	context: ContextTypes.DEFAULT_TYPE,
	*,
	chat_id: int | str | Iterable[int | str] | None = None,
	reply_markup: InlineKeyboardMarkup | None = None,
	caption: str | None = None,
	reply_to_message_id: int | None = None,
) -> str | dict[int | str, str]:
	"""发送文件到一个或多个目标聊天；目标可为私聊、群组或频道 ID。"""
	
	file_path = Path(path)
	if not file_path.is_file():
		raise FileNotFoundError(file_path)

	if chat_id is None:
		effective_chat = update.effective_chat
		if effective_chat is None:
			raise ValueError("无法确定文件发送目标，请显式传入 chat_id")
		targets: list[int | str] = [effective_chat.id]
	elif isinstance(chat_id, (str, int)):
		targets = [chat_id]
	else:
		targets = list(dict.fromkeys(chat_id))

	if not targets:
		raise ValueError("至少需要指定一个文件发送目标")

	file_ids: dict[int | str, str] = {}
	for target in targets:
		with file_path.open("rb") as document:
			sent = await context.bot.send_document(
				chat_id=target,
				document=document,
				filename=file_path.name,
				caption=caption,
				reply_markup=reply_markup,
				reply_to_message_id=(reply_to_message_id if len(targets) == 1 else None),
			)
		if sent.document is not None:
			file_ids[target] = sent.document.file_id

	# 保持单目标调用的旧返回行为；多目标时返回各目标对应的 file_id。
	if len(targets) == 1:
		return file_ids[targets[0]]
	return file_ids
