# ===========================================
# PART 1 — 기본 설정 / CSS / SMTP / 공통 함수 / 데이터 로드
# ===========================================

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date
import smtplib
from email.message import EmailMessage
import os

# ========================
# 앱 전체 설정
# ========================
st.set_page_config(
    page_title="해지 VOC 통합 대시보드",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========================
# Session 초기값 설정
# ========================
if "login_type" not in st.session_state:
    st.session_state["login_type"] = None
if "login_user" not in st.session_state:
    st.session_state["login_user"] = None

# ========================
# 파일 경로
# ========================
DATA_FILE = "merged_v2.csv"
CONTACT_FILE = "contact_map.xlsx"
FEEDBACK_FILE = "feedback.csv"

# ========================
# 스타일(CSS)
# ========================
st.markdown("""
<style>
body, .stApp {
    background-color:#f5f6fa !important;
    font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.section-card {
    background:#fff; padding:18px; border-radius:12px;
    box-shadow:0 3px 10px rgba(0,0,0,0.05); margin-bottom:18px;
}
.metric-box {
    background:#fff; padding:18px; border-radius:14px;
    box-shadow:0 3px 10px rgba(0,0,0,0.08);
    text-align:center;
}
.login-card {
    width:360px; margin:auto; margin-top:80px;
    padding:30px; background:white;
    border-radius:12px; box-shadow:0 8px 18px rgba(0,0,0,0.1);
}
input, select, textarea {
    border-radius:8px !important;
}
</style>
""", unsafe_allow_html=True)

# ==========================
# SMTP 환경변수 (이미 설정됨)
# ==========================
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SENDER_NAME = os.getenv("SENDER_NAME", "해지VOC 관리자")

# ==========================
# 공통 유틸 함수
# ==========================
def clean_contract(x):
    """계약번호 숫자 8자리만 남김"""
    if pd.isna(x): return ""
    s = ''.join(filter(str.isdigit, str(x)))
    return s[:8]

def clean_fee(x):
    """월정료 정제 + 천단위 콤마 적용"""
    if pd.isna(x): return 0
    s = str(x).replace(",", "")
    num = "".join(ch for ch in s if ch.isdigit())
    if num == "": return 0
    return int(num)

def format_fee(num):
    """천단위 콤마"""
    try: return f"{int(num):,}"
    except: return "0"

def parse_date_safe(x):
    """모든 날짜 포맷을 안전하게 변환"""
    if pd.isna(x): return pd.NaT
    if isinstance(x, (datetime, pd.Timestamp)): return x
    try:
        return pd.to_datetime(x, errors="coerce")
    except:
        return pd.NaT

# ==========================
# 데이터 로드
# ==========================
@st.cache_data
def load_data():
    if not os.path.exists(DATA_FILE):
        st.error("❌ merged_v2.csv 파일이 없습니다.")
        return pd.DataFrame()

    df = pd.read_csv(DATA_FILE, encoding="utf-8-sig")

    # 계약번호 정제
    if "계약번호" in df.columns:
        df["계약번호_정제"] = df["계약번호"].apply(clean_contract)

    # 월정료 정제
    fee_col = [c for c in df.columns if "월정료" in c][0]
    df["월정료_raw"] = df[fee_col]
    df["월정료"] = df[fee_col].apply(clean_fee)

    # 날짜 파싱
    date_cols = [c for c in df.columns if "일" in c or "일자" in c or "시" in c]
    for col in date_cols:
        df[col] = df[col].apply(parse_date_safe)

    # B열 체미매칭 컬럼 기준
    if df.columns[1] == "체미매칭":
        df["매칭"] = df["체미매칭"].apply(lambda x: "X" if str(x).strip().upper()=="X" else "O")
    else:
        df["매칭"] = "O"

    return df

# ==========================
# 담당자 파일 로드
# ==========================
@st.cache_data
def load_contact_map():
    if not os.path.exists(CONTACT_FILE):
        st.warning("⚠ contact_map.xlsx 없음 → 담당자 알림 기능 제한됨")
        return pd.DataFrame()
    df_c = pd.read_excel(CONTACT_FILE)
    df_c = df_c.rename(columns={
        df_c.columns[0]: "담당자",
        df_c.columns[1]: "이메일",
        df_c.columns[2]: "휴대폰",
    })
    return df_c

# ==========================
# 활동로그 로드/저장
# ==========================
@st.cache_data
def load_feedback():
    if not os.path.exists(FEEDBACK_FILE):
        return pd.DataFrame(columns=["계약번호", "내용", "등록자", "비고", "등록일"])
    return pd.read_csv(FEEDBACK_FILE, encoding="utf-8-sig")

def save_feedback(df):
    df.to_csv(FEEDBACK_FILE, index=False, encoding="utf-8-sig")

# ===========================================
# PART 2 — 데이터 전처리 + 글로벌 필터 + KPI 구성
# ===========================================

df_raw = load_data()
contact_df = load_contact_map()
feedback_df = load_feedback()

if df_raw.empty:
    st.stop()

# ---------------------------------------
# 1) 기본 전처리
# ---------------------------------------
df = df_raw.copy()

# 지사 전처리
if "관리지사" in df.columns:
    df["관리지사"] = df["관리지사"].astype(str).str.replace("지사", "").str.strip()
else:
    df["관리지사"] = "미정"

# 담당자 컬럼 정규화
mgr_cols = [c for c in df.columns if "담당" in c]
if mgr_cols:
    df["담당자"] = df[mgr_cols[0]].astype(str).str.strip()
else:
    df["담당자"] = "미정"

# 경과일 계산
if "접수일" in df.columns:
    df["접수일"] = df["접수일"].apply(parse_date_safe)
    df["경과일"] = df["접수일"].apply(lambda x: (date.today() - x.date()).days if pd.notna(x) else np.nan)
else:
    df["경과일"] = np.nan

# 리스크 등급
def calc_risk(days):
    if pd.isna(days): return "LOW"
    if days <= 3: return "HIGH"
    if days <= 10: return "MEDIUM"
    return "LOW"

df["리스크"] = df["경과일"].apply(calc_risk)

# ---------------------------------------
# 2) 🔎 글로벌 필터 UI
# ---------------------------------------
st.sidebar.header("🔎 글로벌 필터")

# 지사 선택
branches = ["전체"] + sorted(df["관리지사"].unique().tolist())
sel_branch = st.sidebar.selectbox("🏢 지사", branches)

# 담당자 선택
mgr_list = ["전체"] + sorted(df["담당자"].unique().tolist())
sel_mgr = st.sidebar.selectbox("👤 담당자", mgr_list)

# 매칭 여부
sel_match = st.sidebar.multiselect(
    "🔍 매칭여부",
    ["O", "X"],
    default=["X"]
)

# 리스크 필터
risk_list = ["HIGH", "MEDIUM", "LOW"]
sel_risk = st.sidebar.multiselect(
    "⚠ 리스크 등급",
    risk_list,
    default=risk_list
)

# 월정료 필터 (만원 단위)
fee_min, fee_max = st.sidebar.slider(
    "💰 월정료 범위 (만원)",
    0, 100, (0, 100)
)

# 날짜 필터
date_range = st.sidebar.date_input(
    "📅 접수일 범위",
    [date.today(), date.today()]
)

# ---------------------------------------
# 3) 필터 적용
# ---------------------------------------
df_view = df.copy()

if sel_branch != "전체":
    df_view = df_view[df_view["관리지사"] == sel_branch]

if sel_mgr != "전체":
    df_view = df_view[df_view["담당자"] == sel_mgr]

df_view = df_view[df_view["매칭"].isin(sel_match)]
df_view = df_view[df_view["리스크"].isin(sel_risk)]
df_view = df_view[(df_view["월정료"] >= fee_min*10000) & (df_view["월정료"] <= fee_max*10000)]

if len(date_range) == 2:
    start_d, end_d = date_range
    if "접수일" in df_view.columns:
        df_view = df_view[
            (df_view["접수일"] >= pd.to_datetime(start_d))
            & (df_view["접수일"] <= pd.to_datetime(end_d) + pd.Timedelta(days=1))
        ]

# ---------------------------------------
# 4) KPI 숫자 카드
# ---------------------------------------
with st.container():
    k1, k2, k3, k4 = st.columns(4)

    total_cnt = len(df_view)
    x_cnt = len(df_view[df_view["매칭"] == "X"])
    fee_sum = df_view["월정료"].sum()
    avg_days = df_view["경과일"].mean()

    k1.metric("총 VOC 건수", f"{total_cnt:,}")
    k2.metric("비매칭(X) 건수", f"{x_cnt:,}")
    k3.metric("월정료 합계(원)", f"{fee_sum:,.0f}")
    k4.metric("평균 경과일", f"{avg_days:.1f}" if not np.isnan(avg_days) else "-")    

# ===========================================
# PART 3 — 로그인 시스템 + 권한 기반 데이터 접근
# ===========================================

# 로그인 상태 초기화
if "login_role" not in st.session_state:
    st.session_state["login_role"] = None
if "login_user" not in st.session_state:
    st.session_state["login_user"] = None
if "login_branch" not in st.session_state:
    st.session_state["login_branch"] = None


# -------------------------------------------
# 로그인 UI CSS
# -------------------------------------------
st.markdown("""
<style>
.login-box {
    max-width: 430px;
    margin: 80px auto;
    padding: 30px;
    background: white;
    border-radius: 16px;
    box-shadow: 0 6px 20px rgba(15,23,42,0.15);
}
.login-title {
    font-size: 26px;
    font-weight: 700;
    text-align: center;
    margin-bottom: 20px;
}
</style>
""", unsafe_allow_html=True)


# -------------------------------------------
# 로그인 폼 함수
# -------------------------------------------
def login_page():
    st.markdown('<div class="login-box">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">🔐 로그인</div>', unsafe_allow_html=True)

    tab_admin, tab_branch, tab_user, tab_dashboard = st.tabs(
        ["관리자", "중간관리자", "담당자", "대시보드(로그인 없음)"]
    )

    # 관리자 로그인
    with tab_admin:
        pw = st.text_input("관리자 비밀번호", type="password")
        if st.button("관리자 로그인"):
            if pw == "C3A":   # 관리자코드
                st.session_state["login_role"] = "admin"
                st.session_state["login_user"] = "ADMIN"
                st.success("관리자 로그인 성공")
                st.rerun()
            else:
                st.error("비밀번호가 잘못되었습니다.")

    # 중간관리자 로그인
    with tab_branch:
        branch_list = sorted(df["관리지사"].unique().tolist())
        sel_b = st.selectbox("지사 선택", branch_list)
        pw = st.text_input("지사 비밀번호", type="password")

        # 예: 강북=C001, 고양=C002 …
        BRANCH_CODE = {
            "중앙": "C001", "강북": "C002", "서대문": "C003", "고양": "C004",
            "의정부": "C005", "남양주": "C006", "강릉": "C007", "원주": "C008"
        }

        if st.button("중간관리자 로그인"):
            if pw == BRANCH_CODE.get(sel_b, ""):
                st.session_state["login_role"] = "branch"
                st.session_state["login_user"] = f"{sel_b}_관리자"
                st.session_state["login_branch"] = sel_b
                st.success(f"{sel_b} 지사 관리자 로그인 성공")
                st.rerun()
            else:
                st.error("비밀번호 오류")

    # 담당자 로그인
    with tab_user:
        name = st.text_input("담당자명")
        tel = st.text_input("휴대폰 뒷 4자리", type="password")

        if st.button("담당자 로그인"):
            # 담당자 매핑에서 휴대폰 확인
            user_phone = contact_df.get(name, {}).get("전화", "")
            if user_phone and user_phone[-4:] == tel:
                st.session_state["login_role"] = "user"
                st.session_state["login_user"] = name
                st.session_state["login_branch"] = df[df["담당자"] == name]["관리지사"].iloc[0]
                st.success(f"{name} 님 로그인 성공")
                st.rerun()
            else:
                st.error("사용자 정보가 없습니다.")

    # 로그인 없이도 대시보드 접근 가능
    with tab_dashboard:
        if st.button("대시보드 바로보기"):
            st.session_state["login_role"] = "viewer"
            st.session_state["login_user"] = "VIEWER"
            st.success("로그인 없이 대시보드 진입")
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)


