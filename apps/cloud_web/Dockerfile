# 스택 1 — Cloud Run 웹 UI 이미지 (경량: Playwright 없음)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 의존성 먼저 설치 (레이어 캐시). pillow / pillow-heif 는 self-contained wheel 사용.
COPY requirements.txt .
RUN pip install -r requirements.txt

# 앱 소스 (.dockerignore 로 .env·캐시 제외)
COPY . .

# Cloud Run 은 런타임에 $PORT(기본 8080)를 주입한다. app.py 가 os.environ["PORT"] 를 읽어
# 0.0.0.0:$PORT 로 바인딩한다.
ENV PORT=8080
EXPOSE 8080

CMD ["python", "app.py"]
