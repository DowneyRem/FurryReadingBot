import re

def get_id(string: str) -> str:
	if re.search(r"\d+", str(string)):
		return re.search(r"\d+", str(string)).group()
	else:
		return ""


def get_url(string: str) -> str:
	pattern = "(?:https?|ftp|file)://[-A-Za-z0-9+&@#/%?=~_|!:,.;]+[-A-Za-z0-9+&@#/%=~_|]"
	urls = re.findall(pattern, string)
	if len(urls) == 1:
		return urls[0]
	else:
		return urls
