import streamlit as st
import os
import sys, os, json, re
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
from core.llm_advisor import infer_erd_relationships


# ── 규칙 기반 ERD 생성 함수 (AI 미사용 / fallback) ───
def _build_rule_based_erd(tables: dict, col_types_all: dict, show_types: bool) -> dict:
    mermaid_lines = ["erDiagram"]
    relationships = []
    all_tables    = list(tables.keys())

    for table, cols in tables.items():
        mermaid_lines.append(f"    {table.upper()} " + "{")
        for col in cols[:12]:
            orig_type = col_types_all.get(table, {}).get(col, 'UNKNOWN')
            if orig_type == 'DATE':     dtype = "date"
            elif orig_type == 'NUMBER': dtype = "int"
            else:                       dtype = "string"
            is_pk = col.lower() in [
                f"{table.lower()}_id", f"{table.lower()}_no",
                f"{table.lower()}_seq", "id"
            ]
            type_str = f"{dtype} " if show_types else "string "
            pk_str   = " PK" if is_pk else ""
            mermaid_lines.append(f"        {type_str}{col}{pk_str}")
        mermaid_lines.append("    }")

    added = set()
    for t1 in all_tables:
        for col in tables[t1]:
            for t2 in all_tables:
                if t1 == t2: continue
                if col.lower() in [f"{t2.lower()}_id", f"{t2.lower()}_no", f"{t2.lower()}_seq"]:
                    key = f"{t2}:{t1}"
                    if key not in added:
                        added.add(key)
                        mermaid_lines.append(f"    {t2.upper()} " + "||--o{" + f" {t1.upper()} : has")
                        relationships.append({
                            "from_table": t2, "to_table": t1,
                            "from_col":   col, "to_col": col,
                            "type": "1:N", "confidence": "medium",
                            "reason": f"{col} 컬럼명 패턴으로 추론",
                        })

    return {
        "mermaid_code":   '\n'.join(mermaid_lines),
        "relationships":  relationships,
        "pk_suggestions": {t: f"{t.lower()}_id" for t in all_tables},
        "notes":          "규칙 기반 ERD (AI 미사용)",
        "_source":        "rule_based",
    }


# ══════════════════════════════════════════════
#  페이지 설정
# ══════════════════════════════════════════════

st.markdown("""
<style>
.erd-header {
    background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
    border-radius: 14px; padding: 22px 28px;
    color: white; margin-bottom: 24px;
}
.erd-header h2 { margin: 0 0 4px 0; font-size: 22px; }
.erd-header p  { margin: 0; opacity: 0.8; font-size: 13px; }
.rel-card {
    border-left: 4px solid #4F6BED;
    padding: 8px 14px;
    background: #f0f4ff;
    border-radius: 0 8px 8px 0;
    margin-bottom: 8px;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="erd-header">
  <h2>🗺️ ERD 자동화</h2>
  <p>DB 테이블 구조를 읽어 Claude AI가 관계를 추론하고 ERD · DDL을 자동 생성합니다</p>
</div>
""", unsafe_allow_html=True)

if 'connected' not in st.session_state or not st.session_state.connected:
    st.warning("⚠️ [2_data_connect]에서 먼저 DB를 연결해주세요.")
    st.stop()

connector  = st.session_state.connector
db_dialect = connector.engine.dialect.name.upper()

# ══════════════════════════════════════════════
#  Step 1. 테이블 선택
# ══════════════════════════════════════════════
st.markdown("### 1️⃣ ERD에 포함할 테이블 선택")

all_tables = connector.get_table_names()
if not all_tables:
    st.error("테이블 목록을 불러올 수 없습니다.")
    st.stop()

col_sel, col_meta = st.columns([3, 1])
with col_sel:
    selected_tables = st.multiselect(
        "테이블 선택", all_tables,
        default=all_tables[:min(6, len(all_tables))],
        placeholder="ERD에 포함할 테이블을 선택하세요...",
        label_visibility="collapsed",
        help="5~10개 권장. 너무 많으면 ERD가 복잡해집니다."
    )
with col_meta:
    st.metric("선택된 테이블", f"{len(selected_tables)} 개")
    st.caption(f"연결 DB: {db_dialect}")

if not selected_tables:
    st.info("테이블을 선택하면 ERD 생성을 시작할 수 있습니다.")
    st.stop()

# ══════════════════════════════════════════════
#  Step 2. 테이블 구조 미리보기
# ══════════════════════════════════════════════
st.divider()
st.markdown("### 2️⃣ 테이블 구조 확인")

