# --------------------------------------------
# PART 1 — Imports / Settings / File Loads / Preprocessing
# --------------------------------------------
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date
import os
import smtplib
from email.message import EmailMessage

# ============================================
# Streamlit 기본 설정
# ============================================
st.set_page_config(
    page_title="해지 VOC 대시보드 v2",
    layout="wide"
)

# ============================================
# 파일 경로 설정
# ============================================
DATA_FILE = "merged_v2.csv"           # 새로운 VOC 통합데이터
CONTACT_FILE = "contact_map.xlsx"     # 담당자 Mapping
FEEDBACK_FILE = "feedback.csv"        # 활동내역 저장 파일

# ============================================
# SMTP 환경변수 (Streamlit Cloud Secrets)
# ============================================
SMTP_HOST = st.secrets["SMTP_HOST"]
SMTP_PORT = int(st.secrets["SMTP_PORT"])
SMTP_USER = st.secrets["SMTP_USER"]
SMTP_PASSWORD = st.secrets["SMTP_PASSWORD"]
SENDER_NAME = st.secrets["SENDER_NAME"]

# ============================================
# 공통 함수
# ============================================
def safe_str(x):
    return "" if pd.isna(x) else str(x).strip()

def clean_contract_number(x):
    """계약번호 숫자만 남겨 8자리로 통일"""
    if pd.isna(x):
        return ""
    s = "".join([c for c in str(x) if c.isdigit()])
    return s[:8] if len(s) >= 8 else s

def clean_monthly_fee(x):
    """월정료 원단위 → 천원단위로 변환 & 콤마포맷"""
    if pd.isna(x):
        return np.nan
    s = str(x).replace(",", "").strip()
    if not s.isdigit():
        return np.nan
    v = int(s)
    v = round(v / 1000)     # 원단위 → 천원단위
    return v

