from sources.pixiv.config import BASE, API_BASE


def url_novel(novel_id: str | int) -> str:
	return f"{BASE}/novel/show.php?id={novel_id}"

def url_novel_data(novel_id: str | int) -> str:
	return f"{API_BASE}/novel/{novel_id}"


def url_series(series_id: str | int) -> str:
	return f"{BASE}/novel/series/{series_id}"

def url_series_data(series_id: str | int) -> str:
	return f"{API_BASE}/novel/series/{series_id}"

def url_series_novels_title(series_id: str | int) -> str:
	return f"{API_BASE}/novel/series/{series_id}/content_titles"


def url_user(user_id: str | int) -> str:
	return f"{BASE}/users/{user_id}"

def url_user_data(user_id: str | int) -> str:
	return f"{API_BASE}/user/{user_id}?full=1"

def url_user_works_all(user_id: str | int) -> str:
	return f"{API_BASE}/user/{user_id}/profile/all"

def url_user_works_latest(user_id: str | int) -> str:
	return f"{API_BASE}/user/{user_id}/works/latest"


# aliases
def url_author(author_id: str | int) -> str:
	return url_user(author_id)

def url_author_data(author_id: str | int) -> str:
	return url_user_data(author_id)

def url_author_works_all(author_id: str | int) -> str:
	return url_user_works_all(author_id)

def url_author_works_latest(author_id: str | int) -> str:
	return url_user_works_latest(author_id)
