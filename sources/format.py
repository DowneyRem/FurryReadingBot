from __future__ import annotations

import re
from html import unescape
from collections.abc import Iterable
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from sources.base import Novel


# Pixiv 正文标记：content 是纯文本，但用方括号表达分页 / 章节 / 注音 / 外链 / 图片 / 粗斜体。
# 这些标记不是正文，写进 txt 前要换成可读文本；Linpx 的 content 已经是干净文本，不要走这里。
_PIXIV_JUMPURI_RE = re.compile(r"\[\[jumpuri:\s*(.*?)\s*>\s*(\S+?)\s*\]\]")
_PIXIV_RUBY_RE = re.compile(r"\[\[rb:\s*([^\]>]+?)\s*>\s*([^\]]+?)\s*\]\]")
_PIXIV_EMPHASIS_RE = re.compile(r"\[\[emphasismark:\s*([^\]]*?)\s*>\s*[^\]]*?\]\]")
_PIXIV_CHAPTER_RE = re.compile(r"\[chapter:\s*([^\]]*?)\s*\]")
_PIXIV_NEWPAGE_RE = re.compile(r"\[newpage\]")
_PIXIV_IMAGE_RE = re.compile(r"\[pixivimage:(\d+)\]")
_PIXIV_UPLOAD_RE = re.compile(r"\[uploadedimage:(\d+)\]")
_PIXIV_BOLD_RE = re.compile(r"\[b:([^\]]*?)\]")
_PIXIV_ITALIC_RE = re.compile(r"\[i:([^\]]*?)\]")
_PIXIV_JUMP_RE = re.compile(r"\[jump:(\d+)\]")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


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
		f"链接：{novel.novel_url}",
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


def format_tags(tags: Iterable[str]) -> str:
	"""标签列表 → "#甲 #乙"；空元素/空白自动忽略，无标签返回空串。"""
	return " ".join(f"#{tag.strip()}" for tag in tags if tag and tag.strip())


def format_series_text(series, novels: list[Novel]) -> str:
	"""系列元信息 + 各章正文 → 完整 txt 字符串。"""
	head_lines = [
		series.title,
		f"作者：{series.author_name}",
		# f"链接：{series.series_url}",
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


def format_pixiv_content(
	text: str,
	embedded_images: dict[str, str] | None = None,
) -> str:
	"""Pixiv 正文 → 可读纯文本。

	`[newpage]` 分页、`[chapter: 标题]` 章节、`[[rb:汉字 > 假名]]` 注音、
	`[[jumpuri: 文本 > URL]]` 外链、`[pixivimage:]` / `[uploadedimage:]` 图片、
	`[b:]` / `[i:]` / `[[emphasismark:]]` 粗体 / 斜体 / 着重号。
	`embedded_images` 是 `textEmbeddedImages` 解析出的 `{图片ID: 原图URL}`，
	用于把 `[uploadedimage:ID]` 换成真实图片地址。
	"""
	if not text:
		return ""

	def jump_uri(match: re.Match[str]) -> str:
		label, url = match.group(1).strip(), match.group(2).strip()
		return url if not label or label == url else f"{label} ({url})"

	def chapter(match: re.Match[str]) -> str:
		title = match.group(1).strip()
		return f"\n\n{title}\n\n" if title else "\n\n"

	def uploaded_image(match: re.Match[str]) -> str:
		url = (embedded_images or {}).get(match.group(1))
		return f"[图片 {url}]" if url else "[图片]"

	text = text.replace("\r\n", "\n").replace("\r", "\n")
	# 双括号标记先处理，避免内部的 `[b:]` 之类被后续规则拆开
	text = _PIXIV_JUMPURI_RE.sub(jump_uri, text)
	text = _PIXIV_RUBY_RE.sub(lambda m: f"{m.group(1)}({m.group(2)})", text)
	text = _PIXIV_EMPHASIS_RE.sub(lambda m: m.group(1), text)
	text = _PIXIV_CHAPTER_RE.sub(chapter, text)
	text = _PIXIV_NEWPAGE_RE.sub("\n\n", text)
	text = _PIXIV_IMAGE_RE.sub(
		lambda m: f"[插画 https://www.pixiv.net/artworks/{m.group(1)}]", text)
	text = _PIXIV_UPLOAD_RE.sub(uploaded_image, text)
	text = _PIXIV_BOLD_RE.sub(lambda m: m.group(1), text)
	text = _PIXIV_ITALIC_RE.sub(lambda m: m.group(1), text)
	text = _PIXIV_JUMP_RE.sub(lambda m: f"(见第 {m.group(1)} 页)", text)
	return _BLANK_LINES_RE.sub("\n\n", text).strip()
