"""TakedownService：作者被拉黑后按作者下架历史分享。

运行（在项目根目录）:
	python -m pytest test/test_takedown_service.py -v
"""

from __future__ import annotations

import asyncio

from services.takedown_service import TakedownService
from storage.share_records import ShareRecordStore


def run(coro):
	return asyncio.run(coro)


def make_records(tmp_path) -> ShareRecordStore:
	return ShareRecordStore(
		path=tmp_path / "share_records.json", cooldown_days=0)


def record(
		records: ShareRecordStore,
		*,
		author_id="12345",
		author_name="某作者",
		kind="novel",
		item_id="1001",
		messages=(("-1001", 812),),
):
	return records.record(
		author_id=author_id,
		author_name=author_name,
		kind=kind,
		item_id=item_id,
		messages=list(messages),
		title="雨夜",
		user_id=42,
		user_name="Alice",
	)


def deleter(*, fail=()):
	"""(chat_id, message_id) 删除器；fail 里的组合抛异常。"""
	seen: list[tuple[str, int]] = []

	async def delete(chat_id: str, message_id: int) -> None:
		if (chat_id, message_id) in fail:
			raise RuntimeError("no rights")
		seen.append((chat_id, message_id))

	return delete, seen


def test_takedown_deletes_everything(tmp_path) -> None:
	records = make_records(tmp_path)
	record(records, messages=(("-1001", 903), ("-1002", 889)))
	record(records, kind="series", item_id="55", messages=(("-1002", 912),))
	record(records, author_id="67890", messages=(("-1001", 45),))

	delete, seen = deleter()
	result = run(TakedownService(records).takedown("12345", delete=delete))

	assert result.deleted == 3
	assert result.failed == 0
	assert result.skipped == 0
	assert result.ok is True
	assert sorted(seen) == [("-1001", 903), ("-1002", 889), ("-1002", 912)]
	# 该作者的记录清空，其他作者不受影响
	assert records.by_author("12345") == []
	assert len(records.by_author("67890")) == 1


def test_takedown_keeps_failed_message_for_retry(tmp_path) -> None:
	records = make_records(tmp_path)
	record(records, messages=(("-1001", 903), ("-1002", 889)))

	delete, _seen = deleter(fail=(("-1002", 889),))
	result = run(TakedownService(records).takedown("12345", delete=delete))

	assert result.deleted == 1
	assert result.failed == 1
	assert result.ok is False
	assert "-1002/889" in result.errors[0]
	# 失败的那条记录还在，作者节点也留着，方便下次重试
	rows = records.by_author("12345")
	assert [(row.chat_id, row.message_id) for row in rows] == [("-1002", 889)]


def test_takedown_skips_message_without_handle(tmp_path) -> None:
	"""没有 message_id 的老记录删不掉，只清记录并计入 skipped。"""
	records = make_records(tmp_path)
	record(records, messages=(("-1001", 0),))

	delete, seen = deleter()
	result = run(TakedownService(records).takedown("12345", delete=delete))

	assert result.deleted == 0
	assert result.skipped == 1
	assert result.failed == 0
	assert seen == []
	assert records.by_author("12345") == []


def test_takedown_without_author_is_noop(tmp_path) -> None:
	records = make_records(tmp_path)
	record(records)

	delete, seen = deleter()
	result = run(TakedownService(records).takedown("", delete=delete))

	assert result.total == 0
	assert seen == []
	assert len(records.by_author("12345")) == 1
