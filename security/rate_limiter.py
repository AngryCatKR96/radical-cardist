"""
IP 기반 Rate Limiting

일일 API 호출 횟수를 제한하여 서비스 남용을 방지합니다.
MongoDB에 IP별 호출 횟수를 저장하고 자정(KST) 기준으로 자동 리셋합니다.
"""

import os
from datetime import datetime, timedelta
from typing import Tuple
import pytz
from fastapi import HTTPException, Request
from database.mongodb_client import MongoDBClient
from .ip_utils import get_client_ip, hash_ip


class RateLimiter:
    """MongoDB 기반 IP Rate Limiter"""

    def __init__(self):
        """
        Rate limiter 초기화

        환경변수:
            RATE_LIMIT_DAILY: 일일 요청 한도 (기본값: 3)
            RATE_LIMIT_TIMEZONE: 리셋 타임존 (기본값: Asia/Seoul)
        """
        try:
            self.mongo_client = MongoDBClient()
            self.collection = self.mongo_client.get_rate_limits_collection()
        except Exception as e:
            print(f"[WARNING] RateLimiter MongoDB 초기화 실패: {e}")
            self.collection = None

        self.daily_limit = int(os.getenv("RATE_LIMIT_DAILY", "3"))
        self.timezone = os.getenv("RATE_LIMIT_TIMEZONE", "Asia/Seoul")

    async def check_rate_limit(self, ip_address: str) -> Tuple[bool, int, datetime]:
        """
        IP의 rate limit 확인

        Args:
            ip_address: 클라이언트 IP (해싱 전)

        Returns:
            (is_allowed, remaining_requests, reset_time):
                - is_allowed: 요청 허용 여부
                - remaining_requests: 남은 요청 횟수
                - reset_time: 리셋 시각 (UTC)

        Raises:
            Exception: MongoDB 연결 실패 시
        """
        if self.collection is None:
            # MongoDB 연결 실패 시 fail open (요청 허용)
            print("[WARNING] Rate limiting 비활성화 (MongoDB 연결 없음)")
            return (True, self.daily_limit, datetime.utcnow())

        hashed_ip = hash_ip(ip_address)
        now_utc = datetime.utcnow()
        reset_time = self._get_next_reset_time(now_utc)

        # 기존 rate limit 문서 조회
        rate_doc = self.collection.find_one({"ip_address": hashed_ip})

        if not rate_doc:
            # 첫 요청 - 문서 생성
            self.collection.insert_one({
                "ip_address": hashed_ip,
                "request_count": 1,
                "first_request_at": now_utc,
                "last_request_at": now_utc,
                "reset_at": reset_time,
                "created_at": now_utc,
                "updated_at": now_utc
            })
            return (True, self.daily_limit - 1, reset_time)

        # 리셋 시각 지났는지 확인
        if now_utc >= rate_doc["reset_at"]:
            # 카운터 리셋
            self.collection.update_one(
                {"_id": rate_doc["_id"]},
                {
                    "$set": {
                        "request_count": 1,
                        "first_request_at": now_utc,
                        "last_request_at": now_utc,
                        "reset_at": reset_time,
                        "updated_at": now_utc
                    }
                }
            )
            return (True, self.daily_limit - 1, reset_time)

        # 현재 카운트 확인
        current_count = rate_doc["request_count"]
        if current_count >= self.daily_limit:
            # 한도 초과
            return (False, 0, rate_doc["reset_at"])

        # 카운터 증가
        self.collection.update_one(
            {"_id": rate_doc["_id"]},
            {
                "$inc": {"request_count": 1},
                "$set": {
                    "last_request_at": now_utc,
                    "updated_at": now_utc
                }
            }
        )

        return (True, self.daily_limit - current_count - 1, rate_doc["reset_at"])

    def _get_next_reset_time(self, current_utc: datetime) -> datetime:
        """
        다음 리셋 시각 계산 (자정 KST)

        Args:
            current_utc: 현재 시각 (UTC)

        Returns:
            다음 자정 KST 시각 (UTC로 변환)

        Note:
            KST는 UTC+9, 따라서 자정 KST = 15:00 UTC (전날)
        """
        try:
            kst = pytz.timezone(self.timezone)
            current_kst = current_utc.replace(tzinfo=pytz.UTC).astimezone(kst)

            # 다음 자정 KST
            next_midnight_kst = (current_kst + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            # UTC로 변환 (timezone-naive로 반환)
            return next_midnight_kst.astimezone(pytz.UTC).replace(tzinfo=None)

        except Exception as e:
            print(f"[ERROR] Reset time 계산 실패: {e}")
            # 폴백: 24시간 후
            return current_utc + timedelta(hours=24)


async def rate_limit_dependency(request: Request):
    """
    FastAPI dependency for rate limiting

    Args:
        request: FastAPI Request 객체

    Raises:
        HTTPException: 429 if rate limit exceeded

    Usage:
        @app.post("/endpoint", dependencies=[Depends(rate_limit_dependency)])
        async def endpoint():
            ...
    """
    ip_address = get_client_ip(request)
    rate_limiter = RateLimiter()

    try:
        is_allowed, remaining, reset_time = await rate_limiter.check_rate_limit(ip_address)

        if not is_allowed:
            # 한도 초과
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "message": "일일 추천 횟수를 초과했습니다. 내일 다시 시도해주세요.",
                    "reset_at": reset_time.isoformat(),
                    "limit": rate_limiter.daily_limit
                },
                headers={
                    "X-RateLimit-Limit": str(rate_limiter.daily_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(reset_time.timestamp()))
                }
            )

        # 요청 상태를 request.state에 저장 (로깅용)
        request.state.rate_limit_remaining = remaining
        request.state.rate_limit_reset = reset_time

    except HTTPException:
        # 429 에러는 그대로 전달
        raise

    except Exception as e:
        # MongoDB 연결 실패 등 - fail open (요청 허용)
        print(f"[ERROR] Rate limiting 실패: {e}")
        print("   요청을 허용합니다 (fail open)")
        # 에러 발생해도 요청은 계속
