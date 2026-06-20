import streamlit as st
import sys, os
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
from core.query_builder import QueryBuilder


# ══════════════════════════════════════════════
#  CSS
# ══════════════════════════════════════════════
st.markdown("""
<style>
/* 페이지 전체 폰트 */
html, body, [class*="css"] { font-family: 'Pretendard', 'Malgun Gothic', sans-serif; }

/* 섹션 타이틀 */
.section-title {
    font-size: 18px; font-weight: 700;
    color: #1a1a2e; margin: 20px 0 4px 0;
    border-left: 4px solid #4F6BED;
    padding-left: 10px;
}

/* 타입 배지 */
.badge {
    display: inline-block;
    padding: 2px 9px; border-radius: 20px;
    font-size: 10px; font-weight: 700;
    letter-spacing: 0.5px; color: #fff;
    margin-left: 5px; vertical-align: middle;
}
.badge-DATE    { background: #2196F3; }
.badge-NUMBER  { background: #43A047; }
.badge-TEXT    { background: #FB8C00; }
.badge-UNKNOWN { background: #9E9E9E; }

/* 요약 카드 */
.summary-card {
    background: linear-gradient(135deg, #4F6BED 0%, #6B8CFF 100%);
    border-radius: 12px; padding: 16px 24px;
    color: white; margin: 12px 0;
    display: flex; align-items: center; gap: 16px;
}
.summary-num { font-size: 32px; font-weight: 800; }
.summary-label { font-size: 13px; opacity: 0.85; }

/* 버튼 그룹 */
div[data-testid="stButton"] button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 13px !important;
}

/* data_editor 헤더 중앙 정렬 */
div[data-testid="stDataFrame"] th {
    text-align: center !important;
}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════
#  상수 정의
# ══════════════════════════════════════════════
DIMENSION_META = {
    'completeness': {'label': '완전성', 'emoji': '🔵', 'color': '#2196F3'},
    'consistency':  {'label': '일관성', 'emoji': '🟢', 'color': '#43A047'},
    'accuracy':     {'label': '정확성', 'emoji': '🟠', 'color': '#FB8C00'},
    'usefulness':   {'label': '유용성', 'emoji': '🟡', 'color': '#FDD835'},
    'uniqueness':   {'label': '유일성', 'emoji': '🟣', 'color': '#8E24AA'},
    'validity':     {'label': '유효성', 'emoji': '🔴', 'color': '#E53935'},
}

RULE_SHORT_KR = {
    'COMP_001': '필수값 누락',
    'COMP_002': '공백값',
    'CONS_001': '앞뒤 공백',
    'ACC_001':  '특수문자',
    'USE_001':  '더미 데이터',
    'UNIQ_001': '단일 중복',
    'UNIQ_002': '복합키 중복',
    'VAL_001':  '날짜 형식',
    'VAL_002':  '숫자 혼입',
}

TYPE_DEFAULTS = {
    'DATE':    {'COMP_001','COMP_002','CONS_001','VAL_001'},
    'NUMBER':  {'COMP_001','COMP_002','CONS_001','USE_001','UNIQ_001','VAL_002'},
    'TEXT':    {'COMP_001','COMP_002','CONS_001','ACC_001','USE_001','UNIQ_001'},
    'UNKNOWN': {'COMP_001','COMP_002','CONS_001','ACC_001','USE_001'},
}

TYPE_BADGE = {
    'DATE':    ('badge-DATE',    'DATE'),
    'NUMBER':  ('badge-NUMBER',  'NUMBER'),
    'TEXT':    ('badge-TEXT',    'TEXT'),
    'UNKNOWN': ('badge-UNKNOWN', '?'),
}

# ══════════════════════════════════════════════
#  사전 조건 체크
# ══════════════════════════════════════════════
if 'connected' not in st.session_state or not st.session_state.connected:
    st.warning("⚠️ 먼저 [2_data_connect]에서 DB를 연결하거나 파일을 업로드해주세요.")
    st.stop()

connector = st.session_state.connector
engine    = connector.engine

def detect_db_type(engine) -> str:
    d = engine.dialect.name.lower()
    if 'oracle'     in d: return 'oracle'
    if 'sqlite'     in d: return 'sqlite'
    if 'postgresql' in d: return 'postgresql'
    if 'mysql'      in d: return 'mysql'
    return 'sqlite'

db_type = detect_db_type(engine)

# ══════════════════════════════════════════════
#  규칙 로드
# ══════════════════════════════════════════════
qb = QueryBuilder()
all_rules_by_dim = qb.load_all_templates()

all_rules_flat = []
for dim_key, rules in all_rules_by_dim.items():
    for r in rules:
        r['_dim'] = dim_key
        all_rules_flat.append(r)

rule_dict          = {r['id']: r for r in all_rules_flat}
col_level_rules    = [r for r in all_rules_flat if r.get('level','column') == 'column']
tbl_level_rules    = [r for r in all_rules_flat if r.get('level') == 'table']
col_level_rule_ids = [r['id'] for r in col_level_rules]

# ══════════════════════════════════════════════
#  UI 시작
# ══════════════════════════════════════════════
st.markdown("<div class='section-title'>⚙️ 진단 항목 설정</div>", unsafe_allow_html=True)

# ── 1. 테이블 선택 ────────────────────────────
col_t, col_d = st.columns([3, 2])
with col_t:
    tables = connector.get_table_names()
    if not tables:
        st.error("테이블 목록을 불러오지 못했습니다.")
        st.stop()

    # 단일/다중 모드 선택
    diag_mode = st.radio(
        "진단 모드", ["단일 테이블", "다중 테이블 동시 진단"],
        horizontal=True, label_visibility="collapsed"
    )

with col_d:
    st.metric("연결 DB", db_type.upper())

if diag_mode == "단일 테이블":
    selected_table = st.selectbox("📋 진단할 테이블", tables)
    selected_tables_list = [selected_table] if selected_table else []
else:
    selected_tables_list = st.multiselect(
        "📋 진단할 테이블 선택 (여러 개 가능)", tables,
        placeholder="테이블을 선택하세요...",
        label_visibility="collapsed"
    )
    selected_table = selected_tables_list[0] if selected_tables_list else None
    if selected_tables_list:
        st.info(f"✅ {len(selected_tables_list)}개 테이블 선택됨: "
                + ", ".join([f"`{t}`" for t in selected_tables_list]))

if not selected_tables_list:
    st.info("진단할 테이블을 선택해주세요.")
    st.stop()

# 단일 테이블 기준으로 컬럼 설정 (다중일 때는 공통 규칙 적용)
all_columns  = connector.get_columns(selected_table)
column_types = connector.get_column_types(selected_table)

if diag_mode == "다중 테이블 동시 진단" and len(selected_tables_list) > 1:
    st.caption("💡 다중 테이블 모드: 각 테이블에 동일한 진단 규칙이 적용됩니다. "
               "컬럼 선택은 첫 번째 테이블 기준으로 표시되며, 실제 진단 시 각 테이블의 실제 컬럼에 맞게 자동 적용됩니다.")

# ══════════════════════════════════════════════
#  핵심: st.data_editor 기반 매트릭스
#  - DataFrame을 session_state에 저장
#  - 버튼은 DataFrame을 직접 수정 후 st.rerun()
#  - data_editor는 저장된 DataFrame을 그대로 표시
# ══════════════════════════════════════════════

# DataFrame 컬럼 헤더 구성 (완전성-필수값누락 형식)
def make_col_header(rule_id):
    rule    = rule_dict.get(rule_id, {})
    dim_key = rule.get('_dim', '')
    meta    = DIMENSION_META.get(dim_key, {'label':'?','emoji':'⚪'})
    short   = RULE_SHORT_KR.get(rule_id, rule_id)
    return f"{meta['emoji']} {meta['label']}\n{short}"

# 헤더 목록
df_col_headers = ['컬럼명', '타입'] + [make_col_header(rid) for rid in col_level_rule_ids]

# ── DataFrame 초기화 함수 ─────────────────────
def build_default_df(columns, col_types, selected_cols=None):
    rows = []
    for col in columns:
        if selected_cols and col not in selected_cols:
            continue
        col_type = col_types.get(col, 'UNKNOWN')
        defaults = TYPE_DEFAULTS.get(col_type, TYPE_DEFAULTS['UNKNOWN'])
        badge_cls, badge_txt = TYPE_BADGE.get(col_type, ('badge-UNKNOWN','?'))
        row = {
            '컬럼명': col,
            '타입':   col_type,
        }
        for rid in col_level_rule_ids:
            header = make_col_header(rid)
            row[header] = (rid in defaults)
        rows.append(row)
    return pd.DataFrame(rows)

# 세션에 matrix_df 없으면 초기화
if ('matrix_df' not in st.session_state
        or st.session_state.get('matrix_table') != selected_table):
    st.session_state.matrix_df    = build_default_df(all_columns, column_types)
    st.session_state.matrix_table = selected_table

matrix_df: pd.DataFrame = st.session_state.matrix_df

st.divider()
st.markdown("<div class='section-title'>컬럼별 진단 규칙 설정</div>", unsafe_allow_html=True)
st.caption("Oracle 컬럼 타입을 자동으로 읽어 규칙을 추천합니다. 체크박스로 자유롭게 조정하세요.")

# ── 컬럼 선택 멀티셀렉트 ─────────────────────
selected_columns = st.multiselect(
    "진단할 컬럼 선택",
    all_columns,
    default=list(matrix_df['컬럼명']),
    placeholder="컬럼을 선택하세요...",
    label_visibility="collapsed"
)

# 선택 컬럼 변경 시 matrix_df 동기화
current_cols_in_df = list(matrix_df['컬럼명'])
if set(selected_columns) != set(current_cols_in_df):
    # 기존 행 유지 + 새 컬럼 추가 + 제거된 컬럼 삭제
    existing_rows = matrix_df[matrix_df['컬럼명'].isin(selected_columns)].copy()
    new_cols      = [c for c in selected_columns if c not in current_cols_in_df]
    if new_cols:
        new_rows = build_default_df(new_cols, column_types)
        existing_rows = pd.concat([existing_rows, new_rows], ignore_index=True)
    # 선택 순서 맞추기
    order_map = {col: i for i, col in enumerate(selected_columns)}
    existing_rows['_order'] = existing_rows['컬럼명'].map(order_map)
    existing_rows = existing_rows.sort_values('_order').drop(columns=['_order'])
    matrix_df = existing_rows.reset_index(drop=True)
    st.session_state.matrix_df = matrix_df

# ── 일괄 버튼 4개 ────────────────────────────
b1, b2, b3, b4 = st.columns(4)

with b1:
    if st.button("✅ 전체 선택", use_container_width=True):
        for rid in col_level_rule_ids:
            h = make_col_header(rid)
            st.session_state.matrix_df[h] = True
        st.rerun()

with b2:
    if st.button("🔄 타입 추천으로 초기화", use_container_width=True):
        for idx, row in st.session_state.matrix_df.iterrows():
            col_type = column_types.get(row['컬럼명'], 'UNKNOWN')
            defaults = TYPE_DEFAULTS.get(col_type, TYPE_DEFAULTS['UNKNOWN'])
            for rid in col_level_rule_ids:
                h = make_col_header(rid)
                st.session_state.matrix_df.at[idx, h] = (rid in defaults)
        st.rerun()

with b3:
    if st.button("❌ 전체 해제", use_container_width=True):
        for rid in col_level_rule_ids:
            h = make_col_header(rid)
            st.session_state.matrix_df[h] = False
        st.rerun()

with b4:
    # 현재 체크된 수 표시
    bool_cols = [make_col_header(rid) for rid in col_level_rule_ids]
    if not matrix_df.empty and bool_cols:
        total_checked = matrix_df[bool_cols].sum().sum()
        st.metric("선택된 규칙", f"{int(total_checked)} 건")

# ── data_editor 매트릭스 ──────────────────────
st.markdown("---")

if not matrix_df.empty:
    # 체크박스 컬럼 설정
    bool_headers = [make_col_header(rid) for rid in col_level_rule_ids]

    column_config = {
        '컬럼명': st.column_config.TextColumn('컬럼명', width=130, disabled=True),
        '타입':   st.column_config.TextColumn('타입',   width=80,  disabled=True),
    }
    for rid in col_level_rule_ids:
        h = make_col_header(rid)
        rule    = rule_dict.get(rid, {})
        dim_key = rule.get('_dim', '')
        meta    = DIMENSION_META.get(dim_key, {'label':'?'})
        short   = RULE_SHORT_KR.get(rid, rid)
        column_config[h] = st.column_config.CheckboxColumn(
            label=h,
            width=90,
            help=f"{meta['label']} — {short}"
        )

    edited_df = st.data_editor(
        st.session_state.matrix_df,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        key="matrix_editor",
        height=min(80 + len(matrix_df) * 35, 600),
    )

    # 편집 내용 즉시 세션에 반영
    st.session_state.matrix_df = edited_df
    matrix_df = edited_df

else:
    st.info("진단할 컬럼을 선택해주세요.")
    st.stop()

# ── 복합키(table-level) 규칙 ──────────────────
st.divider()
st.markdown("<div class='section-title'>복합키 / 테이블 전체 규칙</div>", unsafe_allow_html=True)

selected_tbl_rule_ids = []
if tbl_level_rules:
    t_cols = st.columns(max(len(tbl_level_rules), 1))
    for i, rule in enumerate(tbl_level_rules):
        dim_key = rule.get('_dim','')
        meta    = DIMENSION_META.get(dim_key, {'label':'기타','emoji':'⚪'})
        short   = RULE_SHORT_KR.get(rule['id'], rule['name'])
        checked = t_cols[i].checkbox(
            f"{meta['emoji']} {meta['label']} — {short}",
            value=True, key=f"tbl_{rule['id']}"
        )
        if checked:
            selected_tbl_rule_ids.append(rule['id'])
else:
    st.info("테이블 단위 규칙이 없습니다.")

# ── 요약 & 생성 버튼 ──────────────────────────
st.divider()

bool_cols_list  = [make_col_header(rid) for rid in col_level_rule_ids]
total_col_rules = int(matrix_df[bool_cols_list].sum().sum()) if bool_cols_list else 0
total_tbl_rules = len(selected_tbl_rule_ids)
total_queries   = total_col_rules + total_tbl_rules

m1, m2, m3, m4 = st.columns(4)
m1.metric("진단 컬럼",       f"{len(matrix_df)} 개")
m2.metric("컬럼별 규칙",     f"{total_col_rules} 건")
m3.metric("복합키 규칙",     f"{total_tbl_rules} 건")
m4.metric("총 예상 쿼리 수", f"{total_queries} 개")

st.markdown("")



# ── 진단 설정 저장/불러오기 ─────────────────
with st.expander("💾 진단 설정 저장 / 불러오기"):
    import sqlite3 as _sqlite3, json as _json, datetime as _dt

    def _init_config_db():
        con = _sqlite3.connect("history.db")
        con.execute("""
            CREATE TABLE IF NOT EXISTS diagnosis_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                table_name TEXT,
                col_rule_map TEXT,
                saved_at TEXT
            )
        """)
        con.commit()
        con.close()

    def _save_config(name, table, col_map):
        _init_config_db()
        con = _sqlite3.connect("history.db")
        con.execute(
            "INSERT INTO diagnosis_configs (name, table_name, col_rule_map, saved_at) VALUES (?,?,?,?)",
            (name, table,
             _json.dumps(col_map, ensure_ascii=False),
             _dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        con.commit()
        con.close()

    def _load_configs():
        try:
            _init_config_db()
            con = _sqlite3.connect("history.db")
            rows = con.execute(
                "SELECT id, name, table_name, saved_at FROM diagnosis_configs ORDER BY id DESC LIMIT 20"
            ).fetchall()
            con.close()
            return rows
        except Exception:
            return []

    def _get_config(config_id):
        con = _sqlite3.connect("history.db")
        row = con.execute(
            "SELECT col_rule_map FROM diagnosis_configs WHERE id=?",
            (config_id,)
        ).fetchone()
        con.close()
        return row

    sv_col, ld_col = st.columns(2)

    with sv_col:
        st.markdown("**현재 설정 저장**")
        cfg_name = st.text_input("설정 이름",
            placeholder="예) 행안부_cart_기본진단", key="cfg_name_input")
        if st.button("💾 저장", use_container_width=True, key="btn_save_cfg"):
            if not cfg_name.strip():
                st.warning("설정 이름을 입력해주세요.")
            else:
                cur_map = {}
                if 'matrix_df' in st.session_state and not st.session_state.matrix_df.empty:
                    for _, mrow in st.session_state.matrix_df.iterrows():
                        col = mrow['컬럼명']
                        cur_map[col] = [
                            rid for rid in col_level_rule_ids
                            if mrow.get(make_col_header(rid), False)
                        ]
                _save_config(cfg_name.strip(), selected_table, cur_map)
                st.success(f"✅ '{cfg_name}' 저장 완료!")

    with ld_col:
        st.markdown("**저장된 설정 불러오기**")
        saved = _load_configs()
        if saved:
            opts = {f"[{r[0]}] {r[1]} / {r[2]} ({r[3]})": r[0] for r in saved}
            sel_cfg = st.selectbox("설정 선택", list(opts.keys()),
                                   label_visibility="collapsed")
            if st.button("📂 불러오기", use_container_width=True, key="btn_load_cfg"):
                row = _get_config(opts[sel_cfg])
                if row:
                    loaded_map = _json.loads(row[0])
                    if 'matrix_df' in st.session_state:
                        for col, rule_ids in loaded_map.items():
                            for rid in col_level_rule_ids:
                                h   = make_col_header(rid)
                                idx = st.session_state.matrix_df[
                                    st.session_state.matrix_df['컬럼명'] == col
                                ].index
                                if len(idx) > 0:
                                    st.session_state.matrix_df.at[idx[0], h] = rid in rule_ids
                    st.success("✅ 설정 불러오기 완료!")
                    st.rerun()
        else:
            st.info("저장된 설정이 없습니다.")


if st.button("🚀 진단 쿼리 생성 및 저장", type="primary", use_container_width=True):
    if total_queries == 0:
        st.error("적용할 진단 규칙을 하나 이상 선택해주세요.")
        st.stop()

    # matrix_df → column_rule_map 변환
    column_rule_map = {}
    for _, row in matrix_df.iterrows():
        col      = row['컬럼명']
        selected = []
        for rid in col_level_rule_ids:
            h = make_col_header(rid)
            if row.get(h, False):
                selected.append(rid)
        column_rule_map[col] = selected

    with st.spinner("진단 쿼리를 생성 중입니다..."):
        # column-level 쿼리
        queries = qb.build_queries_per_column(
            table=selected_table,
            column_rule_map=column_rule_map,
            all_rules=all_rules_flat,
            db_type=db_type,
        )

        # table-level 쿼리 (복합키 등)
        if selected_tbl_rule_ids and list(column_rule_map.keys()):
            tbl_q = qb.build_queries_per_column(
                table=selected_table,
                column_rule_map={list(column_rule_map.keys())[0]: selected_tbl_rule_ids},
                all_rules=all_rules_flat,
                db_type=db_type,
            )
            tbl_q = [q for q in tbl_q
                     if rule_dict.get(q['rule_id'], {}).get('level') == 'table']
            queries += tbl_q

        st.session_state.diagnosis_queries = queries

    st.success(f"✅ 총 **{len(queries)}개** 진단 쿼리 생성 완료! [4_diagnosis_run]으로 이동하세요.")

    with st.expander("📋 생성된 SQL 쿼리 미리보기"):
        for q in queries:
            dim_key  = rule_dict.get(q['rule_id'], {}).get('_dim', '')
            meta     = DIMENSION_META.get(dim_key, {'emoji':'', 'label':''})
            st.markdown(f"{meta['emoji']} **{q['rule_name']}** — `{q['column']}`")
            st.code(q['query'], language="sql")
