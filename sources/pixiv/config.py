BASE = "https://www.pixiv.net"
API_BASE = f"{BASE}/ajax"
REFERER = f"{BASE}/"

# Web API 只认浏览器登录态：PIXIV_COOKIE 可以是完整 Cookie 串，也可以只填 PHPSESSID 的值。
ENV_COOKIE = "PIXIV_COOKIE"
LANG = "zh"

USER_AGENT = (
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
	"(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
ACCEPT_LANGUAGE = "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7"
HEADERS = {
	"Referer": REFERER,
	"User-Agent": USER_AGENT,
	"Accept": "application/json",
	"Accept-Language": ACCEPT_LANGUAGE,
}

# 全局限流：两次请求之间的最小间隔（秒）。服务端账号比本地阅读器更容易触发风控。
MIN_INTERVAL = 0.5
DEFAULT_SERIES_LIMIT = 30

# 链接识别：只负责从文本里抓 ID，具体归一化在 source 层。
NOVEL_PATTERN = r"(?:https?://)?(?:www\.)?pixiv\.net/novel/show\.php\?id=(\d+)"
SERIES_PATTERN = r"(?:https?://)?(?:www\.)?pixiv\.net/novel/series/(\d+)"
AUTHOR_PATTERN = r"(?:https?://)?(?:www\.)?pixiv\.net/users?/(\d+)"