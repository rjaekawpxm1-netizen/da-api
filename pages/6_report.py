import streamlit as st
import sys
import os
import datetime

sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
from core.report_generator import ReportGenerator


st.title("📄 보고서 출력")
st.markdown("진단 결과를 **엑셀** 및 **PDF** 형식의 공식 보고서로 출력합니다.")

# ──────────────────────────────────────────────
#  사전 조건 체크
# ──────────────────────────────────────────────

if "diagnosis_raw_results" not in st.session_state or not st.session_state.diagnosis_raw_results:
    st.warning("⚠️ 진단 결과가 없습니다. [4_diagnosis_run] 에서 먼저 진단을 실행해주세요.")
    st.stop()

raw_results = st.session_state.diagnosis_raw_results


# ──────────────────────────────────────────────
#  프로젝트 정보 수집
# ──────────────────────────────────────────────

st.subheader("1. 보고서 기본 정보 확인")
st.info("아래 정보는 보고서 표지와 개요 시트에 자동으로 들어갑니다.")

# 세션에 프로젝트 정보가 있으면 자동으로 채워줌
cp = st.session_state.get("current_project", {}) or {}

col1, col2, col3 = st.columns([2, 2, 1])
with col1:
    org_name     = st.text_input("기관명 *",  value=cp.get("org_name", ""),     placeholder="예) 행정안전부")
    project_name = st.text_input("사업명 *",  value=cp.get("project_name", ""), placeholder="예) 2025 공공데이터 품질진단")
with col2:
    manager      = st.text_input("담당자명",  value=cp.get("manager", ""),       placeholder="예) 홍길동")
    table_names = list({r.get("table", "") for r in raw_results if r.get("table")})
    table_name_str = ", ".join(table_names) if table_names else "-"
    st.text_input("대상 테이블 (자동)", value=table_name_str, disabled=True)
with col3:
    st.markdown("**기관 로고** (선택)")
    logo_file = st.file_uploader("로고 이미지", type=["png","jpg","jpeg"],
                                  label_visibility="collapsed",
                                  help="보고서 표지에 삽입됩니다. PNG 권장.")
    if logo_file:
        st.image(logo_file, width=80)
        logo_file.seek(0)
        st.session_state['report_logo'] = logo_file.read()
    else:
        st.session_state.setdefault('report_logo', None)

st.divider()


# ──────────────────────────────────────────────
#  진단 결과 미리보기
# ──────────────────────────────────────────────

st.subheader("2. 진단 결과 미리보기")

import pandas as pd

summary_rows = []
for r in raw_results:
    summary_rows.append({
        "진단 항목":  r.get("rule_name", ""),
        "테이블명":   r.get("table", ""),
        "컬럼명":     r.get("column", ""),
        "총 건수":    r.get("total_cnt", 0),
        "오류 건수":  r.get("error_cnt", 0),
        "오류율(%)":  f"{r.get('error_rate', 0.0):.2f}%",
    })
summary_df = pd.DataFrame(summary_rows)

total_items  = len(summary_df)
error_items  = len(summary_df[summary_df["오류 건수"] > 0])
total_errors = summary_df["오류 건수"].sum()

# KPI 카드
m1, m2, m3, m4 = st.columns(4)
m1.metric("총 진단 항목",    f"{total_items} 개")
m2.metric("오류 발생 항목",   f"{error_items} 개",
          delta=f"-{error_items}" if error_items > 0 else "0",
          delta_color="inverse")
m3.metric("총 점검 건수",    f"{summary_df['총 건수'].sum():,} 건")
m4.metric("총 오류 건수",    f"{int(total_errors):,} 건",
          delta=f"-{int(total_errors)}" if total_errors > 0 else "0",
          delta_color="inverse")

st.dataframe(summary_df, use_container_width=True, hide_index=True)

st.divider()


# ──────────────────────────────────────────────
#  보고서 생성 & 다운로드
# ──────────────────────────────────────────────

st.subheader("3. 보고서 생성 및 다운로드")

if not org_name.strip() or not project_name.strip():
    st.warning("기관명과 사업명을 입력한 후 보고서를 생성하세요.")
    st.stop()

project_info = {
    "org_name":     org_name.strip(),
    "project_name": project_name.strip(),
    "manager":      manager.strip(),
    "table_name":   table_name_str,
    "logo_bytes":   st.session_state.get('report_logo'),
}

col_excel, col_pdf = st.columns(2)

