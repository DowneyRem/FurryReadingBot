BASE = "https://linpx.ink"
API_BASE = "https://api.linpx.ink"
HEADERS = {"Referer": "https://linpx.ink/"}

# linpx link
NOVEL_PATTERN = r"(?:https?://)?(?:www\.)?(?:linpx|furrynovel)\.(?:ink|xyz)/(?:pn|pixiv/novel)/(\d+)"
SERIES_PATTERN = r"(?:https?://)?(?:api\.)?(?:linpx|furrynovel)\.(?:ink|xyz)/pixiv/series/(\d+)"
AUTHOR_PATTERN = r"(https?://)?(?:www\.)?(linpx\.ink)/(pu|pixiv/user)/\d+(/cache)?"
