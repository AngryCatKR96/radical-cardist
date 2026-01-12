"""
공통 유틸리티 함수

함수 실행 시간 측정 데코레이터 등 유틸리티 함수 제공
"""

import time
import functools
from typing import Callable, Any
import inspect


def measure_time(func_name: str = None, verbose: bool = True):
    """
    함수 실행 시간 측정 데코레이터 (동기/비동기 모두 지원) 
    
    Args:
        func_name: 로그에 표시할 함수 이름 (기본값: 함수명)
        verbose: 상세 로그 출력 여부 (기본값: True)
    
    사용 예시:
        @measure_time()
        def my_function():
            ...
        
        @measure_time(verbose=False)
        async def my_async_function():
            ...
        
        @measure_time("커스텀 이름")
        async def analyze_one(self, user_pattern, card_context):
            ...
    
    다른 모듈에서 사용:
        from utils import measure_time
        
        @measure_time("fetch_card_detail")
        async def fetch_card_detail(self, card_id: int):
            ...
    """
    def decorator(func: Callable) -> Callable: 
        is_async = inspect.iscoroutinefunction(func)
        display_name = func_name or func.__name__
        
        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                start_time = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                    elapsed = time.perf_counter() - start_time
                    elapsed_ms = elapsed * 1000
                    
                    if verbose:
                        print(f"[PERF] {display_name}: {elapsed_ms:.2f}ms ({elapsed:.3f}초)")
                    
                    return result
                except Exception as e:
                    elapsed = time.perf_counter() - start_time
                    elapsed_ms = elapsed * 1000
                    if verbose:
                        print(f"[PERF] {display_name} (실패): {elapsed_ms:.2f}ms ({elapsed:.3f}초)")
                    raise
            
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> Any:
                start_time = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                    elapsed = time.perf_counter() - start_time
                    elapsed_ms = elapsed * 1000
                    
                    if verbose:
                        print(f"[PERF] {display_name}: {elapsed_ms:.2f}ms ({elapsed:.3f}초)")
                    
                    return result
                except Exception as e:
                    elapsed = time.perf_counter() - start_time
                    elapsed_ms = elapsed * 1000
                    if verbose:
                        print(f"[PERF] {display_name} (실패): {elapsed_ms:.2f}ms ({elapsed:.3f}초)")
                    raise
            
            return sync_wrapper
    
    return decorator
