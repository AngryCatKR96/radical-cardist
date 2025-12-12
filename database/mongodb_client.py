"""
MongoDB Atlas 클라이언트 모듈

MongoDB Atlas 연결 관리, 헬스 체크, 컬렉션 접근을 담당합니다.
Singleton 패턴으로 구현되어 애플리케이션 전체에서 하나의 연결을 공유합니다.
"""

import os
import time
from typing import Optional
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from dotenv import load_dotenv

load_dotenv()


class MongoDBClient:
    """
    MongoDB Atlas 클라이언트 (Singleton)

    환경변수에서 MongoDB 연결 정보를 읽고, 연결을 관리합니다.
    """

    _instance: Optional["MongoDBClient"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        """
        MongoDB 클라이언트 초기화

        Args:
            max_retries: 연결 재시도 횟수
            retry_delay: 재시도 간 대기 시간 (초)
        """
        if self._initialized:
            return

        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # 환경변수 로드
        self.uri = os.getenv("MONGODB_URI")
        self.db_name = os.getenv("MONGODB_DATABASE", "radical_cardist")
        self.collection_name = os.getenv("MONGODB_COLLECTION_CARDS", "cards")

        # 환경변수 검증
        if not self.uri or "<username>" in self.uri or "<password>" in self.uri:
            raise ValueError(
                "MONGODB_URI 환경변수가 설정되지 않았거나 유효하지 않습니다. "
                ".env 파일에 실제 MongoDB Atlas connection string을 설정해주세요."
            )

        # MongoDB 연결
        self._connect_with_retry()
        self._initialized = True

    def _connect_with_retry(self):
        """재시도 로직을 포함한 MongoDB 연결"""
        last_error = None

        for attempt in range(self.max_retries):
            try:
                print(f"MongoDB 연결 시도 {attempt + 1}/{self.max_retries}...")

                self.client: MongoClient = MongoClient(
                    self.uri,
                    serverSelectionTimeoutMS=10000,
                    connectTimeoutMS=10000,
                    socketTimeoutMS=10000
                )

                # 연결 확인
                self.client.admin.command('ping')

                # 데이터베이스 및 컬렉션 설정
                self.db: Database = self.client[self.db_name]
                self._cards_collection: Collection = self.db[self.collection_name]

                print(f"✅ MongoDB Atlas 연결 성공: {self.db_name}")
                return

            except (ConnectionFailure, ServerSelectionTimeoutError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    print(f"⚠️  연결 실패, {wait_time}초 후 재시도... (에러: {e})")
                    time.sleep(wait_time)
                else:
                    raise ConnectionError(
                        f"MongoDB 연결 실패 (시도 {self.max_retries}회): {last_error}"
                    ) from last_error
            except Exception as e:
                raise ConnectionError(f"MongoDB 연결 중 예상치 못한 오류: {e}") from e

    def get_collection(self, name: Optional[str] = None) -> Collection:
        """
        컬렉션 접근

        Args:
            name: 컬렉션 이름 (기본값: cards)

        Returns:
            MongoDB Collection 객체
        """
        if name is None:
            return self._cards_collection
        return self.db[name]

    def health_check(self) -> bool:
        """
        MongoDB 연결 상태 확인

        Returns:
            연결 성공 시 True, 실패 시 False
        """
        try:
            self.client.admin.command('ping')
            return True
        except Exception as e:
            print(f"MongoDB health check 실패: {e}")
            return False

    def get_stats(self) -> dict:
        """
        데이터베이스 통계 정보 조회

        Returns:
            통계 정보 딕셔너리
        """
        try:
            collection = self.get_collection()

            total_docs = collection.count_documents({})
            with_embeddings = collection.count_documents({"embeddings.0": {"$exists": True}})

            # 일반 인덱스 정보
            indexes = list(collection.list_indexes())
            index_names = [idx["name"] for idx in indexes]

            # Atlas Search 인덱스 확인 (MongoDB 7.0+)
            search_indexes = []
            vector_search_ready = False

            try:
                # $listSearchIndexes aggregation으로 Atlas Search 인덱스 조회
                search_index_cursor = collection.aggregate([
                    {"$listSearchIndexes": {}}
                ])
                search_indexes = [idx["name"] for idx in search_index_cursor]
                vector_search_ready = "card_vector_search" in search_indexes
            except Exception as search_error:
                # MongoDB 버전이 낮거나 권한이 없는 경우
                print(f"Search index 조회 실패 (정상적일 수 있음): {search_error}")
                # embeddings가 있으면 vector search가 설정되었다고 가정
                vector_search_ready = with_embeddings > 0

            return {
                "database": self.db_name,
                "collection": self.collection_name,
                "total_documents": total_docs,
                "documents_with_embeddings": with_embeddings,
                "indexes": index_names,
                "search_indexes": search_indexes,
                "vector_search_ready": vector_search_ready
            }
        except Exception as e:
            return {"error": str(e)}

    def close(self):
        """MongoDB 연결 종료"""
        if hasattr(self, "client") and self.client:
            self.client.close()
            print("MongoDB 연결 종료")
