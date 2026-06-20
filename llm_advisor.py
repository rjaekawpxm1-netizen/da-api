"""
llm_advisor.py
Claude API를 활용한 공공데이터 표준화 추천 엔진
"""

import json
import re
import sys
import os
import requests
import pandas as pd

# core/ 폴더 안에서 실행될 때 standard_loader를 못 찾는 문제 해결
_core_dir = os.path.dirname(os.path.abspath(__file__))
if _core_dir not in sys.path:
    sys.path.insert(0, _core_dir)

from standard_loader import (
    load_standard_documents,
    get_relevant_chunks,
    suggest_standard_name,
    STANDARD_WORD_DICT,
    STANDARD_PREFIX_DICT,
)


CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL   = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """당신은 대한민국 공공데이터베이스 표준화 전문가입니다.
행정안전부의 「공공기관의 데이터베이스 표준화 지침」과 「공공데이터베이스 표준화 관리 매뉴얼 2026」을 완벽하게 숙지하고 있습니다.

핵심 원칙:
1. 공통표준용어는 "공통표준단어 + 형식단어(도메인단어)"로 구성됩니다.
2. 컬럼명(속성명)은 영문약어명으로 표현하며, 수식어_형식단어 형태입니다. (예: INST_CD, REG_DT)
3. 주요 형식단어 영문약어: 코드→CD, 번호→NO, 명(칭)→NM, 일자→DT, 금액→AMT, 여부→YN, 수/건수→CNT, 순번→SEQ
4. 테이블명은 업무명_엔티티유형으로 구성합니다. (예: TB_USER_INFO)
5. 추천 시 반드시 근거(매뉴얼 기준)를 제시하세요.

응답은 반드시 JSON 형식으로만 답하세요. 다른 텍스트는 포함하지 마세요."""


