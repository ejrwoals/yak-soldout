# Cloud Run 배포 가이드 (스택 1)

`cloud_web/` 를 Docker 이미지로 빌드해 Google Cloud Run에 배포한다.
로컬 Docker 없이도 **Cloud Build가 서버에서 Dockerfile을 빌드**한다.

> **권장: 루트의 `./deploy.sh` 한 줄이면 최초 생성·업데이트·도메인 매핑까지 다 된다.**
> 아래는 그 스크립트가 하는 일의 수동 버전(참고용). 리전 `asia-northeast1`, 서비스 `yak-order`,
> 도메인 `yak-order.chajjaem.dev` 기준.

## 0. 사전 준비 (최초 1회)

```bash
gcloud auth login
gcloud config set project <YOUR_PROJECT_ID>
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  secretmanager.googleapis.com artifactregistry.googleapis.com
```

## 1. 시크릿 등록 (Secret Manager)

키를 이미지에 굽지 않고 런타임에 주입한다. `GEMINI_API_KEY`, `SUPABASE_SERVICE_KEY` 두 개.

```bash
# 값 입력 후 Ctrl+D
printf '%s' "<GEMINI_API_KEY 값>"      | gcloud secrets create GEMINI_API_KEY      --data-file=-
printf '%s' "<SUPABASE_SERVICE_KEY 값>" | gcloud secrets create SUPABASE_SERVICE_KEY --data-file=-
```

Cloud Run 런타임 서비스 계정에 시크릿 접근 권한 부여(프로젝트 번호 필요):

```bash
PROJECT_NUMBER=$(gcloud projects describe <YOUR_PROJECT_ID> --format='value(projectNumber)')
for S in GEMINI_API_KEY SUPABASE_SERVICE_KEY; do
  gcloud secrets add-iam-policy-binding $S \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
done
```

## 2. 배포

`--source cloud_web` 가 이 폴더의 Dockerfile로 이미지를 빌드해 배포한다.
공개키(URL·anon)는 평범한 env, 비밀키는 `--set-secrets`.

```bash
gcloud run deploy yak-order-web \
  --source cloud_web \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --set-env-vars "SUPABASE_URL=https://pdtsciusfgzvozohefbt.supabase.co,SUPABASE_ANON_KEY=<ANON_KEY>,GEMINI_MODEL=gemini-2.5-flash" \
  --set-secrets "GEMINI_API_KEY=GEMINI_API_KEY:latest,SUPABASE_SERVICE_KEY=SUPABASE_SERVICE_KEY:latest"
```

- `--allow-unauthenticated`: 앱 자체는 공개, 보안은 Supabase 로그인 + RLS가 담당.
- 배포가 끝나면 서비스 URL(예: `https://yak-order-xxxx.asia-northeast1.run.app`)이 출력된다.
- `$PORT` 는 Cloud Run이 자동 주입 → app.py가 그 포트로 바인딩(설정 불필요).

## 3. 배포 후: 로그인 리다이렉트 등록

발급된 Cloud Run URL을 Supabase에 등록해야 그 도메인에서 Google 로그인이 완료된다.

Supabase 대시보드 → Authentication → URL Configuration:
- **Redirect URLs** 에 `https://yak-order-xxxx.asia-northeast1.run.app/**` 추가
- **Site URL** 을 그 도메인으로 지정(또는 유지) — 개발용 localhost 는 그대로 둬도 됨

> Google Cloud Console의 OAuth redirect URI는 **Supabase 콜백**(`.../auth/v1/callback`)이라
> 그대로 두면 된다. 앱 도메인은 Google에 등록할 필요 없음(Supabase가 콜백을 처리).

## 4. 확인

```bash
curl https://yak-order.chajjaem.dev/api/healthz
# {"ok":true,"ocr_configured":true}
```

브라우저로 접속 → Google 로그인 → 업로드 → OCR → 저장까지 로컬과 동일하게 동작하면 완료.

## 재배포

코드 수정 후 2번의 `gcloud run deploy` 명령을 다시 실행하면 된다.