with st.spinner("테이블 구조를 읽는 중..."):
    tables_dict   = {}
    col_types_all = {}
    for t in selected_tables:
        tables_dict[t]   = connector.get_columns(t)
        col_types_all[t] = connector.get_column_types(t)

TYPE_COLOR = {'DATE': '#2196F3', 'NUMBER': '#43A047', 'TEXT': '#FB8C00', 'UNKNOWN': '#9E9E9E'}

n_cols = 3
rows   = [selected_tables[i:i+n_cols] for i in range(0, len(selected_tables), n_cols)]
for row in rows:
    grid = st.columns(n_cols)
    for i, table in enumerate(row):
        with grid[i]:
            cols  = tables_dict[table]
            types = col_types_all[table]
            with st.expander(f"**{table}** ({len(cols)}개 컬럼)", expanded=True):
                for col in cols:
                    col_type  = types.get(col, 'UNKNOWN')
                    color     = TYPE_COLOR.get(col_type, '#9E9E9E')
                    is_likely_pk = col.lower() in [
                        f"{table.lower()}_id", f"{table.lower()}_no",
                        f"{table.lower()}_seq", "id"
                    ]
                    is_likely_fk = (
                        (col.lower().endswith('_id') or col.lower().endswith('_no'))
                        and not is_likely_pk
                    )
                    if is_likely_pk:
                        icon = "🔑"
                    elif is_likely_fk:
                        icon = "🔗"
                    else:
                        icon = "•"
                    st.markdown(
                        f"{icon} **{col}** "
                        f"<span style='background:{color};color:white;padding:1px 6px;"
                        f"border-radius:8px;font-size:10px'>{col_type}</span>",
                        unsafe_allow_html=True
                    )

# ══════════════════════════════════════════════
#  Step 3. 생성 옵션
# ══════════════════════════════════════════════
st.divider()
st.markdown("### 3️⃣ ERD 생성 옵션")

opt1, opt2, opt3 = st.columns(3)
with opt1:
    use_ai      = st.toggle("🤖 AI 관계 추론", value=False,
                            help="Claude AI가 컬럼명 패턴으로 FK 관계를 추론합니다. OFF 시 규칙 기반으로 생성.")
    if use_ai and not os.environ.get('ANTHROPIC_API_KEY'):
        st.caption("⚠️ API 키 없음 → 자동으로 규칙 기반으로 전환")
with opt2:
    show_types  = st.toggle("📊 데이터 타입 표시", value=True,
                            help="ERD 각 컬럼에 데이터 타입을 함께 표시합니다.")
with opt3:
    show_ddl    = st.toggle("📝 DDL 자동 생성", value=True,
                            help="Mermaid 코드 탭에 CREATE TABLE DDL을 함께 생성합니다.")

st.markdown("")

if st.button("🚀 ERD 생성 시작", type="primary", use_container_width=True):
    with st.spinner("AI가 테이블 관계를 분석하고 ERD를 생성하는 중..." if use_ai
                    else "규칙 기반으로 ERD를 생성하는 중..."):
        if use_ai:
            erd_result = infer_erd_relationships(tables_dict)
        else:
            erd_result = _build_rule_based_erd(tables_dict, col_types_all, show_types)

    st.session_state['erd_result']     = erd_result
    st.session_state['erd_show_types'] = show_types
    st.session_state['erd_show_ddl']   = show_ddl

# ══════════════════════════════════════════════
#  Step 4. ERD 결과
# ══════════════════════════════════════════════
if 'erd_result' not in st.session_state:
    st.stop()

st.divider()
st.markdown("### 4️⃣ ERD 결과")

erd       = st.session_state['erd_result']
show_ddl  = st.session_state.get('erd_show_ddl', True)
source    = erd.get('_source', 'ai')

# 상태 배너
if source == 'ai':
    st.success("✅ Claude AI가 관계를 분석하여 ERD를 생성했습니다.")
elif source == 'rule_based':
    st.info("📐 규칙 기반 ERD가 생성되었습니다. 'AI 관계 추론'을 켜면 더 정확해집니다.")
else:
    st.warning(f"⚠️ AI 파싱 실패 → 규칙 기반으로 대체 생성\n\n{erd.get('notes','')}")

tab_preview, tab_code, tab_rel = st.tabs([
    "👁️ ERD 미리보기",
    "📋 Mermaid 코드 & DDL",
    "🔗 관계 분석",
])

