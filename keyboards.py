from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from sources.linpx.urls import url_author
# todo 通用化 url_author


def apply_author_keyboard(author_url: str, ) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(text="✅ 申请", callback_data=f"af;{author_url}"),
			InlineKeyboardButton(text="🗑️ 取消", callback_data=f"ignore"),
		]]
	)


def confirm_author_keyboard(author_url: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(text="✅ 确认", callback_data=f"afy;{author_url}"),
			InlineKeyboardButton(text="🗑️ 取消", callback_data="ignore"),
		]]
	)


def review_author_keyboard(author_id: str | int) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[
			[
				InlineKeyboardButton(text="✅ 通过", callback_data=f"afa;{author_id}"),
				InlineKeyboardButton(text="🈲 拒绝", callback_data=f"afr;{author_id}"),
			# ], [
			# 	InlineKeyboardButton(text="🚫 拉黑", callback_data=f"afb;{author_id}"),
				InlineKeyboardButton(text="🏡 主页", url=url_author(author_id)),
			],
		]
	)


def down_novel_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(text="📄 下载本章 txt", callback_data=f"dn;{link}"),
			# InlineKeyboardButton(text="👤 下载作者 zip", callback_data=f"da;{link}"),
		]]
	)


def down_novel_series_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(text="📄 下载本章 txt", callback_data=f"dn;{link}"),
			# InlineKeyboardButton(text="👤 下载作者 zip", callback_data=f"da;{link}"),
		# ], [
			InlineKeyboardButton(text="📒 下载系列 txt", callback_data=f"dst;{link}"),
			InlineKeyboardButton(text="📚 下载系列 zip", callback_data=f"dsz;{link}"),
		]]
	)


def down_series_keyboard(link: str, auto: bool = True) -> InlineKeyboardMarkup:
	buttons = []
	if auto:
		buttons.append(InlineKeyboardButton(text="🤖 自动选择", callback_data=f"ds;{link}"))
	buttons.append(InlineKeyboardButton(text="📒 下载系列 txt", callback_data=f"dst;{link}"))
	buttons.append(InlineKeyboardButton(text="📚 下载系列 zip", callback_data=f"dsz;{link}"))
	return InlineKeyboardMarkup([buttons])


def down_author_keyboard(link: str, is_furry: bool=True) -> InlineKeyboardMarkup:
	from utils.links import get_id
	buttons = []
	if is_furry:
		buttons.append(InlineKeyboardButton(text="👤 全部下载", callback_data=f"dan;{link}"))
	else:
		buttons.append(InlineKeyboardButton(text="✅ 申请兽人作者", callback_data=f"af;{link};{get_id(link)}"))
	# buttons.append(InlineKeyboardButton(text="🈲 申请黑名单", callback_data=f"af;{link};{get_id(link)}"))
	return InlineKeyboardMarkup([buttons])


def share_novel_keyboard(kind: str, item_id: str, file_type: str = "txt") -> InlineKeyboardMarkup:
	payload = f"{kind};{item_id};{file_type}"
	if file_type != "txt":
		return InlineKeyboardMarkup([[]])
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(text="🉑 公开分享", callback_data=f"snp;{payload}"),
			InlineKeyboardButton(text="㊙️ 私密分享", callback_data=f"sna;{payload}"),
			InlineKeyboardButton(text="🈲 拒绝分享", callback_data=f"snn;{payload}"),
		]]
	)


def check_novel_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(text="🉑 允许分享", callback_data=f"csna;{link}"),
			InlineKeyboardButton(text="🈲 禁止分享", callback_data=f"csnf;{link}"),
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