# -------------------------------------------
# 로그인 필요 시 로그인 페이지로 이동
# -------------------------------------------
if st.session_state["login_role"] is None:
    login_page()
    st.stop()


# -------------------------------------------
# 권한 기반 데이터 필터링
# -------------------------------------------
role = st.session_state["login_role"]
user = st.session_state["login_user"]
branch = st.session_state["login_branch"]

df_role = df.copy()

if role == "branch":   # 중간관리자 → 해당 지사 데이터만 표시
    df_role = df_role[df_role["관리지사"] == branch]

elif role == "user":   # 담당자 → 본인 데이터만 표시
    df_role = df_role[df_role["담당자"] == user]

elif role == "admin":
    pass  # 전체 가능

elif role == "viewer":  # 로그인 없이도 전체 데이터 볼 수 있음
    pass


# ---------------------------------------------------------
# 시각화 기본 UI 프레임
# ---------------------------------------------------------
st.markdown("## 📊 해지 VOC 대시보드")

tab_viz, tab_table, tab_log, tab_setting = st.tabs(
    ["📈 시각화", "📘 VOC 테이블", "📝 활동내역", "⚙ 관리자"]
)    

# ===========================================
# PART 4 — 대시보드 시각화 + 활동내역 등록 + 관리자 기능
# ===========================================

