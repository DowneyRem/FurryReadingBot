from telegram import Update
from telegram.ext import ContextTypes


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if not query.data:
        return

    await query.edit_message_reply_markup(reply_markup=None)

    if query.data == "ignore":
        await query.delete_message()
        return

    if query.data.startswith("apply_furry_author:"):
        author_id = query.data.split(":", 1)[1]
        await query.message.reply_text(f"已向 Bot 管理提出申请：作者 ID {author_id}")
        # 后续申请流程写在这里