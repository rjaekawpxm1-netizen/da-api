import streamlit as st
import sys, os, json
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
from core.standard_loader import suggest_standard_name, load_standard_documents, STANDARD_WORD_DICT
from core.llm_advisor import recommend_column_standards, analyze_diagnosis_results


st.markdown("""
<style>
.ai-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 14px; padding: 22px 28px;
    color: white; margin-bottom: 24px;
}
.ai-header h2 { margin: 0 0 4px 0; font-size: 22px; }
.ai-header p  { margin: 0; opacity: 0.85; font-size: 13px; }

.conf-high   { color: #43A047; font-weight: 700; }
.conf-medium { color: #FB8C00; font-weight: 700; }
.conf-low    { color: #E53935; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="ai-header">
  <h2>🤖 AI 표준화 어드바이저</h2>
  <p>공공데이터베이스 표준화 관리 매뉴얼 2026 기반 · 컬럼명 표준화 · 진단 결과 AI 분석</p>
</div>
""", unsafe_allow_html=True)

# ── 문서 로드 ─────────────────────────────────
@st.cache_resource(show_spinner="표준화 가이드 문서를 로드하는 중...")
def load_docs():
    return load_standard_documents()

doc_chunks = load_docs()
st.caption(f"📚 표준화 가이드 {len(doc_chunks)}개 청크 로드 완료")

# ── 탭 구성 ──────────────────────────────────
tab_col, tab_ai, tab_dict = st.tabs([
    "📋 컬럼 표준화 추천",
    "🔍 AI 진단 분석",
    "📖 표준단어 사전",
])

