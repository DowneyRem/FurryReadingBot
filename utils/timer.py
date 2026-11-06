import time
import logging
import asyncio
from functools import wraps


def timer(function):
	@wraps(function)
	def wrapper(*args, **kwargs):
		# --- 异步函数处理分支 ---
		if asyncio.iscoroutinefunction(function):
			async def async_wrapper(*args, **kwargs):
				start = time.perf_counter()
				try:
					return await function(*args, **kwargs)
				finally:
					end = time.perf_counter()
					# 建议把 print 改为 logging，这样能带有时间戳，且方便在异步高并发中追踪
					logging.info(f"[Timer] {function.__module__}.{function.__name__}: {end - start:.4f}s")
					print(f"[Timer] {function.__module__}.{function.__name__}: {end - start:.4f}s")
			
			return async_wrapper(*args, **kwargs)
		
		# --- 同步函数处理分支 ---
		start = time.perf_counter()
		try:
			return function(*args, **kwargs)
		finally:
			end = time.perf_counter()
			logging.info(f"[Timer] {function.__module__}.{function.__name__}: {end - start:.4f}s")
			print(f"[Timer] {function.__module__}.{function.__name__}: {end - start:.4f}s")
	
	return wrapper
