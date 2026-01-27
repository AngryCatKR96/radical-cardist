#!/usr/bin/env bash
set -euo pipefail

# 스크래핑(fetch) → 임베딩(embed) 을 한 번에 수행합니다.
#
# 사용 예시:
#   ./script/sync_cards.sh
#   ./script/sync_cards.sh --start 1 --end 4000
#   ./script/sync_cards.sh --card-ids 2862,1357
#   ./script/sync_cards.sh cardid 18
#   ./script/sync_cards.sh --start 1 --end 4000 --overwrite
#
# 전달 인자:
#   - fetch_cardgorilla_range.py / embed_mongodb.py 에 동일하게 전달됩니다.
#   - 두 스크립트 공통 인자: --start, --end, --card-ids, --overwrite

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".env" ]]; then
  # .env를 현재 쉘 환경으로 로드 (key=value 형태 가정)
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

require_env() {
  local key="$1"
  if [[ -z "${!key:-}" ]]; then
    echo "❌ 환경변수 누락: $key"
    echo "   .env(.env.example 참고)에 값을 설정해주세요."
    exit 1
  fi
}

# 임베딩 단계에 필요한 최소 환경변수
require_env "OPENAI_API_KEY"
require_env "MONGODB_URI"
require_env "MONGODB_DATABASE"
require_env "MONGODB_COLLECTION_CARDS"

# 축약 인자 지원:
#   ./script/sync_cards.sh cardid 18  ->  ./script/sync_cards.sh --card-ids 18
ARGS=("$@")
if [[ "${1:-}" == "cardid" ]]; then
  if [[ -z "${2:-}" ]]; then
    echo "❌ 사용법: ./script/sync_cards.sh cardid <id>"
    exit 1
  fi
  ARGS=(--card-ids "$2" "${@:3}")
fi

echo "==> 1/2 카드고릴라 스크래핑(JSON 캐시 생성)"
python "script/fetch_cardgorilla_range.py" "${ARGS[@]}"

echo
echo "==> 2/2 MongoDB 임베딩 생성(cards 컬렉션 저장)"
python "script/embed_mongodb.py" "${ARGS[@]}"

echo
echo "✅ 완료: 스크래핑 + 임베딩"
