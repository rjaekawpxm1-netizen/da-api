import streamlit as st
import pandas as pd
import sys, os

sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
from core.diagnosis_engine import DiagnosisEngine


st.markdown("""
<style>
.result-pass { color: #43A047; font-weight: 700; }
.result-fail { color: #E53935; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

st.title("▶️ 진단 실행")

if 'diagnosis_queries' not in st.session_state or not st.session_state.diagnosis_queries:
    st.warning("⚠️ [3_diagnosis_set]에서 진단 쿼리를 먼저 생성해주세요.")
    st.stop()

queries      = st.session_state.diagnosis_queries
total_queries = len(queries)

st.info(f"총 **{total_queries}개**의 진단 쿼리가 대기 중입니다.")

if st.button("🚀 품질진단 시작하기", type="primary", use_container_width=True):
    progress_bar = st.progress(0)
    status_text  = st.empty()

    engine  = DiagnosisEngine()
    db_conn = st.session_state.connector.engine

    def update_progress(current, total, rule_name, column_name):
        progress_bar.progress(int((current / total) * 100))
        status_text.markdown(
            f"**진행 중 ({current}/{total})** — "
            f"`{column_name}` 컬럼 · `{rule_name}` 검사 중..."
        )

    with st.spinner("데이터를 분석하고 있습니다..."):
        # engine이 (results, error_store) 튜플로 반환
        raw_results, error_store = engine.run_queries(
            db_conn, queries, progress_callback=update_progress
        )

    progress_bar.empty()
    status_text.success("✅ 품질진단이 완료되었습니다!")

    # 세션 저장
    # raw_results : DataFrame 없는 순수 딕셔너리 리스트 → 직렬화 안전
    # error_store : { index: DataFrame } → 드릴다운 전용
    st.session_state.diagnosis_raw_results = raw_results
    st.session_state.diagnosis_error_data  = error_store

    # 화면 표시용 DataFrame
    display_df = pd.DataFrame(raw_results).rename(columns={
        'rule_name':  '진단 항목',
        'table':      '테이블명',
        'column':     '컬럼명',
        'total_cnt':  '총 건수',
        'error_cnt':  '오류 건수',
        'error_rate': '오류율(%)',
        'error_msg':  '에러 메시지',
    })

    base_cols = ['진단 항목', '컬럼명', '총 건수', '오류 건수', '오류율(%)']
    if '테이블명'   in display_df.columns: base_cols.insert(1, '테이블명')
    if '에러 메시지' in display_df.columns: base_cols.append('에러 메시지')

    st.session_state.diagnosis_results_df = display_df[
        [c for c in base_cols if c in display_df.columns]
    ]

# ── 결과 표시 ─────────────────────────────────
if 'diagnosis_results_df' not in st.session_state:
    st.stop()

df = st.session_state.diagnosis_results_df
raw = pd.DataFrame(st.session_state.get('diagnosis_raw_results', []))

st.divider()

# KPI 카드
valid = raw[raw['total_cnt'] >= 0] if not raw.empty else raw
fail  = raw[raw['total_cnt'] < 0]  if not raw.empty else raw

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("총 진단 항목",   f"{len(valid)} 개")
k2.metric("오류 발생",      f"{len(valid[valid['error_cnt']>0])} 개",
          delta=f"{len(valid[valid['error_cnt']>0])} 건 오류" if len(valid[valid['error_cnt']>0]) > 0 else "이상 없음",
          delta_color="inverse" if len(valid[valid['error_cnt']>0]) > 0 else "off")
k3.metric("총 점검 건수",   f"{int(valid['total_cnt'].sum()):,} 건" if not valid.empty else "0 건")
k4.metric("총 오류 건수",   f"{int(valid['error_cnt'].sum()):,} 건" if not valid.empty else "0 건")
k5.metric("쿼리 실패",      f"{len(fail)} 개",
          delta="확인 필요" if len(fail) > 0 else "없음",
          delta_color="inverse" if len(fail) > 0 else "off")

st.subheader("📊 진단 결과 요약")

def highlight_row(row):
    styles = [''] * len(row)
    err_col_idx = list(row.index).index('오류 건수') if '오류 건수' in row.index else -1
    rate_col_idx = list(row.index).index('오류율(%)') if '오류율(%)' in row.index else -1
    total_col_idx = list(row.index).index('총 건수') if '총 건수' in row.index else -1

    if total_col_idx >= 0 and row.iloc[total_col_idx] == -1:
        # 쿼리 실패 행 → 회색
        return ['background-color: #f0f0f0; color: #999'] * len(row)

    if err_col_idx >= 0:
        val = row.iloc[err_col_idx]
        if isinstance(val, (int, float)) and val > 0:
            styles[err_col_idx]  = 'background-color: #FFEBEE; color: #C62828; font-weight:700'
        if rate_col_idx >= 0:
            styles[rate_col_idx] = 'background-color: #FFEBEE; color: #C62828; font-weight:700'
    return styles

st.dataframe(
    df.style.apply(highlight_row, axis=1),
    use_container_width=True,
    height=min(80 + len(df) * 35, 700),
)

# 다운로드
csv = df.to_csv(index=False).encode('utf-8-sig')
st.download_button(
    "📥 진단 결과 CSV 다운로드",
    data=csv,
    file_name="진단결과.csv",
    mime="text/csv",
)
