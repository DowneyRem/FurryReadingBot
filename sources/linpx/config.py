from sources.utils import IdRule

BASE = "https://linpx.ink"
API_BASE = "https://api.linpx.ink"
HEADERS = {"Referer": "https://linpx.ink/"}

# linpx link
NOVEL_PATTERN = r"(?:https?://)?(?:www\.)?(?:linpx|furrynovel)\.(?:ink|xyz)/(?:pn|pixiv/novel)/(\d+)"
SERIES_PATTERN = r"(?:https?://)?(?:api\.)?(?:linpx|furrynovel)\.(?:ink|xyz)/pixiv/series/(\d+)"
AUTHOR_PATTERN = r"(?:https?://)?(?:www\.)?(?:linpx\.ink)/(?:pu|pixiv/user)/(\d+)(?:/cache)?"

# 提取规则：pattern 负责抓 ID，label 用于解析失败的提示文案。
NOVEL = IdRule(NOVEL_PATTERN, "小说")
SERIES = IdRule(SERIES_PATTERN, "系列")
AUTHOR = IdRule(AUTHOR_PATTERN, "作者")