import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime


# -------------------------------------------
# 📊 탭 1 — 시각화 모듈
# -------------------------------------------
with tab_viz:

    st.markdown("### 📌 주요 지표")
    c1, c2, c3, c4 = st.columns(4)

    c1.metric("전체 접수 건수", f"{len(df_role):,}")
    c2.metric("고객 수(유니크)", f"{df_role['계약번호_정제'].nunique():,}")
    c3.metric("비매칭 건수", f"{(df_role['매칭여부']=='X').sum():,}")
    c4.metric("매칭률", f"{100 - (df_role['매칭여부']=='X').mean()*100:.1f}%")

    st.markdown("---")

    # -----------------------------
    # 지사별 리스크 적층막대
    # -----------------------------
    st.markdown("## 🏢 지사별 리스크 현황 (적층 막대)")

    risk_df = (
        df_role.groupby(["관리지사","리스크"])
        .size()
        .reset_index(name="건수")
    )

    if not risk_df.empty:
        fig = px.bar(
            risk_df,
            x="관리지사",
            y="건수",
            color="리스크",
            barmode="stack",
            text="건수",
            color_discrete_map={"HIGH":"#d62728","MEDIUM":"#ff7f0e","LOW":"#2ca02c"}
        )
        fig.update_layout(height=380)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("표시할 데이터가 없습니다.")

    st.markdown("---")

    # -----------------------------
    # 담당자 TOP 20
    # -----------------------------
    st.markdown("## 👤 담당자별 비매칭 TOP 20")

    top_mgr = (
        df_role[df_role["매칭여부"]=="X"]
        .groupby("담당자")["계약번호_정제"]
        .nunique()
        .sort_values(ascending=False)
        .head(20)
        .reset_index(name="계약수")
    )

    fig = px.bar(
        top_mgr,
        x="담당자",
        y="계약수",
        text="계약수",
        color="계약수",
        color_continuous_scale="Blues",
    )
    fig.update_layout(height=380)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # -----------------------------
    # 일별 추이
    # -----------------------------
    st.markdown("## 📅 일별 접수 추이")

    daily_trend = (
        df_role.groupby(df_role["접수일"].dt.date)["계약번호_정제"]
        .nunique()
        .reset_index(name="건수")
    )

    fig = px.line(
        daily_trend,
        x="접수일",
        y="건수",
        markers=True,
    )
    fig.update_layout(height=330)
    st.plotly_chart(fig, use_container_width=True)