# ── 엑셀 보고서 ──
with col_excel:
    st.markdown("#### 📊 엑셀 보고서")
    st.caption("• 3개 시트 구성 (진단개요 / 상세결과 / 영역별요약)\n• 오류 항목 자동 강조\n• 영역별 차트 포함")

    if st.button("📊 엑셀 보고서 생성", type="primary", use_container_width=True):
        with st.spinner("엑셀 보고서를 생성하고 있습니다..."):
            try:
                rg = ReportGenerator()
                excel_path = rg.generate_excel(project_info, raw_results)

                with open(excel_path, "rb") as f:
                    excel_bytes = f.read()

                fname = f"{project_name.strip()}_품질진단결과_{datetime.date.today()}.xlsx"
                st.download_button(
                    label="⬇️ 엑셀 파일 다운로드",
                    data=excel_bytes,
                    file_name=fname,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
                st.success("✅ 엑셀 보고서 생성 완료!")

                # 이력 자동 저장
                if st.session_state.get("current_project"):
                    try:
                        import sqlite3, datetime, pandas as pd
                        pid = st.session_state.current_project["id"]
                        _df = pd.DataFrame(raw_results)
                        _total  = len(_df)
                        _errors = len(_df[_df['error_cnt'] > 0]) if 'error_cnt' in _df.columns else 0
                        _ecnt   = int(_df['error_cnt'].sum()) if 'error_cnt' in _df.columns else 0
                        con = sqlite3.connect("history.db")
                        con.execute(
                            "INSERT INTO diagnosis_history "
                            "(project_id, table_name, total_items, error_items, total_errors, diagnosed_at) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (pid, table_name_str, _total, _errors, _ecnt,
                             datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                        )
                        con.commit()
                        con.close()
                        st.caption("📝 진단 이력이 저장되었습니다.")
                    except Exception as _e:
                        st.caption(f"이력 저장 생략: {_e}")

            except Exception as e:
                st.error(f"❌ 엑셀 생성 실패: {str(e)}")

# ── PDF 보고서 ──
with col_pdf:
    st.markdown("#### 📋 PDF 보고서")
    st.caption("• 공식 제출용 보고서 형식\n• 진단 개요 + 상세 결과 + 종합 의견\n• A4 규격")

    if st.button("📋 PDF 보고서 생성", type="primary", use_container_width=True):
        with st.spinner("PDF 보고서를 생성하고 있습니다..."):
            try:
                rg = ReportGenerator()
                pdf_path = rg.generate_pdf(project_info, raw_results)

                with open(pdf_path, "rb") as f:
                    pdf_bytes = f.read()

                fname = f"{project_name.strip()}_품질진단결과_{datetime.date.today()}.pdf"
                st.download_button(
                    label="⬇️ PDF 파일 다운로드",
                    data=pdf_bytes,
                    file_name=fname,
                    mime="application/pdf",
                    use_container_width=True,
                )
                st.success("✅ PDF 보고서 생성 완료!")

            except Exception as e:
                st.error(f"❌ PDF 생성 실패: {str(e)}")

st.divider()

# ──────────────────────────────────────────────
#  한 번에 둘 다 생성
# ──────────────────────────────────────────────

st.subheader("4. 엑셀 + PDF 한 번에 생성")

if st.button("🚀 전체 보고서 일괄 생성", use_container_width=True):
    with st.spinner("보고서를 생성하고 있습니다..."):
        rg = ReportGenerator()
        errors = []
        results_ready = {}

        try:
            excel_path = rg.generate_excel(project_info, raw_results)
            with open(excel_path, "rb") as f:
                results_ready["excel"] = f.read()
        except Exception as e:
            errors.append(f"엑셀: {str(e)}")

        try:
            pdf_path = rg.generate_pdf(project_info, raw_results)
            with open(pdf_path, "rb") as f:
                results_ready["pdf"] = f.read()
        except Exception as e:
            errors.append(f"PDF: {str(e)}")

    if errors:
        for err in errors:
            st.error(f"❌ {err}")

    today = datetime.date.today()
    pname = project_name.strip()

    if "excel" in results_ready:
        st.download_button(
            label=f"⬇️ {pname}_품질진단결과_{today}.xlsx",
            data=results_ready["excel"],
            file_name=f"{pname}_품질진단결과_{today}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    if "pdf" in results_ready:
        st.download_button(
            label=f"⬇️ {pname}_품질진단결과_{today}.pdf",
            data=results_ready["pdf"],
            file_name=f"{pname}_품질진단결과_{today}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    if not errors:
        st.success("✅ 전체 보고서 생성 완료! 위 버튼에서 다운로드하세요.")