# ──────────────────────────────────────────────
#  공통: Claude API 호출
# ──────────────────────────────────────────────
def call_claude_api(messages: list, system: str = SYSTEM_PROMPT,
                    max_tokens: int = 2000) -> str:
    """
    Claude API 호출.
    API 키 없음 / 네트워크 오류 / 타임아웃 시 {"error": "..."} JSON 반환.
    호출부에서 반드시 예외 처리할 것.
    """
    # API 키 환경변수 확인 (없으면 즉시 에러 반환 - 타임아웃 대기 없음)
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key

    try:
        resp = requests.post(
            CLAUDE_API_URL,
            headers=headers,
            json={
                "model":      CLAUDE_MODEL,
                "max_tokens": max_tokens,
                "system":     system,
                "messages":   messages,
            },
            timeout=60,
        )
        data = resp.json()

        # 401 인증 오류
        if resp.status_code == 401:
            return json.dumps({"error": "API_KEY_MISSING"})
        # 기타 HTTP 오류
        if resp.status_code != 200:
            err_msg = data.get('error', {}).get('message', f'HTTP {resp.status_code}')
            return json.dumps({"error": err_msg})

        if 'content' in data:
            return ''.join(
                block.get('text', '')
                for block in data['content']
                if block.get('type') == 'text'
            )
        elif 'error' in data:
            return json.dumps({"error": data['error'].get('message', '알 수 없는 오류')})
        return json.dumps({"error": "API 응답 형식 오류"})

    except requests.exceptions.Timeout:
        return json.dumps({"error": "API_TIMEOUT"})
    except requests.exceptions.ConnectionError:
        return json.dumps({"error": "API_CONNECTION_ERROR"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _parse_json_response(response: str) -> dict:
    """API 응답에서 JSON 파싱 (코드블록 제거 포함)"""
    clean = response.strip()
    # ```json ... ``` 또는 ``` ... ``` 제거
    clean = re.sub(r'```json\s*', '', clean)
    clean = re.sub(r'```\s*', '', clean)
    clean = clean.strip()
    return json.loads(clean)


# ══════════════════════════════════════════════
#  기능 1: 컬럼 표준화 추천
# ══════════════════════════════════════════════
def recommend_column_standards(columns: list, table_name: str,
                                column_types: dict, doc_chunks: list) -> dict:
    # 규칙 기반 빠른 추천
    rule_based = {col: suggest_standard_name(col, actual_db_type=column_types.get(col, 'UNKNOWN'))
                  for col in columns}

    query    = f"컬럼명 표준화 영문약어 {' '.join(columns[:5])}"
    relevant = get_relevant_chunks(query, doc_chunks, top_k=3)
    context  = '\n\n'.join([c['text'][:800] for c in relevant])

    col_info = [
        {
            'original':        col,
            'db_type':         column_types.get(col, 'UNKNOWN'),
            'rule_suggestion': rule_based[col].get('recommended', ''),
            'confidence':      rule_based[col].get('confidence', 'low'),
        }
        for col in columns
    ]

    # JSON 형식을 문자열로 직접 작성 (f-string 중괄호 충돌 방지)
    format_example = (
        '{\n'
        '  "columns": [\n'
        '    {\n'
        '      "original": "원래컬럼명",\n'
        '      "recommended_kr": "표준 한글용어명",\n'
        '      "recommended_en": "표준 영문약어명 (예: INST_CD)",\n'
        '      "domain": "도메인분류명 (예: 코드, 날짜, 명칭)",\n'
        '      "data_type": "권장 데이터타입 (예: VARCHAR2(100), CHAR(8), NUMBER(15))",\n'
        '      "reason": "추천 근거 (매뉴얼 기준 1-2문장)",\n'
        '      "confidence": "high|medium|low",\n'
        '      "issues": "현재 컬럼명의 문제점 (없으면 null)"\n'
        '    }\n'
        '  ],\n'
        '  "table_name_suggestion": "테이블명 표준화 제안 (예: TB_CART_INFO)",\n'
        '  "overall_assessment": "전체 표준화 수준 평가 (1-2문장)"\n'
        '}'
    )

    prompt = (
        f"다음은 공공기관 DB 테이블 '{table_name}'의 컬럼 목록입니다.\n"
        "공공데이터베이스 표준화 관리 매뉴얼 기준으로 표준화를 추천해주세요.\n\n"
        "## 컬럼 목록\n"
        f"{json.dumps(col_info, ensure_ascii=False, indent=2)}\n\n"
        "## 관련 매뉴얼 내용\n"
        f"{context[:1500]}\n\n"
        "## 응답 형식 (JSON만, 다른 텍스트 없이)\n"
        f"{format_example}"
    )

    response = call_claude_api([{"role": "user", "content": prompt}])

    try:
        return _parse_json_response(response)
    except Exception:
        return {
            "columns": [
                {
                    "original":       col,
                    "recommended_en": rule_based[col].get('recommended', col.upper()),
                    "domain":         rule_based[col].get('domain', ''),
                    "data_type":      rule_based[col].get('data_type', ''),
                    "reason":         "규칙 기반 자동 추천",
                    "confidence":     rule_based[col].get('confidence', 'low'),
                    "issues":         None,
                }
                for col in columns
            ],
            "table_name_suggestion": f"TB_{table_name.upper()}_INFO",
            "overall_assessment":    "규칙 기반 추천 (API 미연결 상태)",
            "_source": "rule_based",
        }


# ══════════════════════════════════════════════
#  기능 2: 진단 결과 AI 코멘트
# ══════════════════════════════════════════════
def analyze_diagnosis_results(raw_results: list, table_name: str) -> dict:
    df       = pd.DataFrame(raw_results)
    error_df = df[df['error_cnt'] > 0] if not df.empty and 'error_cnt' in df.columns else pd.DataFrame()

    if error_df.empty:
        return {
            "summary": "오류가 발견되지 않아 AI 분석이 필요하지 않습니다.",
            "issues": [],
            "recommendations": ["현재 데이터 품질 수준이 양호합니다. 정기적인 품질 모니터링을 권장합니다."]
        }

    error_summary = [
        {
            "진단항목": row.get('rule_name', ''),
            "컬럼":     row.get('column', ''),
            "오류건수": int(row.get('error_cnt', 0)),
            "오류율":   f"{row.get('error_rate', 0):.1f}%",
        }
        for _, row in error_df.iterrows()
    ]

    format_example = (
        '{\n'
        '  "summary": "전체 품질 현황 요약 (2-3문장)",\n'
        '  "issues": [\n'
        '    {\n'
        '      "column": "컬럼명",\n'
        '      "rule": "진단항목",\n'
        '      "likely_cause": "예상 원인",\n'
        '      "severity": "high|medium|low",\n'
        '      "impact": "업무 영향도"\n'
        '    }\n'
        '  ],\n'
        '  "recommendations": ["조치 권고사항 1", "조치 권고사항 2"],\n'
        '  "report_comment": "공공기관 보고서에 들어갈 종합 의견 (공문체, 3-5문장)"\n'
        '}'
    )

    prompt = (
        f"공공기관 DB 테이블 '{table_name}'의 품질진단 결과입니다.\n\n"
        "## 오류 발생 항목\n"
        f"{json.dumps(error_summary, ensure_ascii=False, indent=2)}\n\n"
        "위 품질 오류에 대해 분석해주세요.\n\n"
        "## 응답 형식 (JSON만, 다른 텍스트 없이)\n"
        f"{format_example}"
    )

    response = call_claude_api([{"role": "user", "content": prompt}], max_tokens=1500)

    try:
        return _parse_json_response(response)
    except Exception:
        return {
            "summary":          f"총 {len(error_df)}개 항목에서 오류가 발견되었습니다.",
            "issues":           error_summary,
            "recommendations":  ["오류 데이터를 확인하고 데이터 입력 프로세스를 점검하세요."],
            "report_comment":   "진단 결과 일부 항목에서 품질 오류가 발견되었으며, 조치가 필요합니다.",
            "_source": "fallback",
        }


# ══════════════════════════════════════════════
#  기능 3: ERD 관계 추론
# ══════════════════════════════════════════════

def _build_fallback_erd(tables: dict) -> dict:
    """AI 실패 시 규칙 기반 ERD 자동 생성"""
    mermaid_lines = ["erDiagram"]
    relationships = []
    all_tables    = list(tables.keys())

    for table, cols in tables.items():
        mermaid_lines.append(f"    {table.upper()} " + "{")
        for col in cols[:10]:
            is_num = any(s in col.lower() for s in ['id','no','cnt','seq','amt','qty','price'])
            dtype  = "int" if is_num else "string"
            is_pk  = col.lower() in [
                f"{table.lower()}_id", f"{table.lower()}_no",
                f"{table.lower()}_seq", "id"
            ]
            pk_str = " PK" if is_pk else ""
            mermaid_lines.append(f"        {dtype} {col}{pk_str}")
        mermaid_lines.append("    }")

    # 컬럼명 패턴으로 FK 관계 추론
    added_rels = set()
    for t1 in all_tables:
        for col in tables[t1]:
            for t2 in all_tables:
                if t1 == t2:
                    continue
                candidates = [
                    f"{t2.lower()}_id",
                    f"{t2.lower()}_no",
                    f"{t2.lower()}_seq",
                ]
                if col.lower() in candidates:
                    rel_key = f"{t2}:{t1}"
                    if rel_key not in added_rels:
                        added_rels.add(rel_key)
                        rel_line = f"    {t2.upper()} " + "||--o{" + f" {t1.upper()} : has"
                        mermaid_lines.append(rel_line)
                        relationships.append({
                            "from_table": t2, "to_table": t1,
                            "from_col":   col, "to_col": col,
                            "type":       "1:N", "confidence": "medium",
                            "reason":     f"{col} 컬럼명 패턴으로 추론",
                        })

    return {
        "mermaid_code":   '\n'.join(mermaid_lines),
        "relationships":  relationships,
        "pk_suggestions": {t: f"{t.lower()}_id" for t in all_tables},
        "notes":          "규칙 기반 ERD",
        "_source":        "fallback",
    }


def infer_erd_relationships(tables: dict) -> dict:
    """
    tables: { table_name: [col_names, ...] }
    → Mermaid ERD 코드 + 관계 설명 반환
    AI 실패 시 규칙 기반으로 자동 대체
    """
    tables_info = [
        f"테이블: {table}\n컬럼: {', '.join(cols)}"
        for table, cols in tables.items()
    ]
    tables_text = '\n\n'.join(tables_info)

    # Mermaid 코드에 중괄호{}가 포함되어 f-string과 충돌하므로
    # 응답 형식을 일반 문자열로 작성
    format_example = (
        '{\n'
        '  "mermaid_code": "erDiagram\\n    MEMBER {\\n        int member_id PK\\n    }\\n    CART {\\n        int cart_id PK\\n        int member_id\\n    }\\n    MEMBER ||--o{ CART : has",\n'
        '  "relationships": [\n'
        '    {\n'
        '      "from_table": "MEMBER",\n'
        '      "to_table": "CART",\n'
        '      "from_col": "member_id",\n'
        '      "to_col": "member_id",\n'
        '      "type": "1:N",\n'
        '      "confidence": "high",\n'
        '      "reason": "cart 테이블의 member_id가 member PK 참조"\n'
        '    }\n'
        '  ],\n'
        '  "pk_suggestions": {"MEMBER": "member_id", "CART": "cart_id"},\n'
        '  "notes": "분석 특이사항"\n'
        '}'
    )

    prompt = (
        "다음 공공기관 DB 테이블들의 관계를 추론하여 ERD를 생성해주세요.\n"
        "컬럼명 패턴(_id, _cd, _no, _seq 등)을 분석하여 FK 관계를 추론하세요.\n\n"
        "## 테이블 목록\n"
        f"{tables_text}\n\n"
        "## 응답 형식 (반드시 JSON만, 다른 텍스트 없이)\n"
        f"{format_example}"
    )

    response = call_claude_api([{"role": "user", "content": prompt}], max_tokens=2000)

    try:
        result = _parse_json_response(response)

        # mermaid_code 필수 검증
        mermaid = result.get('mermaid_code', '').strip()
        if not mermaid or not mermaid.startswith('erDiagram'):
            raise ValueError(f"mermaid_code 형식 오류: '{mermaid[:50]}'")

        result['_source'] = 'ai'
        return result

    except Exception as e:
        # AI 실패 → 규칙 기반으로 자동 대체
        fallback         = _build_fallback_erd(tables)
        fallback['notes'] = f"AI 파싱 실패 → 규칙 기반 ERD 생성 ({str(e)[:60]})"
        fallback['_source'] = 'fallback'
        return fallback