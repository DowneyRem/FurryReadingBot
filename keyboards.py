from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from sources.linpx.urls import url_author
# todo 通用化 url_author


def apply_author_keyboard(
		author_url: str, *, show_blacklist: bool = False) -> InlineKeyboardMarkup:
	"""「申请加入兽人作者名单」菜单。

	``show_blacklist`` 只在「作者主页链接」时为 True：下架入口不能出现在
	作品 / 系列链接的菜单里（见 docs/02 第 4 节）。
	"""
	row = [
		InlineKeyboardButton(text="✅ 申请兽人作者", callback_data=f"af;{author_url}"),
	]
	if show_blacklist:
		row.append(
			InlineKeyboardButton(
				text="🈲 申请黑名单", callback_data=f"ab;{author_url}"))
	row.append(InlineKeyboardButton(text="🗑️ 取消", callback_data="ignore"))
	return InlineKeyboardMarkup([row])


def confirm_furry_keyboard(author_url: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(text="✅ 确认", callback_data=f"afy;{author_url}"),
			InlineKeyboardButton(text="↩️ 取消", callback_data=f"afn;{author_url}"),
		]]
	)


def confirm_black_keyboard(author_url: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(text="✅ 确认", callback_data=f"aby;{author_url}"),
			InlineKeyboardButton(text="↩️ 取消", callback_data=f"abn;{author_url}"),
		]]
	)


def review_author_keyboard(author_id: str | int) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[
			[
				InlineKeyboardButton(text="✅ 通过", callback_data=f"afa;{author_id}"),
				InlineKeyboardButton(text="❌ 拒绝", callback_data=f"afr;{author_id}"),
				InlineKeyboardButton(text="🏡 主页", url=url_author(author_id)),
			],
		]
	)


def blacklist_review_keyboard(author_id: str | int) -> InlineKeyboardMarkup:
	"""中转频道里「作者申请下架」的核验键盘。"""
	return InlineKeyboardMarkup(
		[
			[
				InlineKeyboardButton(text="🚫 拉黑", callback_data=f"ablock;{author_id}"),
				InlineKeyboardButton(text="❌ 拒绝", callback_data=f"abdeny;{author_id}"),
				InlineKeyboardButton(text="🏡 主页", url=url_author(author_id)),
			],
		]
	)


def down_novel_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(text="📄 下载本章 txt", callback_data=f"dn;{link}"),
			InlineKeyboardButton(text="🗑️ 取消", callback_data=f"ignore"),
		]]
	)


def down_novel_series_keyboard(link: str) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(
		[[
			InlineKeyboardButton(text="📒 下载系列 txt", callback_data=f"dst;{link}"),
			InlineKeyboardButton(text="📚 下载系列 zip", callback_data=f"dsz;{link}"),
		], [
			InlineKeyboardButton(text="📄 下载本章 txt", callback_data=f"dn;{link}"),
			InlineKeyboardButton(text="🗑️ 取消", callback_data=f"ignore"),
		]]
	)


def down_series_keyboard(link: str, auto: bool = True) -> InlineKeyboardMarkup:
	buttons = []
	if auto:
		buttons.append(InlineKeyboardButton(text="🤖 自动选择", callback_data=f"ds;{link}"))
	buttons.append(InlineKeyboardButton(text="📒 下载系列 txt", callback_data=f"dst;{link}"))
	buttons.append(InlineKeyboardButton(text="📚 下载系列 zip", callback_data=f"dsz;{link}"))
	return InlineKeyboardMarkup([buttons])


def down_author_keyboard(author_url: str, is_furry: bool=True) -> InlineKeyboardMarkup:
	buttons = []
	if is_furry:
		buttons.append(InlineKeyboardButton(text="👤 全部下载", callback_data=f"dan;{author_url}"))
	else:
		buttons.append(InlineKeyboardButton(text="✅ 申请兽人作者", callback_data=f"af;{author_url}"))
	buttons.append(InlineKeyboardButton(text="🈲 申请黑名单", callback_data=f"ab;{author_url}"))
	buttons.append(InlineKeyboardButton(text="🗑️ 取消", callback_data=f"ignore"))
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