# ── 탭 1: 미리보기 ───────────────────────────
with tab_preview:
    mermaid_code = erd.get('mermaid_code', '')
    if mermaid_code:
        mermaid_html = f"""<!DOCTYPE html>
<html><head>
<script src="https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.6.1/mermaid.min.js"></script>
<style>
  body {{ margin:0; background:white; display:flex; justify-content:center; padding:16px; }}
  .mermaid {{ max-width:100%; }}
</style>
</head><body>
<div class="mermaid">{mermaid_code}</div>
<script>mermaid.initialize({{
  startOnLoad: true, theme: 'default',
  er: {{ diagramPadding: 24, layoutDirection: 'TB', minEntityWidth: 120, minEntityHeight: 40 }}
}});</script>
</body></html>"""
        height = max(450, len(selected_tables) * 130)
        st.components.v1.html(mermaid_html, height=height, scrolling=True)
        st.caption("💡 ERD가 작거나 복잡하면 [Mermaid Live Editor](https://mermaid.live)에 코드를 붙여넣어 확인하세요.")
    else:
        st.warning("ERD 코드가 생성되지 않았습니다. ERD 생성 버튼을 다시 눌러주세요.")

# ── 탭 2: 코드 & DDL ─────────────────────────
with tab_code:
    mermaid_code = erd.get('mermaid_code', '')

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**📋 Mermaid 코드**")
        st.code(mermaid_code, language="text")
        st.download_button(
            "⬇️ Mermaid 코드 다운로드 (.mmd)",
            data=mermaid_code.encode('utf-8'),
            file_name=f"erd_{'_'.join(selected_tables[:3])}.mmd",
            mime="text/plain",
            use_container_width=True,
        )
        st.link_button("🌐 Mermaid Live Editor에서 열기",
                        "https://mermaid.live", use_container_width=True)

    with col_b:
        if show_ddl:
            st.markdown("**📝 CREATE TABLE DDL (표준화 기반)**")
            ddl_lines = []
            for table, cols in tables_dict.items():
                types = col_types_all.get(table, {})
                ddl_lines.append(f"-- {table.upper()} 테이블")
                ddl_lines.append(f"CREATE TABLE {table.upper()} (")
                col_ddls = []
                for col in cols:
                    t = types.get(col, 'UNKNOWN')
                    if t == 'DATE':     sql_t = 'DATE'
                    elif t == 'NUMBER': sql_t = 'NUMBER(15)'
                    else:               sql_t = 'VARCHAR2(200)'
                    is_pk   = col.lower() in [f"{table.lower()}_id", f"{table.lower()}_no", f"{table.lower()}_seq"]
                    null_s  = ' NOT NULL' if is_pk else ''
                    col_ddls.append(f"    {col.upper():<30} {sql_t}{null_s}")
                ddl_lines.append(',\n'.join(col_ddls))
                ddl_lines.append(");\n")

            ddl_text = '\n'.join(ddl_lines)
            st.code(ddl_text, language="sql")
            st.download_button(
                "⬇️ DDL 다운로드 (.sql)",
                data=ddl_text.encode('utf-8'),
                file_name=f"ddl_{'_'.join(selected_tables[:3])}.sql",
                mime="text/plain",
                use_container_width=True,
            )

# ── 탭 3: 관계 분석 ──────────────────────────
with tab_rel:
    relationships  = erd.get('relationships', [])
    pk_suggestions = erd.get('pk_suggestions', {})

    if relationships:
        st.markdown(f"**총 {len(relationships)}개의 관계가 추론되었습니다**")
        for rel in relationships:
            conf      = rel.get('confidence', 'low')
            conf_icon = {'high': '🟢', 'medium': '🟡', 'low': '🔴'}.get(conf, '⚪')
            st.markdown(f"""
<div class="rel-card">
  {conf_icon} <b>{rel.get('from_table','').upper()}</b>
  <span style="color:#4F6BED"> ──{rel.get('type','')}──▶ </span>
  <b>{rel.get('to_table','').upper()}</b>
  &nbsp;<span style="font-size:12px;color:#888">
    ({rel.get('from_col','')} → {rel.get('to_col','')})
  </span><br>
  <span style="font-size:12px;color:#666;padding-left:16px">📌 {rel.get('reason','')}</span>
</div>
""", unsafe_allow_html=True)
    else:
        st.info("추론된 관계가 없습니다. 컬럼명에 _id, _no 등 명확한 패턴이 없으면 관계 추론이 어렵습니다.")

    if pk_suggestions:
        st.divider()
        st.markdown("**추천 PK**")
        pk_rows = [{'테이블': t, '추천 PK': pk} for t, pk in pk_suggestions.items()]
        st.dataframe(pd.DataFrame(pk_rows), use_container_width=True, hide_index=True)

    if erd.get('notes'):
        st.divider()
        st.info(f"📝 {erd['notes']}")
