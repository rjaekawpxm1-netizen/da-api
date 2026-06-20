import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.title("📈 진단 결과 분석")

if 'diagnosis_raw_results' not in st.session_state or not st.session_state.diagnosis_raw_results:
    st.warning("⚠️ 진단 결과가 없습니다. [4_diagnosis_run]에서 먼저 진단을 실행해주세요.")
    st.stop()

raw_results  = st.session_state.diagnosis_raw_results
error_store  = st.session_state.get('diagnosis_error_data', {})

raw_df = pd.DataFrame(raw_results)
df = raw_df.rename(columns={
    'rule_name':  '진단 항목',
    'table':      '테이블명',
    'column':     '컬럼명',
    'total_cnt':  '총 건수',
    'error_cnt':  '오류 건수',
    'error_rate': '오류율(%)',
    'error_msg':  '에러 메시지',
})

# 유효한 결과만 분석 (쿼리 실패 -1 제외)
df_valid = df[df['총 건수'] >= 0].copy()
df_fail  = df[df['총 건수'] < 0].copy()
error_df = df_valid[df_valid['오류 건수'] > 0].copy()

# ── 1. 종합 요약 ──────────────────────────────
st.subheader("1. 종합 요약")

total_cnt_sum  = int(df_valid['총 건수'].sum())   if not df_valid.empty else 0
error_cnt_sum  = int(df_valid['오류 건수'].sum())  if not df_valid.empty else 0
overall_rate   = round(error_cnt_sum / total_cnt_sum * 100, 2) if total_cnt_sum > 0 else 0.0

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("총 진단 항목",   f"{len(df_valid)} 개")
k2.metric("오류 발생 항목", f"{len(error_df)} 개")
k3.metric("총 점검 건수",   f"{total_cnt_sum:,} 건")
k4.metric("총 오류 건수",   f"{error_cnt_sum:,} 건")
k5.metric("전체 오류율",    f"{overall_rate:.2f} %")

# 영역별 요약 테이블
st.divider()
st.subheader("2. 영역별 품질 현황")

dim_keywords = {
    '완전성': 'completeness', '일관성': 'consistency', '정확성': 'accuracy',
    '유용성': 'usefulness',   '유일성': 'uniqueness',  '유효성': 'validity',
}
dim_rows = []
for kor, _ in dim_keywords.items():
    mask    = df_valid['진단 항목'].str.contains(kor, na=False)
    sub     = df_valid[mask]
    err_sub = sub[sub['오류 건수'] > 0]
    avg_rate = round(sub['오류율(%)'].mean(), 2) if not sub.empty else 0.0
    grade    = '🟢 양호' if avg_rate == 0 else ('🟡 주의' if avg_rate < 10 else '🔴 위험')
    dim_rows.append({
        '품질 영역':    kor,
        '진단 항목 수': len(sub),
        '오류 항목 수': len(err_sub),
        '총 오류 건수': int(sub['오류 건수'].sum()),
        '평균 오류율':  f"{avg_rate:.2f}%",
        '등급':         grade,
    })

dim_df = pd.DataFrame(dim_rows)
st.dataframe(dim_df, use_container_width=True, hide_index=True)

# ── 3. 시각화 ─────────────────────────────────
if not error_df.empty:
    st.divider()
    st.subheader("3. 오류 발생 현황 시각화")

    tab_chart1, tab_chart2, tab_chart3 = st.tabs(["📊 컬럼별", "📊 항목별", "🎯 레이더 차트"])

    with tab_chart1:
        fig1 = px.bar(
            error_df.sort_values('오류 건수', ascending=False),
            x='컬럼명', y='오류 건수', color='진단 항목',
            text='오류 건수', title="컬럼별 오류 누적 현황",
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig1.update_traces(textposition='outside')
        fig1.update_layout(showlegend=True, height=420)
        st.plotly_chart(fig1, use_container_width=True)

    with tab_chart2:
        fig2 = px.bar(
            error_df.sort_values('오류 건수'),
            y='진단 항목', x='오류 건수', color='컬럼명',
            orientation='h', text='오류 건수',
            title="진단 항목별 오류 현황",
            color_discrete_sequence=px.colors.qualitative.Pastel,
        )
        fig2.update_traces(textposition='outside')
        fig2.update_layout(height=420)
        st.plotly_chart(fig2, use_container_width=True)

    with tab_chart3:
        # 영역별 오류율 레이더 차트
        categories = list(dim_keywords.keys())
        values = []
        for kor in categories:
            mask    = df_valid['진단 항목'].str.contains(kor, na=False)
            sub     = df_valid[mask]
            avg     = sub['오류율(%)'].mean() if not sub.empty else 0.0
            values.append(round(avg, 2))
        values_closed = values + [values[0]]
        cats_closed   = categories + [categories[0]]

        fig3 = go.Figure(go.Scatterpolar(
            r=values_closed, theta=cats_closed,
            fill='toself', fillcolor='rgba(79,107,237,0.2)',
            line=dict(color='#4F6BED', width=2),
            name='오류율(%)'
        ))
        fig3.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, max(values + [1])])),
            title="품질 영역별 오류율 레이더",
            height=420,
        )
        st.plotly_chart(fig3, use_container_width=True)

# ── 4. 드릴다운 ───────────────────────────────
st.divider()
st.subheader("🔍 4. 오류 데이터 원본 추적 (Drill-down)")

if error_df.empty:
    st.success("🎉 오류 데이터가 없습니다. 완벽한 품질입니다!")
else:
    # error_store의 index는 raw_results 기준 — df_valid의 index와 매핑
    error_options = []
    for orig_idx, row in df_valid[df_valid['오류 건수'] > 0].iterrows():
        label = (f"[{row['진단 항목']}]  {row['컬럼명']}  "
                 f"— 오류 {int(row['오류 건수']):,}건 ({row['오류율(%)']:.2f}%)")
        error_options.append((orig_idx, label))

    selected_label = st.selectbox(
        "확인할 항목 선택",
        options=[label for _, label in error_options],
        label_visibility="collapsed"
    )

    selected_orig_idx = next(idx for idx, label in error_options if label == selected_label)
    detail_df = error_store.get(selected_orig_idx)

    if detail_df is not None and not detail_df.empty:
        st.caption(f"총 **{len(detail_df):,}건**의 오류 데이터")
        st.dataframe(detail_df, use_container_width=True, height=300)

        csv = detail_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📥 이 오류 데이터 CSV 다운로드",
            data=csv,
            file_name=f"오류_{selected_label[:20].strip()}.csv",
            mime='text/csv',
        )
    else:
        st.info("상세 쿼리가 정의되지 않았거나 데이터를 불러올 수 없습니다.")

# ── 5. 쿼리 실패 항목 ────────────────────────
if not df_fail.empty:
    st.divider()
    st.subheader("⚠️ 5. 실패한 진단 항목")
    st.caption("쿼리 오류로 실행되지 못한 항목입니다. YAML 규칙이나 DB 문법을 확인하세요.")
    fail_show = df_fail[['진단 항목', '컬럼명']].copy()
    if '에러 메시지' in df_fail.columns:
        fail_show['에러'] = df_fail['에러 메시지'].values
    st.dataframe(fail_show, use_container_width=True, hide_index=True)
