from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def apply_furry_keyboard(link: str, author_id: str | int) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(
				text="✅ 申请兽人作者",
				callback_data=f"af;{link};{author_id}"),
			InlineKeyboardButton(
				text="🗑 忽略",
				callback_data=f"ignore"),
		]]
	)

def check_furry_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(
				text="✅ 确认为兽人小说",
				callback_data=f"is_furry;{link}"),
			InlineKeyboardButton(
				text="🗑 确认非兽人小说",
				callback_data=f"not_furry"),
		]]
	)


def down_novel_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(
				text="📄 下载本章 txt",
				callback_data=f"dn;{link}"),
			# InlineKeyboardButton(
			# 	text="👤 下载作者 zip",
			# 	callback_data=f"da;{link}"),
		]]
	)

def down_novel_series_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(
				text="📄 下载本章 txt",
				callback_data=f"dn;{link}"),
		# 	InlineKeyboardButton(
		# 		text="👤 下载作者 zip",
		# 		callback_data=f"da;{link}"),
		# ], [
			InlineKeyboardButton(
				text="📒 下载系列 txt",
				callback_data=f"dst;{link}"),
			InlineKeyboardButton(
				text="📚 下载系列 zip",
				callback_data=f"dsz;{link}"),
		]]
	)

def down_series_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(
				text="🤖 自动选择",
				callback_data=f"ds;{link}"),
			InlineKeyboardButton(
				text="📒 下载系列 txt",
				callback_data=f"dst;{link}"),
			InlineKeyboardButton(
				text="📚 下载系列 zip",
				callback_data=f"dsz;{link}"),
		]]
	)


def down_author_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(
				text="👤 全部下载",
				callback_data=f"dan;{link}"),
			# InlineKeyboardButton(
			# 	text="✅ 选择下载(未完成)",
			# 	callback_data=f"das;{link}"),
		]]
	)

def import_to_legado_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(
				text="⬇️ 下载开源阅读",
				url="https://pixivsource.pages.dev/Download"),
			InlineKeyboardButton(
				text="🚀 导入 Pixiv 书源",
				url="https://pixivsource.pages.dev/Import?src=https://cdn.jsdelivr.net/gh/DowneyRem/PixivSource@main/pixiv.json"),
		], [
			InlineKeyboardButton(
				text="🚀 导入 Linpx 书源",
				url="https://pixivsource.pages.dev/Import?src=https://cdn.jsdelivr.net/gh/DowneyRem/PixivSource@main/linpx.json"),
			InlineKeyboardButton(
				text="➕ 添加本文至书架",
				url=f"https://pixivsource.pages.dev/Import?src=legado://import/addToBookshelf?src={link}"),
		]]
	)