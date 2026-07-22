"""
유튜브 댓글 AI 분석 앱 - 1단계 (댓글 수집 + AI 세 줄 요약)
- 유튜브 영상 링크를 입력하면 YouTube Data API v3로 댓글을 최대 100개까지 가져온다.
- 좋아요가 많은 순(order=relevance)으로 가져온 뒤, 다시 한 번 좋아요 순으로 정렬해서 보여준다.
- 'AI 세 줄 요약' 버튼을 누르면 Solar API(solar-open2)가 댓글 전체 반응을 요약해준다.
"""

import streamlit as st
import pandas as pd
import requests
from urllib.parse import urlparse, parse_qs
from openai import OpenAI, APIError, APIConnectionError

# ------------------------------------------------------------------
# 1. 기본 페이지 설정
# ------------------------------------------------------------------
st.set_page_config(page_title="유튜브 댓글 AI 분석", page_icon="💬", layout="wide")
st.title("💬 유튜브 댓글 AI 분석 앱")
st.caption("1단계: 댓글을 가져오고, AI가 전체 반응을 세 줄로 요약해줘요.")

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
# 6. 인증키 두 개 불러오기 (절대 코드에 직접 쓰지 않음!)
#    Streamlit Cloud의 Settings > Secrets 에
#    YOUTUBE_API_KEY, SOLAR_API_KEY 를 각각 등록해두어야 합니다.
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

try:
    SOLAR_API_KEY = st.secrets["SOLAR_API_KEY"]
except KeyError:
    st.error(
        "🔑 SOLAR_API_KEY가 설정되어 있지 않아요.\n\n"
        "Streamlit Cloud라면 'Manage app' → 'Settings' → 'Secrets'에서\n"
        'SOLAR_API_KEY = "발급받은_API_키" 를 추가해주세요.'
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

    # 1) youtu.be 짧은 링크: 경로 자체가 영상 ID
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
YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3/commentThreads"

params = {
    "part": "snippet",
    "videoId": video_id,
    "order": "relevance",   # 최신순이 아니라 좋아요(관련도) 많은 순
    "maxResults": 100,
    "key": YOUTUBE_API_KEY,
}

with st.spinner("댓글을 가져오는 중이에요..."):
    try:
        response = requests.get(YOUTUBE_API_URL, params=params, timeout=10)
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
        friendly_message = "YouTube API 키가 올바르지 않은 것 같아요. YOUTUBE_API_KEY 설정을 확인해주세요."
    else:
        friendly_message = "댓글을 가져오는 중 문제가 발생했어요."

    st.error(f"🚫 {friendly_message}\n\n(서버 응답: {message})")
    st.stop()

# ------------------------------------------------------------------
# 10. 댓글 목록 추출 + 세션에 저장
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
df = df.sort_values("좋아요", ascending=False).reset_index(drop=True)
df.index = df.index + 1  # 1부터 시작하는 순번

# 다른 영상으로 다시 검색해도 헷갈리지 않도록, 지금 보고 있는 영상 ID와 함께 세션에 저장
st.session_state.comments_df = df
st.session_state.comments_video_id = video_id

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

# ------------------------------------------------------------------
# 12. AI 세 줄 요약
#     - Solar API(solar-open2)를 openai 라이브러리로 호출
#     - 추론(생각) 기능은 꺼서 빠르게 응답받는다 (reasoning_effort="none")
# ------------------------------------------------------------------
st.divider()
st.subheader("🤖 AI 세 줄 요약")

solar_client = OpenAI(
    api_key=SOLAR_API_KEY,
    base_url="https://api.upstage.ai/v1",
)
SOLAR_MODEL_NAME = "solar-open2"  # 모델 이름은 반드시 이 그대로 사용

if st.button("✨ AI 세 줄 요약 만들기", use_container_width=True):
    # 댓글이 너무 많으면 프롬프트가 지나치게 길어질 수 있으니
    # 가져온 댓글(최대 100개)을 번호를 매겨 하나의 텍스트로 합친다.
    joined_comments = "\n".join(
        f"{i}. {text}" for i, text in enumerate(df["댓글"].tolist(), start=1)
    )

    system_prompt = (
        "너는 유튜브 댓글 반응을 분석하는 애널리스트야. "
        "여러 댓글을 읽고 시청자들의 전체적인 반응을 한국어로만 요약해."
    )
    user_prompt = (
        "아래는 한 유튜브 영상에 달린 댓글 목록이야. "
        "이 댓글들을 모두 읽고 전체 반응을 정확히 세 줄로 요약해줘.\n"
        "- 1~2번째 줄: 댓글에서 드러나는 시청자들의 전반적인 반응과 주요 의견\n"
        "- 마지막 3번째 줄: 긍정/부정 반응의 대략적인 비율을 백분율로 추정해서 "
        "'긍정 70% / 부정 30%'처럼 표시\n\n"
        f"[댓글 목록]\n{joined_comments}"
    )

    with st.spinner("AI가 댓글을 읽고 요약하는 중이에요..."):
        try:
            completion = solar_client.chat.completions.create(
                model=SOLAR_MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                extra_body={"reasoning_effort": "none"},  # 추론(생각) 기능 끄기 → 빠른 응답
            )
            summary_text = completion.choices[0].message.content
            st.success(summary_text)

        except APIConnectionError:
            st.error(
                "🚫 Solar API 서버에 연결하지 못했어요.\n\n"
                "인터넷 연결 상태를 확인한 뒤 다시 시도해주세요."
            )
        except APIError as e:
            st.error(
                "🚫 AI 요약을 만드는 중 문제가 발생했어요.\n\n"
                "API 키가 올바른지, 또는 사용량 한도를 넘기지 않았는지 확인해주세요.\n\n"
                f"(자세한 오류: {e})"
            )
        except Exception as e:
            st.error(
                "🚫 알 수 없는 오류가 발생했어요. 잠시 후 다시 시도해주세요.\n\n"
                f"(자세한 오류: {e})"
            )