# ══════════════════════════════════════════════
#  탭 1: 컬럼 표준화 추천
# ══════════════════════════════════════════════
with tab_col:
    st.subheader("컬럼명 → 공공데이터 표준명 추천")
    st.caption("행정안전부 공공데이터베이스 표준화 관리 매뉴얼 2026 기준으로 컬럼명 표준화를 추천합니다.")

    input_mode = st.radio(
        "입력 방식", ["연결된 DB에서 선택", "직접 입력"],
        horizontal=True, label_visibility="collapsed"
    )

    selected_table   = None
    columns_to_check = []
    column_types     = {}

    if input_mode == "연결된 DB에서 선택":
        if 'connected' not in st.session_state or not st.session_state.connected:
            st.warning("⚠️ [2_data_connect]에서 먼저 DB를 연결해주세요.")
        else:
            connector = st.session_state.connector
            tables    = connector.get_table_names()
            col_a, col_b = st.columns([2, 1])
            with col_a:
                selected_table = st.selectbox("테이블 선택", tables)
            if selected_table:
                all_cols     = connector.get_columns(selected_table)
                column_types = connector.get_column_types(selected_table)
                columns_to_check = st.multiselect(
                    "표준화 검토할 컬럼 선택", all_cols, default=all_cols
                )
    else:
        col_a, col_b = st.columns([1, 1])
        with col_a:
            selected_table = st.text_input("테이블명", placeholder="예) 신청정보")
        with col_b:
            st.markdown("")
        raw_input = st.text_area(
            "컬럼명 목록 (한 줄에 하나씩)",
            placeholder="기관코드\n등록일자\n처리여부\n신청금액\n담당자명",
            height=150,
        )
        if raw_input:
            columns_to_check = [c.strip() for c in raw_input.split('\n') if c.strip()]

    st.divider()

    if columns_to_check:
        btn1, btn2 = st.columns(2)

        with btn1:
            run_fast = st.button("⚡ 빠른 추천 (규칙 기반)", use_container_width=True,
                                 help="API 없이 즉시 결과. 행안부 표준화 규칙 사전 기반.")
        with btn2:
            run_ai = st.button("🤖 AI 정밀 추천 (Claude API)", type="primary",
                               use_container_width=True,
                               help="Claude AI가 매뉴얼을 참조하여 정밀 분석. 10~30초 소요.")

        # ── 빠른 추천 ────────────────────────
        if run_fast:
            results = []
            for col in columns_to_check:
                col_type = column_types.get(col, 'UNKNOWN')
                r        = suggest_standard_name(col, actual_db_type=col_type)
                results.append({
                    '원래 컬럼명':    col,
                    'DB 타입':       col_type,
                    '표준 영문약어':  r.get('recommended', '-'),
                    '도메인':        r.get('domain', '-'),
                    '권장 데이터타입': r.get('data_type', '-'),
                    '신뢰도':        r.get('confidence', 'low'),
                    '사용 예시':     r.get('example', '-'),
                })
            st.session_state['std_fast_df'] = pd.DataFrame(results)
            st.session_state.pop('std_ai_result', None)

        # ── AI 정밀 추천 ─────────────────────
        if run_ai:
            if not selected_table:
                st.warning("테이블명을 입력해주세요.")
            elif not __import__('os').environ.get('ANTHROPIC_API_KEY'):
                # API 키 없으면 규칙 기반으로 자동 폴백
                st.info("ℹ️ ANTHROPIC_API_KEY 미설정 → 규칙 기반 추천으로 자동 전환합니다.")
                results = []
                for col in columns_to_check:
                    col_type = column_types.get(col, 'UNKNOWN')
                    r = suggest_standard_name(col, actual_db_type=col_type)
                    results.append({
                        '원래 컬럼명':    col,
                        'DB 타입':       column_types.get(col, '-'),
                        '표준 영문약어':  r.get('recommended', '-'),
                        '도메인':        r.get('domain', '-'),
                        '권장 데이터타입': r.get('data_type', '-'),
                        '신뢰도':        r.get('confidence', 'low'),
                        '사용 예시':     r.get('example', '-'),
                    })
                st.session_state['std_fast_df'] = pd.DataFrame(results)
                st.session_state.pop('std_ai_result', None)
            else:
                with st.spinner("Claude AI가 매뉴얼을 참조하여 분석 중입니다... (10~30초)"):
                    ai_result = recommend_column_standards(
                        columns_to_check, selected_table,
                        column_types, doc_chunks
                    )
                st.session_state['std_ai_result'] = ai_result
                st.session_state.pop('std_fast_df', None)

        # ── 결과 출력: 빠른 추천 ─────────────
        if 'std_fast_df' in st.session_state:
            df = st.session_state['std_fast_df']
            st.markdown("#### ⚡ 규칙 기반 추천 결과")

            def color_conf(val):
                c = {'high': '#E8F5E9', 'medium': '#FFF8E1', 'low': '#FFEBEE'}
                return f"background-color: {c.get(val, '')}"

            st.dataframe(
                df.style.map(color_conf, subset=['신뢰도']),
                use_container_width=True, hide_index=True
            )
            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                "📥 결과 CSV 다운로드", csv,
                f"{selected_table or 'columns'}_표준화추천.csv", "text/csv",
                use_container_width=True,
            )

        # ── 결과 출력: AI 추천 ───────────────
        if 'std_ai_result' in st.session_state:
            ai = st.session_state['std_ai_result']
            st.markdown("#### 🤖 AI 정밀 추천 결과")

            if isinstance(ai, dict) and 'error' in str(ai.get('_source', '')):
                st.error(f"API 오류: {ai}")
            else:
                if ai.get('table_name_suggestion'):
                    st.info(f"📌 **테이블명 표준화 제안:** `{ai['table_name_suggestion']}`")
                if ai.get('overall_assessment'):
                    st.markdown(f"> {ai['overall_assessment']}")

                cols_data = ai.get('columns', [])
                if cols_data:
                    rows = []
                    for c in cols_data:
                        conf = c.get('confidence', 'low')
                        icon = {'high': '🟢', 'medium': '🟡', 'low': '🔴'}.get(conf, '⚪')
                        rows.append({
                            '원래 컬럼명':     c.get('original', ''),
                            '표준 한글용어':   c.get('recommended_kr', '-'),
                            '표준 영문약어':   c.get('recommended_en', '-'),
                            '도메인':         c.get('domain', '-'),
                            '권장 데이터타입': c.get('data_type', '-'),
                            '신뢰도':         f"{icon} {conf}",
                            '추천 근거':      c.get('reason', '-'),
                            '문제점':         c.get('issues') or '-',
                        })
                    ai_df = pd.DataFrame(rows)
                    st.dataframe(ai_df, use_container_width=True,
                                 hide_index=True, height=380)
                    csv2 = ai_df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        "📥 AI 추천 결과 CSV", csv2,
                        f"{selected_table}_AI표준화추천.csv", "text/csv",
                        use_container_width=True,
                    )

        # API 안내
        with st.expander("ℹ️ AI 정밀 추천 사용 안내"):
            st.markdown("""
**Claude API 연결 방법:**
- claude.ai 환경에서는 자동으로 연결됩니다.
- 별도 서버 배포 시 `ANTHROPIC_API_KEY` 환경변수 설정이 필요합니다.
- API 미연결 시 **규칙 기반 빠른 추천**을 사용하세요.
""")

