"""
유튜브 댓글 분석 대시보드 - 1단계 (댓글 수집)
- 사용자가 유튜브 영상 링크를 입력하면
  YouTube Data API v3로 댓글을 최대 100개까지 가져와 보여준다.
- 좋아요가 많은 순(order=relevance)으로 가져온 뒤, 다시 한 번 좋아요 순으로 정렬해서 보여준다.
"""

import streamlit as st
import pandas as pd
import requests
from urllib.parse import urlparse, parse_qs

# ------------------------------------------------------------------
# 1. 기본 페이지 설정
# ------------------------------------------------------------------
st.set_page_config(page_title="유튜브 댓글 분석", page_icon="💬", layout="wide")
st.title("💬 유튜브 댓글 분석 대시보드")
st.caption("1단계: 영상 링크를 입력하면 좋아요가 많은 댓글 순으로 최대 100개를 가져와요.")

# ------------------------------------------------------------------
# 2. 예시로 쓸 링크 두 개를 상수로 정의
# ------------------------------------------------------------------
EXAMPLE_URL_1 = "https://youtu.be/d95J8yzvjbQ?si=LfL5DLwCL8Pk077r"  # 딥마인드 다큐(영어 댓글)
EXAMPLE_URL_2 = "https://youtu.be/I9vK5EVTt0U?si=NEZ8L7MRuNvrzINa"  # 2002 월드컵 추억(한국어 댓글)

# ------------------------------------------------------------------
# 3. 입력창의 값을 관리하기 위해 session_state 사용
#    - 예시 버튼을 누르면 이 값을 바꿔서 입력창에 반영한다.
# ------------------------------------------------------------------
if "video_url" not in st.session_state:
    st.session_state.video_url = EXAMPLE_URL_1  # 입력창 기본값


def fill_example_1():
    st.session_state.video_url = EXAMPLE_URL_1


def fill_example_2():
    st.session_state.video_url = EXAMPLE_URL_2


# ------------------------------------------------------------------
# 4. 예시 버튼 두 개를 나란히 배치
# ------------------------------------------------------------------
btn_col1, btn_col2 = st.columns(2)
btn_col1.button(
    "예시 1 · 딥마인드 다큐(영어 댓글)",
    on_click=fill_example_1,
    use_container_width=True,
)
btn_col2.button(
    "예시 2 · 2002 월드컵 추억(한국어 댓글)",
    on_click=fill_example_2,
    use_container_width=True,
)

# ------------------------------------------------------------------
# 5. 링크 입력창
#    - key="video_url" 로 지정해두면 위 버튼들이 바꾼 session_state 값이
#      자동으로 이 입력창에 반영된다.
# ------------------------------------------------------------------
video_url = st.text_input("🔗 유튜브 영상 링크를 붙여넣으세요", key="video_url")

# ------------------------------------------------------------------
# 6. 인증키 불러오기 (절대 코드에 직접 쓰지 않음!)
#    Streamlit Cloud의 Settings > Secrets 에
#    YOUTUBE_API_KEY = "발급받은키" 형태로 등록해두어야 합니다.
# ------------------------------------------------------------------
try:
    YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]
except KeyError:
    st.error(
        "🔑 YOUTUBE_API_KEY가 설정되어 있지 않아요.\n\n"
        "Streamlit Cloud라면 'Manage app' → 'Settings' → 'Secrets'에서\n"
        'YOUTUBE_API_KEY = "발급받은_API_키" 를 추가해주세요.'
    )
    st.stop()


# ------------------------------------------------------------------
# 7. 링크에서 영상 ID를 뽑아내는 함수
#    - youtu.be/영상ID  형태 (짧은 링크)
#    - youtube.com/watch?v=영상ID  형태 (일반 링크)
#    - si=... 같은 부가 파라미터는 자연스럽게 무시된다.
# ------------------------------------------------------------------
def extract_video_id(url: str) -> str | None:
    if not url:
        return None

    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None

    host = (parsed.hostname or "").lower()

    # 1) youtu.be 짧은 링크: 경로 자체가 영상 ID (예: /d95J8yzvjbQVideoId)
    if host in ("youtu.be", "www.youtu.be"):
        video_id = parsed.path.lstrip("/")
        return video_id if video_id else None

    # 2) youtube.com/watch?v=영상ID 형태
    if host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        if parsed.path == "/watch":
            query_params = parse_qs(parsed.query)
            video_ids = query_params.get("v")
            if video_ids:
                return video_ids[0]
        # youtube.com/shorts/영상ID 같은 형태도 대비
        if parsed.path.startswith("/shorts/"):
            video_id = parsed.path.split("/shorts/")[-1]
            return video_id if video_id else None

    return None


