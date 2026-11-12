from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from keyboards import apply_author_keyboard, down_author_keyboard
from policy.author import AuthorPolicy
from sources import Author, fetch


def _link_from_data(data: str) -> str:
	parts = data.split(";", 1)
	return parts[1].strip() if len(parts) > 1 else ""


async def back_to_author(update: Update, context: ContextTypes.DEFAULT_TYPE,
	*, data: str) -> None:
	"""ba：下载键盘的「👤 查看作者」与确认页的「↩️ 返回」共用。

	按名单决定回哪一页：兽人作者回作者页，未收录回申请页，
	黑名单只给结论（不给任何入口）。只有要展示作者页时才抓作者，
	Novel / Series 本身就带 author_id / author_name / author_url。
	"""
	link = _link_from_data(data)
	item = await fetch(link)
	decision = AuthorPolicy().check(item.author_id, item.author_name)

	if decision.is_furry:
		author = item if isinstance(item, Author) else await fetch(item.author_url)
		text = str(author)
		markup = down_author_keyboard(item.author_url, is_furry=True)

	elif decision.is_blacklisted:
		text = "\n".join([
			f"作者 {item.author_name}（#a{item.author_id}）已停止通过本 Bot 下载与分享",
			"",
			"如需下载其他 Pixiv 小说，可以使用 @PixivNBot",
		])
		markup = None

	else:
		text = "\n".join([
			"不好意思，本 Bot 仅可下载、分享兽人小说。",
			f"作者：{item.author_name}（#a{item.author_id}）目前不在兽人作者名单", "",
			"申请其为兽人小说作者？",
			"如需下载其他 Pixiv 小说，可以使用 @PixivNBot",
		])
		markup = apply_author_keyboard(item.author_url)

	await update.callback_query.edit_message_text(text=text, reply_markup=markup)
