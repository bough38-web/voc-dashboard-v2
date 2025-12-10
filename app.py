import streamlit as st
import pandas as pd
import numpy as np

# -----------------------------------------------
# 1) CSV 파일 로드
# -----------------------------------------------
@st.cache_data
def load_data():
    df = pd.read_csv("merged_v2.csv", encoding="latin1")

    # 체미매칭 컬럼 자동 탐색 (두 번째 열)
    match_col = df.columns[1]

    # 매칭여부 컬럼 생성
    df["매칭여부"] = df[match_col].map({"O": "매칭(O)", "X": "비매칭(X)"}).fillna("비매칭(X)")

    # 계약번호 정제
    if "계약번호" in df.columns:
        df["계약번호_정제"] = (
            df["계약번호"]
            .astype(str)
            .str.replace(r"[^0-9A-Za-z]", "", regex=True)
            .str.strip()
        )
    else:
        df["계약번호_정제"] = ""

    # 지사명 정제
    if "관리지사" in df.columns:
        df["관리지사"] = df["관리지사"].astype(str).str.replace("지사", "").str.strip()
    else:
        df["관리지사"] = ""

    # 담당자 정제
    mgr_cols = [c for c in df.columns if "담당" in c or "처리자" in c]
    if mgr_cols:
        df["담당자_통합"] = df[mgr_cols[0]].astype(str).str.strip()
    else:
        df["담당자_통합"] = ""

    return df


df = load_data()

# -----------------------------------------------
# 2) 페이지 설정
# -----------------------------------------------
st.set_page_config(page_title="해지 VOC Dashboard", layout="wide")
st.title("📊 해지 VOC 대시보드 (merged_v2 기반 자동 반영)")

# -----------------------------------------------
# 3) 글로벌 필터 UI (지사 / 담당자 / 매칭여부)
# -----------------------------------------------
col1, col2, col3 = st.columns(3)

# 지사 목록
branches = ["전체"] + sorted(df["관리지사"].dropna().unique().tolist())
sel_branch = col1.selectbox("관리지사 선택", branches)

# 담당자 목록 (지사 선택 영향 받음)
tmp_df = df.copy()
if sel_branch != "전체":
    tmp_df = tmp_df[tmp_df["관리지사"] == sel_branch]

managers = ["전체"] + sorted(tmp_df["담당자_통합"].dropna().unique().tolist())
sel_mgr = col2.selectbox("담당자 선택", managers)

# 매칭여부
sel_match = col3.selectbox("매칭여부", ["전체", "매칭(O)", "비매칭(X)"])

# -----------------------------------------------
# 4) 필터 적용
# -----------------------------------------------
filtered = df.copy()

if sel_branch != "전체":
    filtered = filtered[filtered["관리지사"] == sel_branch]

if sel_mgr != "전체":
    filtered = filtered[filtered["담당자_통합"] == sel_mgr]

if sel_match != "전체":
    filtered = filtered[filtered["매칭여부"] == sel_match]

# -----------------------------------------------
# 5) KPI 카드
# -----------------------------------------------
st.subheader("📌 Key Metrics")

k1, k2, k3 = st.columns(3)
k1.metric("총 VOC 건수", f"{len(filtered):,}")
k2.metric("비매칭(X) 건수", f"{len(filtered[filtered['매칭여부']=='비매칭(X)']):,}")
k3.metric("매칭(O) 건수", f"{len(filtered[filtered['매칭여부']=='매칭(O)']):,}")

# -----------------------------------------------
# 6) 지사별 비매칭 분포 (Plotly bar)
# -----------------------------------------------
import plotly.express as px

st.markdown("### 🏢 지사별 비매칭 현황")

branch_summary = (
    df[df["매칭여부"]=="비매칭(X)"]
    .groupby("관리지사")["계약번호_정제"]
    .nunique()
    .reset_index(name="비매칭건수")
)

fig = px.bar(branch_summary, x="관리지사", y="비매칭건수", text="비매칭건수")
st.plotly_chart(fig, use_container_width=True)

# -----------------------------------------------
# 7) 담당자별 비매칭(X) 분석
# -----------------------------------------------
st.markdown("### 👤 담당자별 비매칭 현황")

mgr_summary = (
    df[df["매칭여부"]=="비매칭(X)"]
    .groupby("담당자_통합")["계약번호_정제"]
    .nunique()
    .reset_index(name="비매칭건수")
    .sort_values("비매칭건수", ascending=False)
)

fig2 = px.bar(mgr_summary.head(20), x="담당자_통합", y="비매칭건수", text="비매칭건수")
st.plotly_chart(fig2, use_container_width=True)

# -----------------------------------------------
# 8) 상세 데이터 테이블
# -----------------------------------------------
st.markdown("### 📋 상세 VOC 데이터")

st.dataframe(filtered, use_container_width=True, height=480)

# CSV 다운로드 버튼
st.download_button(
    label="📥 필터링된 데이터 다운로드 (CSV)",
    data=filtered.to_csv(index=False).encode("utf-8-sig"),
    file_name="filtered_voc.csv",
    mime="text/csv",
)