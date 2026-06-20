import streamlit as st
import pandas as pd
import sqlite3
import os

HISTORY_DB = "history.db"


def render_home():
    """홈 대시보드 — 전체 현황 요약 + 워크플로우 안내"""

    # ── 헤더 ──
    st.markdown("""
    <div style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 55%,#0f3460 100%);
                border-radius:16px;padding:30px 36px;margin-bottom:8px;">
      <div style="color:#fff;font-size:28px;font-weight:800;letter-spacing:-0.5px;">
        🏛️ 공공데이터 품질진단 시스템
      </div>
      <div style="color:#a9b4d0;font-size:14px;margin-top:6px;">
        행정안전부 공공데이터베이스 표준화 관리 매뉴얼 2026 기반 ·
        Oracle / MySQL / PostgreSQL / 파일(CSV·Excel) 지원
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 현재 세션 상태 ──
    cp        = st.session_state.get("current_project")
    connected = st.session_state.get("connected", False)
    queries   = st.session_state.get("diagnosis_queries", [])
    results   = st.session_state.get("diagnosis_raw_results", [])

    total_errors = 0
    if results:
        _df = pd.DataFrame(results)
        if 'error_cnt' in _df.columns:
            total_errors = int(_df[_df['error_cnt'] >= 0]['error_cnt'].sum())

    st.markdown("##### 📍 현재 작업 현황")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("현재 프로젝트", (cp.get('project_name','미설정')[:12] if cp else "미설정"))
    c2.metric("DB 연결",      "연결됨" if connected else "미연결")
    c3.metric("진단 항목",    f"{len(results)} 개")
    c4.metric("총 오류 건수", f"{total_errors:,} 건")

    # ── 전체 이력 요약 ──
    st.markdown("##### 🏆 전체 진단 이력")
    try:
        con = sqlite3.connect(HISTORY_DB)
        rows = con.execute("""
            SELECT p.org_name, d.diagnosed_at,
                   CASE WHEN d.total_items > 0
                        THEN ROUND((1.0 - CAST(d.error_items AS FLOAT)/d.total_items)*100,1)
                        ELSE 100.0 END AS quality_score
            FROM diagnosis_history d
            JOIN projects p ON d.project_id = p.id
            ORDER BY d.diagnosed_at DESC LIMIT 50
        """).fetchall()
        con.close()
    except Exception:
        rows = []

    if rows:
        hist = pd.DataFrame(rows, columns=['기관명','진단일시','품질점수'])
        h1,h2,h3,h4 = st.columns(4)
        h1.metric("총 진단 횟수",   f"{len(hist)} 회")
        h2.metric("참여 기관 수",   f"{hist['기관명'].nunique()} 개")
        h3.metric("평균 품질 점수", f"{hist['품질점수'].mean():.1f} 점")
        h4.metric("최고 품질 점수", f"{hist['품질점수'].max():.1f} 점")

        recent = hist.head(10).sort_values('진단일시')
        if len(recent) > 1:
            import plotly.express as px
            fig = px.bar(recent, x='진단일시', y='품질점수', color='기관명',
                         color_discrete_sequence=px.colors.qualitative.Set2, height=240)
            fig.update_layout(yaxis_range=[0,100], margin=dict(l=0,r=0,t=10,b=0),
                              legend=dict(orientation="h", y=-0.3))
            fig.add_hline(y=80, line_dash="dash", line_color="orange",
                          annotation_text="기준선 80점")
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("아직 진단 이력이 없습니다. 보고서 출력 시 이력이 자동 저장됩니다.")

    st.divider()

    # ── 6대 품질 영역 ──
    st.markdown("##### 📚 6대 품질 진단 영역")
    areas = [
        ("🔵 완전성", "필수값 누락·공백값 검사"),
        ("🟢 일관성", "앞뒤 공백 등 형식 일관성"),
        ("🟠 정확성", "비정상 특수문자 검사"),
        ("🟡 유용성", "더미·미상 데이터 검사"),
        ("🟣 유일성", "단일·복합키 중복 검사"),
        ("🔴 유효성", "날짜 형식·숫자 혼입 검사"),
    ]
    cols = st.columns(3)
    for i, (title, desc) in enumerate(areas):
        with cols[i % 3]:
            st.markdown(f"**{title}**  \n<span style='color:#888;font-size:13px'>{desc}</span>",
                        unsafe_allow_html=True)


render_home()
