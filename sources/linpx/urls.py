from sources.linpx.config import BASE, API_BASE


def url_novel(novel_id: str | int) -> str:
	return f"{BASE}/pixiv/novel/{novel_id}"

def url_novel_data(novel_id: str | int) -> str:
	return f"{API_BASE}/pixiv/novel/{novel_id}/cache"


def url_series(series_id: str | int) -> str:
	return f"{BASE}/pixiv/series/{series_id}"
	# return f"https://www.pixiv.net/novel/series/{series_id}"

def url_series_data(series_id: str | int) -> str:
	return f"{API_BASE}/pixiv/series/{series_id}/cache"


def url_user(user_id: str | int) -> str:
	return f"{BASE}/pixiv/user/{user_id}"

def url_user_data(user_id: str | int) -> str:
	return f"{API_BASE}/pixiv/user/{user_id}/cache"

def url_fav_user_data() -> str:
	return f"{API_BASE}/fav/user/cache"
