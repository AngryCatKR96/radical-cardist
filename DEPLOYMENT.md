# Cloud Run 배포 가이드

Google Cloud Run을 사용한 Radical Cardist MVP 배포 가이드입니다.

## 📋 사전 준비

### 1. Google Cloud Platform 계정 및 프로젝트 생성

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 새 프로젝트 생성 또는 기존 프로젝트 선택
3. 결제 계정 연결 (무료 크레딧 $300 제공)

### 2. gcloud CLI 설치

```bash
# macOS
brew install google-cloud-sdk

# 또는 공식 설치 스크립트
curl https://sdk.cloud.google.com | bash

# 설치 후 초기화
gcloud init
```

### 3. 인증 및 프로젝트 설정

```bash
# Google 계정으로 로그인
gcloud auth login

# 프로젝트 ID 확인
gcloud projects list

# 프로젝트 설정
gcloud config set project YOUR_PROJECT_ID
```

### 4. 환경 변수 설정

```bash
# 필수 환경 변수 설정
export GCP_PROJECT_ID="your-project-id"
export GCP_REGION="asia-northeast3"  # 서울 리전
export OPENAI_API_KEY="your-openai-api-key"
```

## 🚀 배포 단계

### Step 1: Backend (FastAPI) 배포

```bash
# 백엔드 배포 스크립트 실행
./deploy-backend.sh
```

배포가 완료되면 백엔드 URL이 출력됩니다:
```
✅ Backend deployment complete!
📍 Service URL: https://radical-cardist-backend-xxx.run.app
```

**이 URL을 복사해두세요!** 프론트엔드 배포 시 필요합니다.

### Step 2: Frontend (Next.js) 배포

```bash
# 백엔드 URL을 환경 변수로 설정
export NEXT_PUBLIC_API_BASE_URL="https://radical-cardist-backend-xxx.run.app"

# 프론트엔드 배포 스크립트 실행
./deploy-frontend.sh
```

배포가 완료되면:
```
✅ Frontend deployment complete!
📍 Service URL: https://radical-cardist-frontend-xxx.run.app
```

### Step 3: 환경 변수 업데이트 (필요 시)

```bash
# Backend 환경 변수 업데이트
gcloud run services update radical-cardist-backend \
  --set-env-vars OPENAI_API_KEY=your-new-key \
  --region asia-northeast3

# Frontend 환경 변수 업데이트
gcloud run services update radical-cardist-frontend \
  --set-env-vars NEXT_PUBLIC_API_BASE_URL=https://your-backend-url \
  --region asia-northeast3
```

## 🧪 배포 테스트

### Backend API 테스트

```bash
# Health check
curl https://radical-cardist-backend-xxx.run.app/health

# API 문서 확인
open https://radical-cardist-backend-xxx.run.app/docs
```

### Frontend 테스트

브라우저에서 프론트엔드 URL 접속:
```
https://radical-cardist-frontend-xxx.run.app
```

## 📊 비용 관리

### 무료 티어 한도
- **Cloud Run**: 매월 200만 요청 무료
- **Cloud Build**: 120 빌드-분/일 무료
- **Container Registry**: 0.5GB 스토리지 무료

### 비용 예상 (무료 티어 초과 시)
- Cloud Run: $0.00002400/vCPU-초, $0.00000250/GiB-초
- 예상 월 비용: 트래픽 적은 MVP는 거의 무료

### 비용 확인
```bash
# 현재 비용 확인
gcloud billing accounts list
```

[GCP 콘솔](https://console.cloud.google.com/billing)에서 실시간 비용 모니터링 가능

## 🔧 유용한 명령어

### 로그 확인
```bash
# Backend 로그
gcloud run services logs read radical-cardist-backend \
  --region asia-northeast3 \
  --limit 50

# Frontend 로그
gcloud run services logs read radical-cardist-frontend \
  --region asia-northeast3 \
  --limit 50
```

### 서비스 상태 확인
```bash
# 서비스 목록
gcloud run services list --region asia-northeast3

# 상세 정보
gcloud run services describe radical-cardist-backend \
  --region asia-northeast3
```

### 서비스 삭제
```bash
# Backend 삭제
gcloud run services delete radical-cardist-backend \
  --region asia-northeast3

# Frontend 삭제
gcloud run services delete radical-cardist-frontend \
  --region asia-northeast3
```

## ⚠️ 주의사항

### 1. Vector DB 영속성
현재 구현은 MongoDB Atlas(또는 MongoDB 호스팅)의 `cards` 컬렉션에 임베딩을 저장합니다. 

### 2. Cold Start
- 트래픽이 없으면 인스턴스가 종료됨
- 첫 요청 시 10-30초 지연 발생 가능
- 최소 인스턴스 설정으로 해결 (비용 증가):
```bash
gcloud run services update radical-cardist-backend \
  --min-instances 1 \
  --region asia-northeast3
```

### 3. CORS 설정
현재 FastAPI는 모든 origin 허용 중. 프로덕션에서는 제한 필요:
```python
# main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend-url.run.app"],
    ...
)
```

## 🔐 보안 권장사항

### 1. Secret Manager 사용
환경 변수 대신 Secret Manager 사용 권장:

```bash
# Secret 생성
echo -n "your-openai-api-key" | \
  gcloud secrets create openai-api-key --data-file=-

# Cloud Run에서 사용
gcloud run services update radical-cardist-backend \
  --set-secrets OPENAI_API_KEY=openai-api-key:latest \
  --region asia-northeast3
```

### 2. 인증 추가
공개 서비스이므로 필요 시 인증 추가:
- Firebase Authentication
- Cloud Identity-Aware Proxy
- API Key 기반 인증

## 📈 CI/CD 설정 (선택사항)

GitHub Actions를 통한 자동 배포:

`.github/workflows/deploy.yml`:
```yaml
name: Deploy to Cloud Run

on:
  push:
    branches: [ main ]

jobs:
  deploy-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: google-github-actions/setup-gcloud@v1
        with:
          project_id: ${{ secrets.GCP_PROJECT_ID }}
          service_account_key: ${{ secrets.GCP_SA_KEY }}
      - run: ./deploy-backend.sh
```

## 🆘 트러블슈팅

### 배포 실패
```bash
# 빌드 로그 확인
gcloud builds list --limit 5

# 빌드 상세 로그
gcloud builds log BUILD_ID
```

### 메모리 부족
```bash
# 메모리 증가
gcloud run services update radical-cardist-backend \
  --memory 2Gi \
  --region asia-northeast3
```

### 타임아웃
```bash
# 타임아웃 증가
gcloud run services update radical-cardist-backend \
  --timeout 600 \
  --region asia-northeast3
```

## 📚 추가 리소스

- [Cloud Run 공식 문서](https://cloud.google.com/run/docs)
- [GCP 무료 티어](https://cloud.google.com/free)
- [Cloud Run 가격 계산기](https://cloud.google.com/products/calculator)

## 🎉 완료!

이제 Radical Cardist MVP가 클라우드에서 실행 중입니다!

문제가 발생하면 이슈를 등록해주세요.