def parse_date_safe(x):
    """강력 날짜 파싱"""
    if pd.isna(x):
        return pd.NaT

    if isinstance(x, (datetime, pd.Timestamp)):
        return x

    s = str(x).strip()
    formats = [
        "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
        "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M",
        "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except:
            pass

    try:
        return pd.to_datetime(s, errors="coerce")
    except:
        return pd.NaT

# ============================================
# 데이터 불러오기
# ============================================
@st.cache_data
def load_data():
    if not os.path.exists(DATA_FILE):
        st.error("❌ merged_v2.csv 파일을 찾을 수 없습니다.")
        return pd.DataFrame()

    df = pd.read_csv(DATA_FILE, dtype=str)

    # 계약번호 정제
    df["계약번호"] = df["계약번호"].apply(clean_contract_number)

    # 비매칭 여부(B열)
    if "매칭" in df.columns:
        df["매칭여부"] = df["매칭"].apply(lambda x: "X" if str(x).upper() == "X" else "O")
    else:
        df["매칭여부"] = "O"

    # 월정료 처리
    if "월정료" in df.columns:
        df["월정료_천원"] = df["월정료"].apply(clean_monthly_fee)

    # 날짜 파싱
    if "접수일" in df.columns:
        df["접수일"] = df["접수일"].apply(parse_date_safe)

    return df

# ============================================
# 담당자 Mapping 불러오기
# ============================================
@st.cache_data
def load_contact_map():
    if not os.path.exists(CONTACT_FILE):
        st.warning("⚠ contact_map.xlsx 파일이 존재하지 않습니다.")
        return pd.DataFrame()

    df = pd.read_excel(CONTACT_FILE)
    df.columns = [c.strip() for c in df.columns]

    # 담당자 기본 컬럼명 정제
    name_col = [c for c in df.columns if "담당" in c or "성명" in c][0]
    phone_col = [c for c in df.columns if "휴대" in c or "연락" in c][0]
    email_col = [c for c in df.columns if "메일" in c or "email" in c.lower()][0]

    df.rename(columns={
        name_col: "담당자",
        phone_col: "전화번호",
        email_col: "이메일"
    }, inplace=True)

    return df

# ============================================
# 활동내역 로드
# ============================================
@st.cache_data
def load_feedback():
    if not os.path.exists(FEEDBACK_FILE):
        return pd.DataFrame(columns=["계약번호", "내용", "등록자", "등록일시", "비고"])
    return pd.read_csv(FEEDBACK_FILE, dtype=str)

def save_feedback(df):
    df.to_csv(FEEDBACK_FILE, index=False, encoding="utf-8-sig")

# --------------------------------------------
# PART 2 — 로그인 & 권한 시스템
# --------------------------------------------

# 세션 상태 초기화
if "login_type" not in st.session_state:
    st.session_state["login_type"] = None
if "login_user" not in st.session_state:
    st.session_state["login_user"] = None
if "login_branch" not in st.session_state:
    st.session_state["login_branch"] = None

# ----------------------------------------------------------
# ◼ 로그인 종류 정의
# ----------------------------------------------------------
LOGIN_TYPES = {
    "admin": "최고관리자",
    "branch_admin": "중간관리자(지사)",
    "user": "담당자 로그인",
    "public": "대시보드 공개모드"
}

# ----------------------------------------------------------
# ◼ 중간관리자(지사) 비밀번호 테이블
# ----------------------------------------------------------
BRANCH_ADMIN_PW = {
    "중앙": "C001",
    "강북": "C002",
    "서대문": "C003",
    "고양": "C004",
    "의정부": "C005",
    "남양주": "C006",
    "강릉": "C007",
    "원주": "C008"
}

# ----------------------------------------------------------
# ◼ 로그인 UI 구성
# ----------------------------------------------------------
def login_screen(contact_df):

    st.markdown("## 🔐 로그인")

    tab_admin, tab_branch, tab_user, tab_public = st.tabs(
        ["최고관리자", "지사 중간관리자", "담당자 로그인", "대시보드 공개모드"]
    )

    # -----------------------------
    # 1) 최고관리자 로그인
    # -----------------------------
    with tab_admin:
        admin_pw = st.text_input("관리자 비밀번호", type="password")
        if st.button("로그인 (관리자)"):
            if admin_pw == "C3A":
                st.session_state["login_type"] = "admin"
                st.session_state["login_user"] = "ADMIN"
                st.success("관리자 로그인 성공")
                st.rerun()
            else:
                st.error("비밀번호가 올바르지 않습니다.")

    # -----------------------------
    # 2) 지사 중간관리자
    # -----------------------------
    with tab_branch:
        branch = st.selectbox("지사 선택", list(BRANCH_ADMIN_PW.keys()))
        pw = st.text_input("중간관리자 비밀번호", type="password")

        if st.button("로그인 (지사관리자)"):
            if pw == BRANCH_ADMIN_PW[branch]:
                st.session_state["login_type"] = "branch_admin"
                st.session_state["login_user"] = branch + "_ADMIN"
                st.session_state["login_branch"] = branch
                st.success(f"{branch} 지사 중간관리자 로그인 성공!")
                st.rerun()
            else:
                st.error("비밀번호가 일치하지 않습니다.")

    # -----------------------------
    # 3) 담당자 로그인
    #     → contact_map.xlsx 에서 전화번호 뒷 4자리로 인증
    # -----------------------------
    with tab_user:

        df = contact_df.copy()
        df["전화번호"] = df["전화번호"].astype(str)

        name = st.text_input("담당자 이름")
        pw = st.text_input("전화번호 뒷 4자리", type="password")

        if st.button("로그인 (담당자)"):

            row = df[df["담당자"] == name]

            if row.empty:
                st.error("등록되지 않은 담당자입니다.")
            else:
                real_phone = row.iloc[0]["전화번호"]
                last4 = real_phone[-4:] if len(real_phone) >= 4 else None

                if pw == last4:
                    st.session_state["login_type"] = "user"
                    st.session_state["login_user"] = name
                    st.success(f"{name} 담당자 로그인 성공!")
                    st.rerun()
                else:
                    st.error("전화번호 뒷 4자리가 일치하지 않습니다.")

    # -----------------------------
    # 4) 대시보드 공개모드
    # -----------------------------
    with tab_public:
        st.info("로그인 없이 전체 대시보드를 조회할 수 있는 모드입니다. (수정불가)")
        if st.button("대시보드 보기"):
            st.session_state["login_type"] = "public"
            st.session_state["login_user"] = "PUBLIC"
            st.rerun()


# ----------------------------------------------------------
# ◼ 사용자별 접근 가능한 데이터 필터링
# ----------------------------------------------------------
def filter_by_role(df):

    login_type = st.session_state["login_type"]
    login_user = st.session_state["login_user"]
    login_branch = st.session_state.get("login_branch")

    df_role = df.copy()

    # 최고관리자 → 전체 접근
    if login_type == "admin":
        return df_role

    # 공용모드 → 전체 조회 가능, 수정 불가
    if login_type == "public":
        return df_role

    # 지사 중간관리자 → 해당 지사 전체 데이터
    if login_type == "branch_admin":
        if "관리지사" in df_role.columns:
            return df_role[df_role["관리지사"] == login_branch]
        else:
            return df_role

    # 담당자 로그인 → 담당자 본인 데이터만 보기
    if login_type == "user":
        if "담당자" in df_role.columns:
            return df_role[df_role["담당자"] == login_user]
        elif "구역담당자" in df_role.columns:
            return df_role[df_role["구역담당자"] == login_user]
        else:
            return df_role  # 컬럼 없을 경우 전체 조회 fallback

    return df_role 

# ------------------------------------------------------------
# PART 3 — 대시보드 화면 구성 (필터 + KPI + 시각화)
# ------------------------------------------------------------

st.markdown("## 📊 해지 VOC 통합 대시보드")

df_view = df.copy()
df_view = filter_by_role(df_view)   # 로그인 권한 필터 적용


# ------------------------------------------------------------
# 📌 1) 계약번호 정제 (8자리 숫자)
# ------------------------------------------------------------
def clean_contract(x):
    if pd.isna(x):
        return ""
    s = re.sub(r"[^0-9]", "", str(x))
    return s[:8] if len(s) >= 8 else s

df_view["계약번호_정제"] = df_view["계약번호"].apply(clean_contract) \
    if "계약번호" in df_view.columns else df_view.get("계약번호_정제", "")


# ------------------------------------------------------------
# 📌 2) 월정료(원) → 천원단위 정제
# ------------------------------------------------------------
def parse_fee(v):
    if pd.isna(v):
        return 0
    s = str(v).replace(",", "").strip()
    if not s.isdigit():
        return 0
    w = int(s)
    return round(w / 1000)

fee_col = None
for col in ["월정료", "KTT월정료", "KTT월정료(조정)", "시설_KTT월정료(조정)"]:
    if col in df_view.columns:
        fee_col = col
        break

if fee_col:
    df_view["월정료_천원"] = df_view[fee_col].apply(parse_fee)
else:
    df_view["월정료_천원"] = 0


# ------------------------------------------------------------
# 📌 3) 글로벌 필터 UI
# ------------------------------------------------------------
st.sidebar.markdown("### 🎛 글로벌 필터")

branches = sorted(df_view["관리지사"].dropna().unique()) \
    if "관리지사" in df_view.columns else []

sel_branches = st.sidebar.multiselect("📍 지사 선택", ["전체"] + branches, default=["전체"])

managers = sorted(df_view["담당자"].dropna().unique()) \
    if "담당자" in df_view.columns else []

sel_managers = st.sidebar.multiselect("👤 담당자 선택", ["전체"] + managers, default=["전체"])

risk_levels = ["HIGH", "MEDIUM", "LOW"]
sel_risk = st.sidebar.multiselect("⚠ 리스크 등급", risk_levels, default=risk_levels)

match_levels = ["X", "O"]
sel_match = st.sidebar.multiselect("🔍 매칭여부 (X=비매칭)", match_levels, default=match_levels)

fee_min, fee_max = st.sidebar.slider("💰 월정료(천원) 범위", 0, 500, (0, 500))

daterange = st.sidebar.date_input("📅 날짜 범위", [])

sel_voc_mid = st.sidebar.selectbox(
    "📌 VOC 중분류", 
    ["전체"] + sorted(df_view["VOC유형중"].dropna().unique()) if "VOC유형중" in df_view else ["전체"]
)

st.sidebar.markdown("---")


# ------------------------------------------------------------
# 📌 4) 필터 적용
# ------------------------------------------------------------
df_f = df_view.copy()

if "전체" not in sel_branches:
    df_f = df_f[df_f["관리지사"].isin(sel_branches)]

if "전체" not in sel_managers:
    df_f = df_f[df_f["담당자"].isin(sel_managers)]

if sel_risk:
    if "리스크등급" in df_f.columns:
        df_f = df_f[df_f["리스크등급"].isin(sel_risk)]

if sel_match:
    if "체미매칭" in df_f.columns:
        df_f = df_f[df_f["체미매칭"].isin(sel_match)]

if SEL_VOC_MID := sel_voc_mid:
    if sel_voc_mid != "전체" and "VOC유형중" in df_f.columns:
        df_f = df_f[df_f["VOC유형중"] == sel_voc_mid]

df_f = df_f[(df_f["월정료_천원"] >= fee_min) & (df_f["월정료_천원"] <= fee_max)]


# ------------------------------------------------------------
# 📌 5) KPI 카드
# ------------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)

c1.metric("총 행 수", f"{len(df_f):,}")
c2.metric("유니크 계약 수", f"{df_f['계약번호_정제'].nunique():,}")
c3.metric("비매칭(X) 계약건", f"{(df_f['체미매칭']=='X').sum():,}" if "체미매칭" in df_f else "-")
c4.metric("평균 월정료(천원)", f"{df_f['월정료_천원'].mean():.1f}")


st.markdown("---")


# ------------------------------------------------------------
# 📌 6) 시각화 — 지사별 계약수 (적층)
# ------------------------------------------------------------
st.markdown("### 🏢 지사별 계약 수 (리스크 적층)")

if {"관리지사", "리스크등급"}.issubset(df_f.columns):

    pivot = df_f.pivot_table(
        index="관리지사",
        columns="리스크등급",
        values="계약번호_정제",
        aggfunc="nunique",
        fill_value=0
    )

    fig = px.bar(
        pivot,
        x=pivot.index,
        y=["HIGH", "MEDIUM, 'LOW"],
        title="지사별 계약수 (리스크 적층)",
        barmode="stack",
        text_auto=True
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("지사 또는 리스크 데이터가 부족하여 시각화를 생성할 수 없습니다.")


# ------------------------------------------------------------
# 📌 7) 담당자별 비매칭 TOP 20
# ------------------------------------------------------------
if "담당자" in df_f.columns and "체미매칭" in df_f.columns:

    st.markdown("### 👤 담당자별 비매칭 TOP 20")

    top_fail = (
        df_f[df_f["체미매칭"]=="X"]
        .groupby("담당자")["계약번호_정제"]
        .nunique()
        .sort_values(ascending=False)
        .head(20)
    )

    fig2 = px.bar(
        top_fail,
        title="담당자별 비매칭 TOP 20",
        text_auto=True
    )
    st.plotly_chart(fig2, use_container_width=True)


# ------------------------------------------------------------
# 📌 8) 상세 테이블
# ------------------------------------------------------------
st.markdown("### 📄 필터링된 상세 데이터")

display_cols = [
    "계약번호_정제", "상호", "관리지사", "담당자",
    "VOC유형중", "체미매칭", "리스크등급", "월정료_천원"
]

display_cols = [col for col in display_cols if col in df_f.columns]

st.dataframe(df_f[display_cols], use_container_width=True, height=350)   

# ------------------------------------------------------------
# PART 4 — 활동내역 등록 / 로그 저장 / 관리자 전체 조회
# ------------------------------------------------------------

LOG_FILE = "activity_log.csv"


# ------------------------------------------------------------
# 1) 로그 파일 로드 함수
# ------------------------------------------------------------
@st.cache_data
def load_logs():
    if os.path.exists(LOG_FILE):
        try:
            return pd.read_csv(LOG_FILE, encoding="utf-8-sig")
        except:
            return pd.read_csv(LOG_FILE)
    else:
        return pd.DataFrame(columns=["계약번호", "활동내용", "등록자", "등록일시", "비고"])


def save_logs(df_logs):
    df_logs.to_csv(LOG_FILE, index=False, encoding="utf-8-sig")


logs_df = load_logs()


# ------------------------------------------------------------
# 2) UI — 활동내역 등록
# ------------------------------------------------------------
st.markdown("## 📝 활동내역 등록")

st.info("특정 계약번호의 고객 대응 및 현장 활동 내역을 기록합니다.")

colA, colB = st.columns([1, 2])

with colA:
    sel_contract = st.selectbox(
        "📌 계약번호 선택",
        ["선택하세요"] + sorted(df_view["계약번호_정제"].dropna().unique())
    )

with colB:
    st.write("")  # 간격 확보
    st.write("")

activity = st.text_area("✍ 활동 내용 입력")
note = st.text_input("비고 (선택사항)")


if st.button("📥 활동내역 등록"):

    if sel_contract == "선택하세요":
        st.error("계약번호를 선택해주세요.")
    elif activity.strip() == "":
        st.error("활동 내용을 입력해주세요.")
    else:
        new_row = {
            "계약번호": sel_contract,
            "활동내용": activity,
            "등록자": LOGIN_USER,
            "등록일시": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "비고": note,
        }

        logs_df = pd.concat([logs_df, pd.DataFrame([new_row])], ignore_index=True)

        save_logs(logs_df)

        st.success(f"등록 완료! (계약번호: {sel_contract})")
        st.balloons()


# ------------------------------------------------------------
# 3) 관리자 전용 — 전체 활동로그 조회
# ------------------------------------------------------------
st.markdown("---")
st.markdown("## 📋 활동내역 조회")

if LOGIN_TYPE == "admin":
    st.success("관리자 권한: 전체 활동내역 조회 가능")

    st.dataframe(
        logs_df.sort_values("등록일시", ascending=False),
        use_container_width=True,
        height=350,
    )

else:
    st.info("담당자는 본인 활동내역만 확인할 수 있습니다.")

    df_mylog = logs_df[logs_df["등록자"] == LOGIN_USER]

    st.dataframe(
        df_mylog.sort_values("등록일시", ascending=False),
        use_container_width=True,
        height=350,
    )

# ------------------------------------------------------------
# PART 5 — 담당자 이메일 알림 발송 기능 (관리자 전용)
# ------------------------------------------------------------

import smtplib
from email.message import EmailMessage

st.markdown("---")
st.markdown("## 📬 담당자 이메일 알림 발송")

if LOGIN_TYPE != "admin":
    st.info("이메일 알림 기능은 관리자만 사용할 수 있습니다.")
else:
    st.success("관리자 권한: 담당자 이메일 발송 가능")

    # 비매칭(X) 데이터 기반
    unmatched_df = df_view[df_view["체미매칭"] == "X"].copy()

    if unmatched_df.empty:
        st.info("현재 비매칭(X) 데이터가 없습니다.")
    else:
        # 담당자별 분류
        grouped = unmatched_df.groupby("담당자")

        st.markdown("### 📊 담당자별 비매칭 데이터")

        alert_rows = []
        for mgr, g in grouped:
            mgr = str(mgr).strip()
            if mgr == "" or mgr == "nan":
                continue

            email = manager_contacts.get(mgr, {}).get("email", "")
            alert_rows.append([mgr, email, len(g)])

        alert_df = pd.DataFrame(alert_rows, columns=["담당자", "이메일", "비매칭 건수"])
        st.dataframe(alert_df, use_container_width=True, height=260)

        st.markdown("### ✉ 개별 이메일 발송")

        sel_mgr = st.selectbox(
            "담당자 선택",
            ["선택하세요"] + alert_df["담당자"].tolist()
        )

        if sel_mgr != "선택하세요":

            mgr_email = manager_contacts.get(sel_mgr, {}).get("email", "")
            custom_email = st.text_input(
                "담당자 이메일 주소",
                value=mgr_email,
                placeholder="등록된 이메일이 없으면 직접 입력"
            )

            df_target = unmatched_df[unmatched_df["담당자"] == sel_mgr]

            st.write(f"📌 발송 대상 건수: {len(df_target)}건")

            if st.button("📤 이메일 발송하기"):
                if custom_email.strip() == "":
                    st.error("이메일 주소를 입력해주세요.")
                else:
                    try:
                        msg = EmailMessage()
                        msg["Subject"] = f"[해지VOC] {sel_mgr} 담당자 비매칭 VOC 알림"
                        msg["From"] = f"{SENDER_NAME} <{SMTP_USER}>"
                        msg["To"] = custom_email

                        body = (
                            f"{sel_mgr} 담당자님,\n\n"
                            f"귀하에게 배정된 비매칭 VOC가 총 {len(df_target)}건 확인되었습니다.\n"
                            "첨부된 CSV 파일을 확인해 조치 부탁드립니다.\n\n"
                            "- 해지VOC 관리자 드림 -"
                        )

                        msg.set_content(body)

                        # CSV 첨부
                        csv_bytes = df_target.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                        msg.add_attachment(
                            csv_bytes,
                            maintype="application",
                            subtype="octet-stream",
                            filename=f"비매칭VOC_{sel_mgr}.csv"
                        )

                        # SMTP 전송
                        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
                            smtp.starttls()
                            smtp.login(SMTP_USER, SMTP_PASSWORD)
                            smtp.send_message(msg)

                        st.success(f"메일 발송 완료 → {custom_email}")

                    except Exception as e:
                        st.error(f"메일 발송 실패: {e}")    
