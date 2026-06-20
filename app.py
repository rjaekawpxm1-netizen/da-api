"""
공공데이터 품질진단 시스템 — 메인 진입점
st.navigation 기반 단일 대시보드 앱

실행:  streamlit run app.py
"""
import streamlit as st
import os

# ── 전역 페이지 설정 (앱 전체에서 단 1회) ──────────
st.set_page_config(
    page_title="공공데이터 품질진단 시스템",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 전역 스타일 ───────────────────────────────
st.markdown("""
<style>
/* 사이드바 */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
}
[data-testid="stSidebar"] * { color: #e8ebf5 !important; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { color: #ffffff !important; }

/* 사이드바 네비게이션 링크 */
[data-testid="stSidebarNav"] a {
    border-radius: 8px;
    margin: 1px 6px;
    transition: background 0.15s;
}
[data-testid="stSidebarNav"] a:hover { background: rgba(255,255,255,0.08); }

/* 상태 배지 */
.status-on  { background:#1b5e20; color:#a5d6a7; padding:3px 10px;
              border-radius:14px; font-size:11px; font-weight:700; }
.status-off { background:#4a1c1c; color:#ef9a9a; padding:3px 10px;
              border-radius:14px; font-size:11px; font-weight:700; }

/* 메트릭 컴팩트 */
[data-testid="stMetricValue"] { font-size: 22px; }
</style>
""", unsafe_allow_html=True)


# ── 세션 상태 전역 초기화 (KeyError 방지) ──────────
for _k, _v in {
    "current_project": None,
    "connected": False,
    "connector": None,
    "diagnosis_queries": [],
    "diagnosis_raw_results": [],
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── 페이지 정의 (워크플로우 단계별 그룹핑) ──────────
home = st.Page("pages/0_home.py", title="홈 대시보드", icon="🏠", default=True)

p_project = st.Page("pages/1_project.py",      title="프로젝트 관리",   icon="📋")
p_connect = st.Page("pages/2_data_connect.py", title="데이터 연결",     icon="🔌")

p_set     = st.Page("pages/3_diagnosis_set.py", title="진단 항목 설정",  icon="⚙️")
p_run     = st.Page("pages/4_diagnosis_run.py", title="진단 실행",       icon="▶️")
p_result  = st.Page("pages/5_result.py",        title="결과 분석",       icon="📈")

p_report  = st.Page("pages/6_report.py",   title="보고서 출력",        icon="📄")
p_erd     = st.Page("pages/7_erd.py",      title="ERD 자동화",         icon="🗺️")
p_std     = st.Page("pages/8_standard.py", title="AI 표준화 어드바이저", icon="🤖")

nav = st.navigation({
    "  ": [home],
    "① 준비":   [p_project, p_connect],
    "② 진단":   [p_set, p_run, p_result],
    "③ 산출물": [p_report, p_erd, p_std],
})


# ── 공통 사이드바: 현재 상태 + 진행 단계 ──────────
def render_sidebar_status():
    with st.sidebar:
        st.markdown("---")

        cp        = st.session_state.get("current_project")
        connected = st.session_state.get("connected", False)
        has_q     = bool(st.session_state.get("diagnosis_queries"))
        has_r     = bool(st.session_state.get("diagnosis_raw_results"))

        # 현재 프로젝트
        st.markdown("**📋 현재 프로젝트**")
        if cp:
            st.markdown(
                f"<div style='font-size:13px;line-height:1.5'>"
                f"<b>{cp.get('org_name','')}</b><br>{cp.get('project_name','')}</div>",
                unsafe_allow_html=True)
        else:
            st.caption("프로젝트 미선택")

        # DB 연결 상태
        st.markdown("**🔌 DB 연결**")
        if connected:
            conn = st.session_state.get("connector")
            d = ""
            try:
                if conn and conn.engine:
                    d = f" ({conn.engine.dialect.name.upper()})"
            except Exception:
                pass
            st.markdown(f"<span class='status-on'>✅ 연결됨{d}</span>", unsafe_allow_html=True)
        else:
            st.markdown("<span class='status-off'>❌ 미연결</span>", unsafe_allow_html=True)

        # 진행 단계
        st.markdown("**📊 진행 단계**")
        steps = [
            ("1 프로젝트", bool(cp)),
            ("2 DB 연결",  connected),
            ("3 항목 설정", has_q),
            ("4 진단 실행", has_r),
            ("5 결과 분석", has_r),
            ("6 보고서",    has_r),
        ]
        prog_html = ""
        for name, done in steps:
            icon = "✅" if done else "⬜"
            prog_html += f"<div style='font-size:12px;margin:2px 0'>{icon} {name}</div>"
        st.markdown(prog_html, unsafe_allow_html=True)

        st.markdown("---")
        st.caption("행정안전부 표준화 관리 매뉴얼 2026")
        st.caption("© 2026 품질진단 시스템")


render_sidebar_status()

# ── 선택된 페이지 실행 ──
nav.run()
