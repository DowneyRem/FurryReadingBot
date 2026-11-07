from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

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
		
		await query.message.reply_text(f"已向 Bot 管理提出申请：作者 ID {author_id}")
		
	if query.data.startswith("down_novel"):
		link = query.data.split(";")[1]
		
		try:
			path = await save_novel(link)
			with open(path, "rb") as file_object:
				message = await update.message.reply_document(
					document=file_object,
					filename=Path(path).name,
					caption="这是为您准备的文件！",
					# reply_to_message_id=update.message.message_id
				)

			file_id = message.document.file_id
			await message.reply_text(file_id)
			# todo：存储file id 避免重复上传

		except FileNotFoundError:
			# 容错处理：如果文件不存在，通知用户
			await update.message.reply_text("抱歉，未找到指定的文件。")
		except Exception as e:
			# 捕获其他潜在异常（如网络问题或权限问题）
			await update.message.reply_text(f"文件发送失败，错误信息: {e}")
