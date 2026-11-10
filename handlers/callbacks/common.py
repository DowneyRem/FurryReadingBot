"""callbacks 公共工具：统一回复、申请记录、中转频道。

用户申请（apply）与管理核验（review）共用的工具都放在这里，
两个业务模块只依赖本模块，互不 import。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from config import ADMIN_IDS, TRANSIT_CHANNEL
from handlers.callbacks.upload import get_cache, upload_file
from keyboards import review_author_keyboard
from sources import save
from storage.application import ApplicationStore
from storage.file_async import remove_file
from storage.file_cache import FileCacheStore
from utils.json import JsonDict
from utils.links import get_id


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


def transit_file_type(kind: str) -> str:
	"""中转频道里用哪种文件格式展示申请：单篇用 txt，系列 / 作者用 zip。"""
	return "txt" if kind == "novel" else "zip"


def transit_caption(record: JsonDict) -> str:
	"""中转频道核验消息的文案，管理员据此判断是否为兽人向作者。"""
	name = record.author_name or record.author_id
	message = [
		"兽人作者申请",
		f"作者：{name}（#a{record.author_id}）",
	]
	if record.kind:
		message.append(f"类型：{record.kind}")
	message.append(f"申请人：{record.user_name or '匿名'}（#{record.user_id or '-'}）")
	if record.link:
		message.append(f"链接：{record.link}")
	message.append(f"申请次数：{record.count or 1}")
	message.extend([
		"",
		"✅ 通过申请并加入兽人作者 / 🈲 拒绝申请",
		# "🚫 拒绝申请加入作者黑名单"
	])
	return "\n".join(message)


async def send_to_transit(
		update: Update, context: ContextTypes.DEFAULT_TYPE,
		record: JsonDict) -> bool:
	"""把申请的作品送进中转频道（暂用测试频道），返回是否发送成功。"""
	if not TRANSIT_CHANNEL:
		logger.warning("未配置中转频道，申请 %s 无法送审", record.author_id)
		return False

	caption = transit_caption(record)
	markup = review_author_keyboard(record.author_id)
	link = str(record.link or "")
	kind = str(record.kind or guess_kind(link))
	file_type = transit_file_type(kind)
	cache_key = (
		FileCacheStore.make_key(kind, get_id(link), file_type)
		if link and kind else ""
	)
	path: Path | None = None

	# 已经下载并上传过的作品直接复用 file_id，避免重新拉取
	if cache_key:
		store = get_cache()
		cached = store.get_valid(cache_key)
		if cached:
			try:
				await upload_file(
					update, context, file_id=cached.file_id,
					filename=cached.file_name or None, chat_id=TRANSIT_CHANNEL,
					reply_markup=markup, caption=caption, cache_key=cache_key)
				return True
			except Exception:
				logger.warning(
					"复用缓存 file_id 失败，改为重新下载：%s", cache_key, exc_info=True)
				store.remove(cache_key)

	if link and kind:
		try:
			path = Path(await save(link, file_type))
			await upload_file(
				update, context, path=path, chat_id=TRANSIT_CHANNEL,
				reply_markup=markup, caption=caption, cache_key=cache_key)
			return True
		except Exception:
			logger.exception("申请 %s 的作品送入中转频道失败", record.author_id)
		finally:
			# 即传即删：中转频道不需要保留本地文件
			if path is not None and path.is_file():
				await remove_file(path)
	else:
		logger.warning("申请 %s 的链接无法识别，改为发送链接供人工核验", record.author_id)

	# 下载 / 上传失败时退化为纯文本，管理员仍可通过链接人工核验
	try:
		await context.bot.send_message(
			chat_id=TRANSIT_CHANNEL, text=caption, reply_markup=markup)
		return True
	except Exception:
		logger.exception("申请 %s 的核验消息发送失败", record.author_id)
		return False


async def is_admin_of_transit(
		context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
	"""判断用户是否为中转频道管理员（ADMIN_IDS 可额外放行）。"""
	if ADMIN_IDS and user_id in ADMIN_IDS:
		return True
	if not TRANSIT_CHANNEL:
		return False
	try:
		member = await context.bot.get_chat_member(TRANSIT_CHANNEL, user_id)
	except Exception:
		logger.warning(
			"查询管理员身份失败 chat=%s user=%s", TRANSIT_CHANNEL, user_id, exc_info=True)
		return False
	return str(getattr(member, "status", "")) in {"creator", "administrator"}

