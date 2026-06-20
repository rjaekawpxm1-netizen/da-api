import streamlit as st
import sqlite3
import datetime
import os


st.title("📋 프로젝트 관리")
st.markdown("품질진단 프로젝트를 생성하고, 기존 이력을 조회합니다.")

# ──────────────────────────────────────────────
#  DB 초기화 (SQLite로 이력 관리)
# ──────────────────────────────────────────────

DB_PATH = "history.db"

def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            org_name     TEXT NOT NULL,
            project_name TEXT NOT NULL,
            manager      TEXT,
            created_at   TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS diagnosis_history (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id   INTEGER NOT NULL,
            table_name   TEXT,
            total_items  INTEGER,
            error_items  INTEGER,
            total_errors INTEGER,
            diagnosed_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)
    con.commit()
    con.close()

def get_all_projects():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT id, org_name, project_name, manager, created_at FROM projects ORDER BY id DESC")
    rows = cur.fetchall()
    con.close()
    return rows

def insert_project(org_name, project_name, manager):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        "INSERT INTO projects (org_name, project_name, manager, created_at) VALUES (?, ?, ?, ?)",
        (org_name, project_name, manager, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    project_id = cur.lastrowid
    con.commit()
    con.close()
    return project_id

def delete_project(project_id):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("DELETE FROM diagnosis_history WHERE project_id = ?", (project_id,))
    cur.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    con.commit()
    con.close()

def get_history_for_project(project_id):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        "SELECT table_name, total_items, error_items, total_errors, diagnosed_at "
        "FROM diagnosis_history WHERE project_id = ? ORDER BY id DESC",
        (project_id,)
    )
    rows = cur.fetchall()
    con.close()
    return rows

def save_diagnosis_history(project_id, table_name, raw_results):
    """진단 완료 후 이력 저장 (4_diagnosis_run 완료 시 자동 호출 가능)"""
    import pandas as pd
    df = pd.DataFrame(raw_results)
    total_items  = len(df)
    error_items  = len(df[df.get("error_cnt", 0) > 0]) if "error_cnt" in df.columns else 0
    total_errors = int(df["error_cnt"].sum()) if "error_cnt" in df.columns else 0

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        "INSERT INTO diagnosis_history (project_id, table_name, total_items, error_items, total_errors, diagnosed_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (project_id, table_name, total_items, error_items, total_errors,
         datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    con.commit()
    con.close()


# ──────────────────────────────────────────────
#  초기화 & 세션 상태
# ──────────────────────────────────────────────

init_db()

if "current_project" not in st.session_state:
    st.session_state.current_project = None  # {"id", "org_name", "project_name", "manager"}


# ──────────────────────────────────────────────
#  UI
# ──────────────────────────────────────────────

tab_new, tab_list, tab_compare = st.tabs(["➕ 새 프로젝트 생성", "📂 기존 프로젝트 이력", "📊 품질 이력 비교"])

# ── 탭1: 새 프로젝트 ──────────────────────────
with tab_new:
    st.subheader("새 품질진단 프로젝트 등록")

    col1, col2 = st.columns(2)
    with col1:
        org_name     = st.text_input("기관명 *", placeholder="예) 행정안전부")
        project_name = st.text_input("사업명 *", placeholder="예) 2025 공공데이터 품질진단")
    with col2:
        manager = st.text_input("담당자명", placeholder="예) 홍길동")
        st.write("")  # 여백

    st.divider()

    if st.button("✅ 프로젝트 생성 및 선택", type="primary"):
        if not org_name.strip() or not project_name.strip():
            st.error("기관명과 사업명은 필수 입력입니다.")
        else:
            pid = insert_project(org_name.strip(), project_name.strip(), manager.strip())
            st.session_state.current_project = {
                "id":           pid,
                "org_name":     org_name.strip(),
                "project_name": project_name.strip(),
                "manager":      manager.strip(),
            }
            st.success(f"✅ 프로젝트가 생성되었습니다. (ID: {pid})")
            st.info("이제 왼쪽 메뉴 **[2] 데이터 연결** 로 이동하세요.")

