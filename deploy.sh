#!/usr/bin/env bash
#
# 스택 1 (cloud_web) → Google Cloud Run 배포.
# 최초 생성 / 코드 수정 후 업데이트 / 도메인 매핑을 모두 이 한 줄로 처리한다:
#
#     ./deploy.sh
#
# - gcloud run deploy 는 서비스가 없으면 생성, 있으면 업데이트(동일 명령).
# - 시크릿(GEMINI_API_KEY, SUPABASE_SERVICE_KEY)은 cloud_web/.env 값으로 동기화.
# - 도메인 매핑은 없을 때만 생성.
#
# 사전: gcloud CLI 설치 + `gcloud auth login` 완료, 프로젝트 결제 활성화.
#
set -euo pipefail
cd "$(dirname "$0")"

# ===================== 설정 =====================
PROJECT_ID="gen-lang-client-0011046539"
REGION="asia-northeast1"
SERVICE="yak-order"
DOMAIN="yak-order.chajjaem.dev"
SRC_DIR="cloud_web"
ENV_FILE="$SRC_DIR/.env"
# ================================================

# ---- .env 로드 (키 값은 여기서 읽는다) ----
[ -f "$ENV_FILE" ] || { echo "❌ $ENV_FILE 가 없습니다."; exit 1; }
set -a; source "$ENV_FILE"; set +a
for v in SUPABASE_URL SUPABASE_ANON_KEY GEMINI_API_KEY SUPABASE_SERVICE_KEY; do
  [ -n "${!v:-}" ] || { echo "❌ $ENV_FILE 에 $v 값이 비어 있습니다."; exit 1; }
done
GEMINI_MODEL="${GEMINI_MODEL:-gemini-2.5-flash}"

echo "▶ 프로젝트 $PROJECT_ID · 리전 $REGION · 서비스 $SERVICE"
gcloud config set project "$PROJECT_ID" >/dev/null

# ---- 필요한 API (idempotent) ----
echo "▶ API 활성화 확인…"
gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com \
  secretmanager.googleapis.com artifactregistry.googleapis.com >/dev/null

# ---- 시크릿 동기화 (.env 값을 최신 버전으로) ----
sync_secret() {
  local name="$1" value="$2" current
  if ! gcloud secrets describe "$name" >/dev/null 2>&1; then
    echo "  · 시크릿 생성 $name"
    gcloud secrets create "$name" --replication-policy=automatic >/dev/null
    printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- >/dev/null
  else
    current="$(gcloud secrets versions access latest --secret="$name" 2>/dev/null || true)"
    if [ "$current" != "$value" ]; then
      echo "  · 시크릿 갱신 $name"
      printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- >/dev/null
    fi
  fi
}
echo "▶ 시크릿 동기화…"
sync_secret GEMINI_API_KEY      "$GEMINI_API_KEY"
sync_secret SUPABASE_SERVICE_KEY "$SUPABASE_SERVICE_KEY"

# 런타임 서비스 계정에 시크릿 접근 권한 (idempotent)
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for s in GEMINI_API_KEY SUPABASE_SERVICE_KEY; do
  gcloud secrets add-iam-policy-binding "$s" \
    --member="serviceAccount:$RUNTIME_SA" \
    --role="roles/secretmanager.secretAccessor" >/dev/null 2>&1 || true
done

# ---- 배포 (생성/업데이트 동일) ----
echo "▶ 빌드 & 배포 (Cloud Build → Cloud Run)…"
gcloud run deploy "$SERVICE" \
  --source "$SRC_DIR" \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-env-vars "SUPABASE_URL=${SUPABASE_URL},SUPABASE_ANON_KEY=${SUPABASE_ANON_KEY},GEMINI_MODEL=${GEMINI_MODEL}" \
  --set-secrets "GEMINI_API_KEY=GEMINI_API_KEY:latest,SUPABASE_SERVICE_KEY=SUPABASE_SERVICE_KEY:latest"

RUN_URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
echo "✔ 배포 완료 · Cloud Run URL: $RUN_URL"

# ---- 커스텀 도메인 매핑 (없을 때만) ----
if gcloud beta run domain-mappings describe --domain "$DOMAIN" --region "$REGION" >/dev/null 2>&1; then
  echo "▶ 도메인 매핑 이미 존재: $DOMAIN"
else
  echo "▶ 도메인 매핑 생성: $DOMAIN → $SERVICE"
  if gcloud beta run domain-mappings create --service "$SERVICE" --domain "$DOMAIN" --region "$REGION"; then
    echo "  ⚠ 아래 대상으로 DNS 레코드를 추가하세요 (와일드카드가 없다면):"
    gcloud beta run domain-mappings describe --domain "$DOMAIN" --region "$REGION" \
      --format='value(status.resourceRecords[].rrdata)' || true
  else
    echo "  ⚠ 도메인 매핑 실패 — chajjaem.dev 가 이 프로젝트에서 검증됐는지 확인 필요(아래 안내 참고)."
  fi
fi

echo ""
echo "── 완료 ──"
echo "앱:            https://$DOMAIN   (DNS 반영 후)"
echo "Cloud Run URL: $RUN_URL"
echo ""
echo "최초 배포라면: Supabase → Authentication → URL Configuration → Redirect URLs 에"
echo "  https://$DOMAIN/**   를 추가하세요 (Google 로그인 리다이렉트용)."
