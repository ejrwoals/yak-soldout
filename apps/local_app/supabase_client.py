"""로컬 앱용 Supabase 클라이언트 팩토리.

anon key로 클라이언트를 만들고, 이후 사용자가 로그인(Google/이메일)하면 그 세션으로
RLS가 적용된다. 즉 로그인 전에는 auth.uid()가 없어 어떤 주문도 조회되지 않는다.
service_role key는 로컬 앱에 두지 않는다(RLS 우회 방지).
"""

import os

from dotenv import load_dotenv

from runtime_paths import DATA_DIR

# .env 로드 (실행 위치와 무관). 소스 실행이면 local_app/.env, 동결이면 exe 옆의 .env
load_dotenv(DATA_DIR / ".env")


def get_config() -> tuple[str, str]:
    """(SUPABASE_URL, SUPABASE_ANON_KEY) 반환. 미설정 시 명확히 실패."""
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_ANON_KEY", "").strip()
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_ANON_KEY 가 설정되지 않았습니다. "
            "local_app/.env 를 확인하세요 (.env.example 참고)."
        )
    return url, key


def create_supabase():
    """새 Supabase 클라이언트 생성. 반환된 client에 로그인 세션을 실어 사용한다."""
    from supabase import create_client

    url, key = get_config()
    return create_client(url, key)