# ══════════════════════════════════════════════
#  탭 2: AI 진단 분석
# ══════════════════════════════════════════════
with tab_ai:
    st.subheader("품질진단 결과 AI 분석 & 보고서 의견 자동 생성")
    st.caption("4번 화면에서 실행한 품질진단 결과를 Claude AI가 분석하여 원인, 권고사항, 보고서 문구를 생성합니다.")

    if 'diagnosis_raw_results' not in st.session_state or not st.session_state.diagnosis_raw_results:
        st.warning("⚠️ [4_diagnosis_run]에서 품질진단을 먼저 실행해주세요.")
    else:
        raw_results = st.session_state.diagnosis_raw_results
        df_raw      = pd.DataFrame(raw_results)
        valid_df    = df_raw[df_raw['total_cnt'] >= 0] if not df_raw.empty else df_raw
        error_count = len(valid_df[valid_df['error_cnt'] > 0]) if not valid_df.empty else 0
        table_name  = raw_results[0].get('table', '진단테이블') if raw_results else ''

        # 현재 진단 요약
        m1, m2, m3 = st.columns(3)
        m1.metric("총 진단 항목",   f"{len(valid_df)} 개")
        m2.metric("오류 발생 항목", f"{error_count} 개")
        m3.metric("대상 테이블",    table_name)

        st.markdown("")

        if st.button("🤖 AI 분석 시작", type="primary", use_container_width=True):
            with st.spinner("Claude AI가 진단 결과를 분석 중입니다... (10~30초)"):
                ai_analysis = analyze_diagnosis_results(raw_results, table_name)
            st.session_state['ai_analysis'] = ai_analysis

        if 'ai_analysis' in st.session_state:
            analysis = st.session_state['ai_analysis']

            st.divider()

            # 요약
            st.markdown("#### 📊 AI 분석 요약")
            st.info(analysis.get('summary', ''))

            # 이슈별 상세
            issues = analysis.get('issues', [])
            if issues and isinstance(issues[0], dict) and 'likely_cause' in issues[0]:
                st.markdown("#### 🚨 주요 이슈 상세")
                for issue in issues:
                    sev  = issue.get('severity', 'low')
                    icon = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(sev, '⚪')
                    with st.expander(f"{icon} **{issue.get('column', '')}** — {issue.get('rule', '')}"):
                        col_l, col_r = st.columns(2)
                        col_l.markdown(f"**예상 원인**\n\n{issue.get('likely_cause', '-')}")
                        col_r.markdown(f"**업무 영향도**\n\n{issue.get('impact', '-')}")

            # 권고사항
            recs = analysis.get('recommendations', [])
            if recs:
                st.markdown("#### ✅ 조치 권고사항")
                for i, rec in enumerate(recs, 1):
                    st.markdown(f"**{i}.** {rec}")

            # 보고서 문구
            report_comment = analysis.get('report_comment', '')
            if report_comment:
                st.markdown("#### 📄 보고서 종합 의견 자동 생성 (공문체)")
                st.text_area(
                    "아래 내용을 복사하여 보고서에 사용하세요",
                    report_comment, height=160,
                    label_visibility="collapsed"
                )
                st.download_button(
                    "📥 종합 의견 텍스트 다운로드",
                    data=report_comment.encode('utf-8'),
                    file_name=f"{table_name}_AI종합의견.txt",
                    mime="text/plain",
                    use_container_width=True,
                )

# ══════════════════════════════════════════════
#  탭 3: 표준단어 사전
# ══════════════════════════════════════════════
with tab_dict:
    st.subheader("공공데이터 표준단어 사전")
    st.caption("행정안전부 공공데이터베이스 표준화 관리 매뉴얼 2026 기준 형식단어(도메인 단어) 목록")

    search = st.text_input("🔍 단어 검색", placeholder="코드, 번호, DT, AMT ...")

    rows = []
    for word, meta in STANDARD_WORD_DICT.items():
        if search:
            q = search.lower()
            if (q not in word.lower()
                    and q not in meta.get('abbr','').lower()
                    and q not in meta.get('eng','').lower()):
                continue
        rows.append({
            '한글 표준단어':   word,
            '영문명':         meta.get('eng', ''),
            '영문약어 (컬럼 suffix)': meta.get('abbr', ''),
            '도메인 분류':    meta.get('domain', ''),
            '권장 데이터타입': meta.get('type', ''),
            '사용 예시':     meta.get('example', ''),
        })

    dict_df = pd.DataFrame(rows)
    st.dataframe(dict_df, use_container_width=True, hide_index=True, height=480)

    st.divider()
    st.markdown("#### 💡 공공데이터 표준화 핵심 규칙")
    st.markdown("""
| 구성 원칙 | 내용 |
|---|---|
| **컬럼명 구조** | 수식어(업무단어) + 형식단어(도메인단어) |
| **영문 표기** | 영문약어명으로 표현, 언더스코어(`_`) 구분 |
| **예시** | 기관코드 → `INST_CD` / 등록일자 → `REG_DT` / 사용여부 → `USE_YN` |
| **대소문자** | 영문약어 대문자 사용 권장 |
| **테이블명** | `TB_업무명_엔티티유형` 형태 권장 (예: `TB_APLY_INFO`) |
| **적용 기준** | 공공기관의 데이터베이스 표준화 지침 (행정안전부고시 제2025-19호) |
""")
