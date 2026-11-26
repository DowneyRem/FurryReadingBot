from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utc_now() -> datetime:
	return datetime.now(timezone.utc)


def utc_now_iso() -> str:
	return utc_now().strftime("%Y-%m-%dT%H:%M:%S%z")


def parse_iso(s: str) -> datetime | None:
	"""解析存储里的时间字符串，兼容 ``+0000`` 与 ``+00:00``。"""
	if not s:
		return None
	try:
		s = s.strip()
		if len(s) >= 5 and (s[-5] in "+-" and s[-3] != ":"):
			s = s[:-2] + ":" + s[-2:]
		return datetime.fromisoformat(s)
	except Exception:
		return None


def cooldown_remaining(moment: datetime | None, hours: float) -> float:
	"""距离 ``moment + hours`` 还剩多少秒；时间缺失或已过期返回 0。"""
	return remaining_seconds(moment, timedelta(hours=hours))


def cooldown_left(stamp: str, hours: float) -> float:
	"""直接吃存储里的时间字符串：``stamp + hours`` 还剩多少秒。

	空串 / 格式坏 / 已过期都返回 0（调用方按「现在就能申请」处理）；
	省掉每个 Store 再写一遍 ``cooldown_remaining(parse_iso(...), hours)``。
	"""
	return cooldown_remaining(parse_iso(stamp), hours)


def remaining_seconds(moment: datetime | None, window: timedelta) -> float:
	"""距离 ``moment + window`` 还剩多少秒；时间缺失或已过期返回 0。

	冷却（小时）/ 分享冷却（天）/ 材料窗口（分钟）都走这里，
	单位由调用方传进 ``window``，不用各自再写一遍减法。
	"""
	if moment is None:
		return 0.0
	return max(0.0, (moment + window - utc_now()).total_seconds())


def is_expired(stamp: str, *, now: datetime | None = None, missing: bool = False) -> bool:
	"""``expires_at`` 这类「绝对到期时间戳」是否已到期。

	解析失败（空串 / 手写坏）按 ``missing`` 决定：
	cache 传 ``True``（没有到期时间的缓存条目本就该重建），
	``file_cache`` 的旧条目传 ``False``（升级前写入的记录还能继续复用）。

	``now`` 可传入同一批淘汰共用的「当前时间」，避免逐条取时钟。
	"""
	expires = parse_iso(str(stamp or ""))
	if expires is None:
		return missing
	return (now or utc_now()) >= expires


def is_older_than(moment: datetime | None, days: float) -> bool:
	"""``moment`` 是否已经早于「现在 - days 天」（存储层 TTL 淘汰用）。

	时间缺失（``None``，例如升级前的旧数据 / 手写坏字段）返回 ``False``：
	宁可留下一条无法判断时间的记录，也不要静默删掉业务数据。
	``days=0`` 表示「过去的都算过期」，与其它 TTL 的 0 语义一致。
	"""
	return moment is not None and remaining_seconds(
		moment, timedelta(days=days)) <= 0.0


def format_remaining(seconds: float) -> str:
	"""把剩余秒数格式化为「x 天 y 小时」/「x 小时 y 分钟」/「x 分钟」。"""
	minutes = int(seconds // 60) + (1 if seconds % 60 else 0)
	days, minutes = divmod(minutes, 24 * 60)
	hours, minutes = divmod(minutes, 60)
	if days:
		return f"{days} 天 {hours} 小时" if hours else f"{days} 天"
	if hours:
		return f"{hours} 小时 {minutes} 分钟" if minutes else f"{hours} 小时"
	return f"{max(minutes, 1)} 分钟"
