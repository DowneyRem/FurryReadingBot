from sources.utils import IdRule

BASE = "https://www.pixiv.net"
API_BASE = f"{BASE}/ajax"
REFERER = f"{BASE}/"

# Web API 只认浏览器登录态：PIXIV_COOKIE 支持单个，或用换行 / "||" 分隔多个（完整 Cookie 串或裸 PHPSESSID）。
ENV_COOKIE = "PIXIV_COOKIE"
COOKIE_SEPARATOR = "||"
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

# 单账号限流：同一账号两次请求之间的最小间隔（秒）。服务端账号比本地阅读器更容易触发风控。
MIN_INTERVAL = 0.5
# 单 IP 全局最小间隔（秒）：多账号轮换下限制同出口 IP 的总速率，避免多号并发打爆边缘限流。
GLOBAL_MIN_INTERVAL = 0.3
# 请求随机抖动上限（秒）：每次调度附加 0 ~ REQUEST_JITTER 的随机延迟，打散机械请求特征。
REQUEST_JITTER = 0.2
# 单账号连续请求多少次后轮换到下一个账号（避免短时间同时惊动所有账号）。
MAX_REQUESTS_PER_ACCOUNT = 100
# 单账号触发 429 限流后的默认冷却时间（秒）：15 分钟后自动恢复可用。
RATE_LIMIT_COOLDOWN = 900

# 链接识别：只负责从文本里抓 ID，具体归一化在 source 层。
NOVEL_PATTERN = r"(?:https?://)?(?:www\.)?pixiv\.net/novel/show\.php\?id=(\d+)"
SERIES_PATTERN = r"(?:https?://)?(?:www\.)?pixiv\.net/novel/series/(\d+)"
AUTHOR_PATTERN = r"(?:https?://)?(?:www\.)?pixiv\.net/users?/(\d+)"

# 提取规则：pattern 负责抓 ID，label 用于解析失败的提示文案。
NOVEL = IdRule(NOVEL_PATTERN, "小说")
SERIES = IdRule(SERIES_PATTERN, "系列")
AUTHOR = IdRule(AUTHOR_PATTERN, "作者")