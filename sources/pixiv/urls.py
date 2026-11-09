from sources.pixiv.config import BASE


def url_novel(novel_id: str | int) -> str:
	return f"{BASE}/novel/show.php?id={novel_id}"

def url_novel_data(novel_id: str | int) -> str:
	return f"{BASE}/ajax/novel/{novel_id}"

def url_novels_data(user_id, novel_ids: list[ str | int ]) -> str:
	query = "&".join([f"ids[]={v}" for v in novel_ids])
	return f"{BASE}/ajax/user/{user_id}/novels?{query}"


def url_series(series_id: str | int) -> str:
	return f"{BASE}/novel/series/{series_id}"

def url_series_data(series_id: str | int) -> str:
	return f"{BASE}/ajax/novel/series/{series_id}"

def url_series_novels(series_id: str | int, limit: int=30, offset: int=10) -> str:
	return f"{BASE}/ajax/novel/series_content/{series_id}?limit={limit}&last_order={offset}&order_by=asc&lang=zh"

def url_series_novels_title(series_id: str | int) -> str:
	return f"{BASE}/ajax/novel/series/{series_id}/content_titles"


def url_user(user_id: str | int) -> str:
	return f"`{BASE}/users/{user_id}"

def url_user_data(user_id: str | int) -> str:
	return f"{BASE}/ajax/user/{user_id}"

def url_user_work_latest(user_id: str | int) -> str:
	return f"{BASE}/ajax/user/{user_id}/works/latest"
	
def url_user_works_all(user_id: str | int) -> str:
	return f"{BASE}/ajax/user/{user_id}/profile/all"
