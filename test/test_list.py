from storage.list import ListManager


def test_add_and_contains() -> None:
	mgr = ListManager()
	assert not mgr.is_whitelisted("1")
	mgr.add_whitelist("1", name="A", note="ok")
	assert mgr.is_whitelisted("1")
	assert mgr.whitelist.get("1")["name"] == "A"


def test_persist_across_instances() -> None:
	mgr1 = ListManager()
	mgr1.add_blacklist("99", name="bad")
	mgr2 = ListManager()
	assert mgr2.is_blacklisted("99")


def test_whitelist_removes_from_blacklist() -> None:
	mgr = ListManager()
	mgr.add_blacklist("7")
	mgr.add_whitelist("7", name="now_good")
	assert mgr.is_whitelisted("7")
	assert not mgr.is_blacklisted("7")


def test_remove() -> None:
	mgr = ListManager()
	mgr.add_whitelist("3")
	assert mgr.remove_whitelist("3") is True
	assert not mgr.is_whitelisted("3")
	assert mgr.remove_whitelist("3") is False
	
	
if __name__ == "__main__":
	test_add_and_contains()
	test_persist_across_instances()
	test_whitelist_removes_from_blacklist()
	test_remove()