# ── 탭2: 기존 이력 ───────────────────────────
with tab_list:
    st.subheader("등록된 프로젝트 목록")
    projects = get_all_projects()

    if not projects:
        st.info("아직 등록된 프로젝트가 없습니다.")
    else:
        for p in projects:
            pid, org, pname, mgr, created = p
            is_active = (
                st.session_state.current_project is not None
                and st.session_state.current_project["id"] == pid
            )
            label = f"{'🟢 ' if is_active else ''}[{pid}] {org} — {pname}"

            with st.expander(label, expanded=is_active):
                col_info, col_btn = st.columns([3, 1])
                with col_info:
                    st.write(f"**기관명:** {org}")
                    st.write(f"**사업명:** {pname}")
                    st.write(f"**담당자:** {mgr or '-'}")
                    st.write(f"**생성일:** {created}")

                with col_btn:
                    if not is_active:
                        if st.button("이 프로젝트 선택", key=f"sel_{pid}"):
                            st.session_state.current_project = {
                                "id":           pid,
                                "org_name":     org,
                                "project_name": pname,
                                "manager":      mgr or "",
                            }
                            st.rerun()
                    else:
                        st.success("현재 선택됨")

                    if st.button("삭제", key=f"del_{pid}", type="secondary"):
                        delete_project(pid)
                        if is_active:
                            st.session_state.current_project = None
                        st.rerun()

                # 진단 이력
                histories = get_history_for_project(pid)
                if histories:
                    st.markdown("**진단 이력**")
                    import pandas as pd
                    hdf = pd.DataFrame(histories, columns=["테이블", "진단항목수", "오류항목수", "총오류건수", "진단일시"])
                    st.dataframe(hdf, use_container_width=True, hide_index=True)

# ──────────────────────────────────────────────
#  사이드바: 현재 선택된 프로젝트 표시
# ──────────────────────────────────────────────


# ── 탭3: 이력 비교 ────────────────────────────
with tab_compare:
    st.subheader("품질진단 이력 비교")
    st.caption("기관별·프로젝트별 품질 점수 변화를 비교합니다.")

    try:
        con = sqlite3.connect(DB_PATH)
        # 전체 이력 조회
        rows = con.execute("""
            SELECT p.org_name, p.project_name, d.table_name,
                   d.total_items, d.error_items, d.total_errors, d.diagnosed_at,
                   CASE WHEN d.total_items > 0
                        THEN ROUND((1.0 - CAST(d.error_items AS FLOAT)/d.total_items)*100, 1)
                        ELSE 100.0 END AS quality_score
            FROM diagnosis_history d
            JOIN projects p ON d.project_id = p.id
            ORDER BY d.diagnosed_at DESC
            LIMIT 100
        """).fetchall()
        con.close()

        if not rows:
            st.info("아직 진단 이력이 없습니다. 보고서 출력 후 이력이 자동 저장됩니다.")
        else:
            hist_df = pd.DataFrame(rows, columns=[
                '기관명','사업명','테이블','진단항목수','오류항목수','총오류건수','진단일시','품질점수'
            ])

            # 요약 KPI
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("총 진단 횟수",   f"{len(hist_df)} 회")
            k2.metric("참여 기관 수",   f"{hist_df['기관명'].nunique()} 개")
            k3.metric("평균 품질 점수", f"{hist_df['품질점수'].mean():.1f} 점")
            k4.metric("최고 품질 점수", f"{hist_df['품질점수'].max():.1f} 점")

            st.divider()

            # 기관 선택 필터
            orgs = ['전체'] + sorted(hist_df['기관명'].unique().tolist())
            sel_org = st.selectbox("기관 선택", orgs)
            if sel_org != '전체':
                hist_df = hist_df[hist_df['기관명'] == sel_org]

            # 품질 점수 트렌드 차트
            if len(hist_df) > 1:
                import plotly.express as px
                fig = px.line(
                    hist_df.sort_values('진단일시'),
                    x='진단일시', y='품질점수',
                    color='기관명', markers=True,
                    title="기관별 품질 점수 추이",
                    labels={'품질점수': '품질 점수 (%)', '진단일시': '진단 일시'},
                    color_discrete_sequence=px.colors.qualitative.Set2,
                )
                fig.update_layout(yaxis_range=[0, 100], height=350)
                fig.add_hline(y=80, line_dash="dash", line_color="orange",
                              annotation_text="기준선(80점)")
                st.plotly_chart(fig, use_container_width=True)

            # 이력 테이블
            st.markdown("**상세 이력**")

            def color_score(val):
                if isinstance(val, float):
                    if val >= 90: return 'background-color: #E8F5E9; color: #2E7D32'
                    elif val >= 70: return 'background-color: #FFF8E1; color: #F57F17'
                    else: return 'background-color: #FFEBEE; color: #C62828'
                return ''

            st.dataframe(
                hist_df.style.applymap(color_score, subset=['품질점수']),
                use_container_width=True, hide_index=True, height=300
            )

            # CSV 다운로드
            csv = hist_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 이력 CSV 다운로드", csv,
                               "품질진단_이력.csv", "text/csv",
                               use_container_width=True)

    except Exception as e:
        st.error(f"이력 조회 실패: {e}")
