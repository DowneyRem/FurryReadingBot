"""下载类 callback：dn / ds / dst / dsz / dan（Telegram 展示层）。"""

from __future__ import annotations

import asyncio

from telegram import Update
from telegram.ext import ContextTypes

from handlers.telegram import reply, upload_file
from keyboards import down_series_keyboard, share_novel_keyboard
from services import (
	DownloadArtifact,
	DownloadService,
	DownloadInvalidLinkError,
	DownloadUnsupportedActionError,
)


async def choose_series_format(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		*, link: str) -> None:
	"""series 的 txt 与 zip 缓存同时存在时，编辑当前按钮让用户做选择。"""
	text = "该系列已有 txt 与 zip 缓存，请选择要下载的格式"
	markup = down_series_keyboard(link, auto=False)
	query = update.callback_query
	if query:
		await query.edit_message_text(text, reply_markup=markup)
	else:
		await reply(update, context, text, reply_markup=markup, delete_after=0)


async def download(
	update: Update, context: ContextTypes.DEFAULT_TYPE,
	*, data: str,) -> None:

	query = update.callback_query
	action, _, link = data.partition(";")

	service = DownloadService()
	if not service.supports_action(action):
		await reply(update, context, "暂不支持该下载操作。")
		return

	if query:
		await query.edit_message_text("正在获取文件，请稍候……")

	async def send(artifact: DownloadArtifact) -> None:
		"""把 service 的产物交给 Telegram 上传适配器。"""
		await upload_file(
			update, context,
			path=artifact.path,
			file_id=artifact.file_id,
			filename=artifact.filename,
			reply_markup=share_novel_keyboard(
				artifact.kind, artifact.item_id, artifact.file_type),
			caption=artifact.caption,
			cache_key=artifact.cache_key,
			author_id=artifact.author_id,
			author_name=artifact.author_name,
			cleanup=False,
		)

	try:
		outcome = await service.deliver(action, link, upload=send)
	except DownloadInvalidLinkError:
		await reply(update, context, "请发送一个有效的小说、系列或作者链接。")
		return
	except DownloadUnsupportedActionError:
		await reply(update, context, "暂不支持该下载操作。")
		return

	if outcome.format_choice_link:
		await choose_series_format(
			update, context, link=outcome.format_choice_link)
		return

	if query:
		await query.edit_message_text("还请去源网站，给作者一个收藏/评论，以表支持")
		try:
			await asyncio.sleep(2)
			await query.delete_message()
		except Exception:
			pass
