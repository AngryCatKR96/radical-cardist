"""
사용자 요청 로깅

모든 API 요청을 MongoDB에 기록하여 분석 및 디버깅에 활용합니다.
"""

import time
import traceback
from datetime import datetime
from typing import Optional, Dict, List
from database.mongodb_client import MongoDBClient
from .ip_utils import hash_ip


class RequestTimer:
    """요청 처리 시간 측정"""

    def __init__(self):
        self.start_time = None
        self.step_times = {}

    def start(self):
        """타이머 시작"""
        self.start_time = time.perf_counter()

    def mark_step(self, step_name: str):
        """
        단계 완료 시각 기록

        Args:
            step_name: 단계 이름 (예: "step1_input_parsing_ms")
        """
        if self.start_time:
            elapsed_ms = (time.perf_counter() - self.start_time) * 1000
            self.step_times[step_name] = round(elapsed_ms, 2)

    def get_total_time(self) -> float:
        """
        총 처리 시간 (밀리초)

        Returns:
            시작부터 현재까지의 시간 (ms)
        """
        if self.start_time:
            return round((time.perf_counter() - self.start_time) * 1000, 2)
        return 0.0

    def get_performance_dict(self) -> Dict[str, float]:
        """
        성능 메트릭 딕셔너리

        Returns:
            단계별 시간 + 총 시간
        """
        return {
            **self.step_times,
            "total_ms": self.get_total_time()
        }


class RequestLogger:
    """MongoDB 기반 요청 로거"""

    def __init__(self):
        """MongoDB 클라이언트 초기화"""
        try:
            self.mongo_client = MongoDBClient()
            self.collection = self.mongo_client.get_user_requests_collection()
            print(f"[DEBUG] RequestLogger 초기화 성공: collection={self.collection}")
        except Exception as e:
            print(f"[WARNING] RequestLogger 초기화 실패: {e}")
            self.collection = None

    async def log_request(
        self,
        ip_address: str,
        endpoint: str,
        user_input: str,
        processing_time_ms: float,
        status: str,
        recommendation: Optional[Dict] = None,
        error: Optional[Dict] = None,
        performance: Optional[Dict] = None,
        prompt_attack_detected: bool = False,
        attack_patterns: Optional[List[str]] = None,
        alternative_cards: Optional[List[str]] = None
    ):
        """
        요청을 MongoDB에 비동기 로깅

        Args:
            ip_address: 클라이언트 IP (해싱 전)
            endpoint: API 엔드포인트
            user_input: 사용자 입력
            processing_time_ms: 처리 시간
            status: "success" | "error" | "rate_limited" | "validation_error"
            recommendation: 추천 결과 (성공 시)
            error: 에러 정보 (실패 시)
            performance: 성능 메트릭
            prompt_attack_detected: 프롬프트 공격 탐지 여부
            attack_patterns: 탐지된 공격 패턴 목록
            alternative_cards: 고려된 대안 카드들
        """
        if self.collection is None:
            # MongoDB 연결 실패 시 로깅 건너뛰기 (서비스는 계속)
            print("[WARNING] MongoDB collection 없음, 로깅 생략")
            return

        try:
            print(f"[DEBUG] log_request 시작: ip={ip_address}, endpoint={endpoint}, status={status}")

            # IP 해싱
            hashed_ip = hash_ip(ip_address)
            print(f"[DEBUG] IP 해싱 완료: {hashed_ip[:16]}...")

            # 로그 엔트리 구성
            log_entry = {
                "timestamp": datetime.utcnow(),
                "ip_address": hashed_ip,
                "endpoint": endpoint,
                "user_input": user_input,
                "processing_time_ms": processing_time_ms,
                "status": status,
                "prompt_attack_detected": prompt_attack_detected,
                "attack_patterns_matched": attack_patterns or []
            }

            # 성공 시 추천 정보
            if recommendation:
                log_entry["recommendation"] = recommendation

            # 에러 시 에러 정보
            if error:
                log_entry["error"] = error

            # 성능 메트릭
            if performance:
                log_entry["performance"] = performance

            # 대안 카드
            if alternative_cards:
                log_entry["alternative_cards"] = alternative_cards

            print(f"[DEBUG] MongoDB에 로그 삽입 시작...")
            # MongoDB에 삽입 (fire-and-forget)
            result = self.collection.insert_one(log_entry)
            print(f"[DEBUG] MongoDB 로그 삽입 성공: inserted_id={result.inserted_id}")

        except Exception as e:
            # 로깅 실패해도 API 응답은 정상 반환
            print(f"[ERROR] 요청 로깅 실패: {e}")
            print(traceback.format_exc())
