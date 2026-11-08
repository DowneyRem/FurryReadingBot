import re
from html import unescape

from sources.base import Novel


def format_caption(text: str) -> str:
	if not text:
		return ""
	
	text = text.replace("<br>", "\n").replace("<br />", "\n")
	text = text.replace("<strong>", "").replace("</strong>", "")
	text = unescape(text)
	
	# 优化 Pixiv 内部链接转换（使用正则表达式捕获组 + 替换函数）
	pixiv_pattern = r'<a href="pixiv://(illusts|novels|users)/([0-9]{5,})">(?:illust|novel|user)/[0-9]{5,}</a>'
	
	def replace_pixiv_link(match):
		link_type, id_str = match.groups()
		if link_type == "illusts":
			return f"https://www.pixiv.net/artworks/{id_str}"
		elif link_type == "novels":
			return f"https://www.pixiv.net/novel/show.php?id={id_str}"
		elif link_type == "users":
			return f"https://www.pixiv.net/users/{id_str}"
		return match.group(0)  # 兜底：未匹配到则保持原样
	
	text = re.sub(pixiv_pattern, replace_pixiv_link, text)
	
	# 优化通用外链转换（更精确的正则，避免贪婪匹配过长）
	# 匹配带 target="_blank" 的 a 标签，并直接提取 href 中的 URL
	general_pattern = r'<a href="(https?://[^"]+)"[^>]*target=["\']_blank["\'][^>]*>.*?</a>'
	
	def replace_general_link(match):
		return match.group(1)
	
	text = re.sub(general_pattern, replace_general_link, text)
	return text


def format_novel_text(novel: Novel) -> str:
	"""生成写入文件的完整文本（头部信息 + 正文）。"""
	head_lines = [
		novel.title,
		f"作者：{novel.author_name}",
		f"链接：{novel.url}",
	]
	if novel.tags:
		tags = " ".join(f"#{t}" for t in novel.tags) if novel.tags else ""
		head_lines.append(f"标签：{tags}")
	if novel.caption:
		head_lines.append(f"简介：{novel.caption}")
	# if novel.series_title:
	# 	head_lines.append(f"系列：{novel.series_title}")
	head = "\n".join(head_lines)
	return f"{head}\n\n\n{novel.content}"


def format_chapter_title(chapter_title: str, series_title: str, index: int) -> str:
	"""生成章节标题：去掉与系列名重复的部分，并补上「第N章」。"""
	title = (chapter_title or "").strip()
	series = (series_title or "").strip()
	if series:
		replaced = title.replace(series, "").replace("-", "").strip()
		if len(replaced) >= 2:
			title = replaced
	if "第" not in title and "章" not in title:
		title = f"第{index}章 {title}"
	return title


def format_series_text(series, novels: list[Novel]) -> str:
	"""系列元信息 + 各章正文 → 完整 txt 字符串。"""
	head_lines = [
		series.title,
		f"作者：{series.author_name}",
		# f"链接：{series.url}",
		f"链接：{series.novel_url}",
	]
	if series.tags:
		tags = " ".join(f"#{t}" for t in series.tags) if series.tags else ""
		head_lines.append(f"标签：{tags}")
	if series.caption:
		head_lines.append(f"简介：{series.caption}")

	content = []
	for i, novel in enumerate(novels, start=1):
		title = novel.title
		# 可选：统一章节名
		# title = format_chapter_title(novel.title, series.title, i)
		content.append(title)
		content.append(novel.caption)
		content.extend(["", ""])
		content.append(novel.content)
		content.extend(["", "", ""])
	head = "\n".join(head_lines)
	contents = "\n".join(content)
	return f"{head}\n\n\n{contents}"
