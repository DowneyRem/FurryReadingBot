from urllib.parse import urlencode

from sources.pixiv.config import API_BASE, BASE, DEFAULT_SERIES_LIMIT, LANG


def url_novel(novel_id: str | int) -> str:
	return f"{BASE}/novel/show.php?id={novel_id}"

def url_novel_data(novel_id: str | int) -> str:
	return f"{API_BASE}/novel/{novel_id}"

def url_novels_data(user_id: str | int, novel_ids: list[str | int]) -> str:
	query = urlencode([("ids[]", str(novel_id)) for novel_id in novel_ids])
	return f"{API_BASE}/user/{user_id}/novels?{query}"


def url_series(series_id: str | int) -> str:
	return f"{BASE}/novel/series/{series_id}"

def url_series_data(series_id: str | int) -> str:
	return f"{API_BASE}/novel/series/{series_id}"


def url_series_content(
	series_id: str | int,
	*,
	limit: int = DEFAULT_SERIES_LIMIT,
	last_order: int | str | None = None,
	order_by: str = "asc",
	lang: str = LANG,
) -> str:
	params: dict[str, object] = {
		"limit": limit,
		"order_by": order_by,
		"lang": lang,
	}
	if last_order is not None:
		params["last_order"] = last_order
	return f"{API_BASE}/novel/series_content/{series_id}?{urlencode(params)}"


def url_series_novels(
	series_id: str | int,
	limit: int = DEFAULT_SERIES_LIMIT,
	last_order: int | str | None = None,
	order_by: str = "asc",
	lang: str = LANG,
) -> str:
	"""旧名字，等价于 `url_series_content`。"""
	return url_series_content(
		series_id, limit=limit, last_order=last_order, order_by=order_by, lang=lang)


def url_series_novels_title(series_id: str | int) -> str:
	return f"{API_BASE}/novel/series/{series_id}/content_titles"


def url_user(user_id: str | int) -> str:
	return f"{BASE}/users/{user_id}"

def url_user_data(user_id: str | int) -> str:
	return f"{API_BASE}/user/{user_id}"

def url_user_works_latest(user_id: str | int) -> str:
	return f"{API_BASE}/user/{user_id}/works/latest"

def url_user_works_all(user_id: str | int) -> str:
	return f"{API_BASE}/user/{user_id}/profile/all"


# aliases
def url_author(author_id: str | int) -> str:
	return url_user(author_id)

def url_author_data(author_id: str | int) -> str:
	return url_user_data(author_id)

def url_author_works_latest(author_id: str | int) -> str:
	return url_user_works_latest(author_id)

def url_author_works_all(author_id: str | int) -> str:
	return url_user_works_all(author_id)
