from os import PathLike
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes, CallbackContext

from keyboards import check_furry_keyboard
from sources import save_novel


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	query = update.callback_query
	await query.answer()

	if not query.data:
		return

	await query.edit_message_reply_markup(reply_markup=None)

	if query.data == "ignore" or query.data == "not_furry":
		await query.delete_message()
		return

	if query.data.startswith("apply_fa"):
		link =query.data.split(";")[1]
		author_id = query.data.split(";")[2]
		# path = await down_novels(link, update)
		# await update.message.get_bot().send_document()
		
		
	if query.data.startswith("down_novel"):
		link = query.data.split(";")[1]
		# await down_novels(query, link, )
		# await upload_file()(


async def down_novels(link: str, update: Update) -> PathLike:
	path = ""
	try:
		path = await save_novel(link)
	except FileNotFoundError:
		# 容错处理：如果文件不存在，通知用户
		await update.message.reply_text("抱歉，未找到指定的文件。")
	except Exception as e:
		# 捕获其他潜在异常（如网络问题或权限问题）
		await update.message.reply_text(f"文件发送失败，错误信息: {e}")
	else:
		return Path(path)
	


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
