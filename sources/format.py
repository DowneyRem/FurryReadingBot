import re
from html import unescape


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