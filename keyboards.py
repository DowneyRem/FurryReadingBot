from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def apply_furry_author_keyboard(link: str, author_id: str | int) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(
				text="✅ 申请兽人作者",
				callback_data=f"af;{link};{author_id}"),
			InlineKeyboardButton(
				text="🗑️ 忽略",
				callback_data=f"ignore"),
		]]
	)

def check_furry_author_keyboard(link: str, author_id: str | int) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(
				text="✅ 确认为兽人作者",
				callback_data=f"ifa;{link};{author_id}"),
			InlineKeyboardButton(
				text="❌ 确认非兽人作者",
				callback_data=f"nfa"),
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

def share_novel_keyboard(
		kind: str, item_id: str, file_type: str = "txt") -> InlineKeyboardMarkup:
	payload = f"{kind};{item_id};{file_type}"
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(
				text="🉑 公开分享",
				callback_data=f"snp;{payload}"),
			InlineKeyboardButton(
				text="㊙️ 私密分享",
				callback_data=f"sna;{payload}"),
			InlineKeyboardButton(
				text="🈲 拒绝分享",
				callback_data=f"snn;{payload}"),
		]]
	)

def check_novel_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(
				text="🉑 允许分享",
				callback_data=f"csna;{link}"),
			InlineKeyboardButton(
				text="🈲 禁止分享",
				callback_data=f"csnf;{link}"),
		]]
	)

def import_to_legado_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(
				text="⬇️ 下载 开源阅读",
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