video_id = extract_video_id(video_url)

if not video_id:
    st.warning("⚠️ 링크에서 영상 ID를 찾을 수 없어요. 유튜브 링크 형식을 다시 확인해주세요.")
    st.stop()

# ------------------------------------------------------------------
# 8. YouTube Data API v3 commentThreads 호출
#    - part=snippet, order=relevance(좋아요 많은 순), maxResults=100
# ------------------------------------------------------------------
API_URL = "https://www.googleapis.com/youtube/v3/commentThreads"

params = {
    "part": "snippet",
    "videoId": video_id,
    "order": "relevance",   # 최신순이 아니라 좋아요(관련도) 많은 순
    "maxResults": 100,
    "key": YOUTUBE_API_KEY,
}

with st.spinner("댓글을 가져오는 중이에요..."):
    try:
        response = requests.get(API_URL, params=params, timeout=10)
        data = response.json()
    except requests.exceptions.RequestException as e:
        st.error(
            "🚫 유튜브 서버에 연결하지 못했어요.\n\n"
            "인터넷 연결 상태를 확인한 뒤 새로고침 해주세요.\n\n"
            f"(자세한 오류: {e})"
        )
        st.stop()
    except ValueError:
        st.error("🚫 서버 응답을 해석할 수 없어요. 잠시 후 다시 시도해주세요.")
        st.stop()

# ------------------------------------------------------------------
# 9. 에러 응답 확인
#    - 응답에 "error" 필드가 있으면 실패한 것 (영상 없음, 댓글 사용 중지 등)
# ------------------------------------------------------------------
if "error" in data:
    error_info = data["error"]
    reasons = [err.get("reason", "") for err in error_info.get("errors", [])]
    message = error_info.get("message", "알 수 없는 오류")

    if "commentsDisabled" in reasons:
        friendly_message = "이 영상은 댓글 기능이 꺼져 있어서 댓글을 가져올 수 없어요."
    elif "videoNotFound" in reasons:
        friendly_message = "영상을 찾을 수 없어요. 링크가 올바른지 다시 확인해주세요."
    elif "quotaExceeded" in reasons:
        friendly_message = "오늘 API 사용량 한도를 다 써버렸어요. 내일 다시 시도해주세요."
    elif "keyInvalid" in reasons or "badRequest" in reasons:
        friendly_message = "API 키가 올바르지 않은 것 같아요. YOUTUBE_API_KEY 설정을 확인해주세요."
    else:
        friendly_message = "댓글을 가져오는 중 문제가 발생했어요."

    st.error(f"🚫 {friendly_message}\n\n(서버 응답: {message})")
    st.stop()

# ------------------------------------------------------------------
# 10. 댓글 목록 추출
# ------------------------------------------------------------------
items = data.get("items", [])

if not items:
    st.warning("😥 이 영상에는 댓글이 없거나, 가져올 수 있는 댓글이 없어요.")
    st.stop()

comments = []
for item in items:
    top_comment = item["snippet"]["topLevelComment"]["snippet"]
    comments.append(
        {
            "댓글": top_comment.get("textOriginal", ""),
            "좋아요": top_comment.get("likeCount", 0),
        }
    )

df = pd.DataFrame(comments)

# 좋아요 수 기준으로 다시 한 번 내림차순 정렬 (안전하게)
df = df.sort_values("좋아요", ascending=False).reset_index(drop=True)
df.index = df.index + 1  # 1부터 시작하는 순번

# ------------------------------------------------------------------
# 11. 결과 보여주기
# ------------------------------------------------------------------
st.divider()
st.metric(label="📥 가져온 댓글 개수", value=f"{len(df)}개")

st.subheader("📋 댓글 목록 (좋아요 많은 순)")
st.dataframe(
    df,
    use_container_width=True,
    column_config={
        "좋아요": st.column_config.NumberColumn(format="%d개"),
        "댓글": st.column_config.TextColumn(width="large"),
    },
)
