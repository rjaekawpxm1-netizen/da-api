"""
standard_loader.py
공공데이터베이스 표준화 관리 매뉴얼 PDF를 읽어
Claude API에 전달할 수 있는 청크 구조로 변환합니다.
"""

import os
import re
import json
import subprocess
from pathlib import Path


# core/ 폴더 기준으로 상위 폴더의 standards/ 를 찾음
# 실행 위치에 관계없이 동작
_this_dir     = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_this_dir)  # core/ 의 상위 = 프로젝트 루트
STANDARDS_DIR = os.path.join(_project_root, 'standards')
CACHE_PATH    = os.path.join(STANDARDS_DIR, '_cache.json')


# ──────────────────────────────────────────────
#  표준 영문약어 사전 (매뉴얼 핵심 지식 하드코딩)
#  - 매뉴얼에서 반복 언급되는 핵심 표준단어 목록
#  - Claude API 호출 없이도 기본 추천 가능
# ──────────────────────────────────────────────
STANDARD_WORD_DICT = {
    # 형식단어 (Domain Word) - 컬럼명 맨 뒤에 붙는 단어
    '코드':     {'eng': 'CODE',   'abbr': 'CD',   'domain': '코드',   'type': 'CHAR',    'example': '기관코드 → INST_CD'},
    '번호':     {'eng': 'NUMBER', 'abbr': 'NO',   'domain': '번호',   'type': 'VARCHAR', 'example': '등록번호 → REG_NO'},
    '명':       {'eng': 'NAME',   'abbr': 'NM',   'domain': '명칭',   'type': 'VARCHAR', 'example': '기관명 → INST_NM'},
    '명칭':     {'eng': 'NAME',   'abbr': 'NM',   'domain': '명칭',   'type': 'VARCHAR', 'example': '업무명칭 → TASK_NM'},
    '일자':     {'eng': 'DATE',   'abbr': 'DT',   'domain': '날짜',   'type': 'CHAR(8)', 'example': '등록일자 → REG_DT'},
    '일시':     {'eng': 'DATETIME','abbr': 'DTM', 'domain': '일시',   'type': 'CHAR(14)','example': '처리일시 → PROC_DTM'},
    '금액':     {'eng': 'AMOUNT', 'abbr': 'AMT',  'domain': '금액',   'type': 'NUMBER',  'example': '지급금액 → PAY_AMT'},
    '수량':     {'eng': 'QUANTITY','abbr': 'QTY', 'domain': '수량',   'type': 'NUMBER',  'example': '신청수량 → APLY_QTY'},
    '여부':     {'eng': 'BOOLEAN','abbr': 'YN',   'domain': '여부',   'type': 'CHAR(1)', 'example': '사용여부 → USE_YN'},
    '수':       {'eng': 'COUNT',  'abbr': 'CNT',  'domain': '수',     'type': 'NUMBER',  'example': '처리수 → PROC_CNT'},
    '건수':     {'eng': 'COUNT',  'abbr': 'CNT',  'domain': '수',     'type': 'NUMBER',  'example': '신청건수 → APLY_CNT'},
    '내용':     {'eng': 'CONTENT','abbr': 'CONT', 'domain': '내용',   'type': 'VARCHAR', 'example': '처리내용 → PROC_CONT'},
    '주소':     {'eng': 'ADDRESS','abbr': 'ADDR', 'domain': '주소',   'type': 'VARCHAR', 'example': '소재지주소 → LOC_ADDR'},
    '순번':     {'eng': 'SEQUENCE','abbr': 'SEQ', 'domain': '순번',   'type': 'NUMBER',  'example': '처리순번 → PROC_SEQ'},
    '비율':     {'eng': 'RATIO',  'abbr': 'RT',   'domain': '비율',   'type': 'NUMBER',  'example': '달성비율 → ACHV_RT'},
    '구분':     {'eng': 'TYPE',   'abbr': 'TP',   'domain': '구분',   'type': 'CHAR',    'example': '사업구분 → BIZ_TP'},
    '유형':     {'eng': 'TYPE',   'abbr': 'TP',   'domain': '유형',   'type': 'CHAR',    'example': '서비스유형 → SVC_TP'},
    '상태':     {'eng': 'STATUS', 'abbr': 'STS',  'domain': '상태',   'type': 'CHAR',    'example': '처리상태 → PROC_STS'},
    '설명':     {'eng': 'DESCRIPTION','abbr': 'DESC','domain':'설명', 'type': 'VARCHAR', 'example': '업무설명 → TASK_DESC'},
    '경로':     {'eng': 'PATH',   'abbr': 'PATH', 'domain': '경로',   'type': 'VARCHAR', 'example': '파일경로 → FILE_PATH'},
    '크기':     {'eng': 'SIZE',   'abbr': 'SIZE', 'domain': '크기',   'type': 'NUMBER',  'example': '파일크기 → FILE_SIZE'},
    '아이디':   {'eng': 'ID',     'abbr': 'ID',   'domain': '식별자', 'type': 'VARCHAR', 'example': '사용자아이디 → USER_ID'},
    '식별자':   {'eng': 'ID',     'abbr': 'ID',   'domain': '식별자', 'type': 'VARCHAR', 'example': '기관식별자 → INST_ID'},
    '연도':     {'eng': 'YEAR',   'abbr': 'YR',   'domain': '연도',   'type': 'CHAR(4)', 'example': '사업연도 → BIZ_YR'},
    '연월':     {'eng': 'YEAR_MONTH','abbr': 'YM','domain': '연월',   'type': 'CHAR(6)', 'example': '기준연월 → BASE_YM'},
}

# 수식어 (업무단어) 표준 영문약어
STANDARD_PREFIX_DICT = {
    '기관':   'INST',  '사업':   'BIZ',   '업무':   'TASK',  '서비스': 'SVC',
    '처리':   'PROC',  '등록':   'REG',   '신청':   'APLY',  '승인':   'APRVL',
    '접수':   'RCPT',  '발급':   'ISSU',  '관리':   'MGMT',  '운영':   'OPER',
    '사용자': 'USER',  '담당자': 'CHRG',  '담당':   'CHRG',  '부서':   'DEPT',
    '기준':   'BASE',  '대상':   'TGT',   '결과':   'RSLT',  '계획':   'PLAN',
    '현황':   'STAT',  '목록':   'LIST',  '상세':   'DTL',   '요청':   'REQ',
    '응답':   'RES',   '파일':   'FILE',  '데이터': 'DATA',  '정보':   'INFO',
    '내역':   'DTL',   '이력':   'HIST',  '통계':   'STAT',  '합계':   'TOT',
    '소재지': 'LOC',   '주민':   'RSD',   '법인':   'CORP',  '사업자': 'BIZ',
    '전화':   'TEL',   '팩스':   'FAX',   '이메일': 'EMAIL', '홈페이지':'HP',
    '달성':   'ACHV',  '목표':   'GOAL',  '실적':   'PERF',  '평가':   'EVAL',
    '사용':   'USE',   '수신':   'RCV',   '발신':   'SND',   '입력':   'INP',
    '출력':   'OUT',   '변경':   'CHG',   '삭제':   'DEL',   '조회':   'INQ',
    '생성':   'CRT',   '확인':   'CFM',   '완료':   'CMPL',  '취소':   'CNCL',
    '반려':   'RJCT',  '이관':   'TRNF',  '최초':   'FRST',  '최종':   'LAST',
    '총':     'TOT',   '일반':   'GEN',   '공통':   'CMN',   '현재':   'CUR',
    '이전':   'PRV',   '다음':   'NXT',   '임시':   'TMP',   '원본':   'ORG',
}


def extract_text_from_pdf(pdf_path: str) -> str:
    """PDF에서 텍스트 추출 (pdftotext 사용)"""
    try:
        result = subprocess.run(
            ['pdftotext', '-layout', pdf_path, '-'],
            capture_output=True, text=True, timeout=60
        )
        return result.stdout
    except Exception as e:
        return f"PDF 텍스트 추출 실패: {str(e)}"


def clean_text(text: str) -> str:
    """추출된 텍스트 정제"""
    text = text.replace('\f', '\n')
    text = re.sub(r'[·]{2,}[\s\d]*', '', text)
    text = re.sub(r'공공데이터베이스 표준화 관리 매뉴얼\s*', '', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    lines = [l.strip() for l in text.split('\n') if l.strip() and len(l.strip()) > 3]
    return '\n'.join(lines)


def chunk_text(text: str, chunk_size: int = 2000, overlap: int = 200) -> list:
    """텍스트를 청크로 분할"""
    chunks = []
    paragraphs = text.split('\n\n')
    current_chunk = []
    current_len   = 0

    for para in paragraphs:
        para_len = len(para)
        if current_len + para_len > chunk_size and current_chunk:
            chunks.append('\n\n'.join(current_chunk))
            # overlap: 마지막 단락 유지
            current_chunk = current_chunk[-1:] if current_chunk else []
            current_len   = len(current_chunk[0]) if current_chunk else 0
        current_chunk.append(para)
        current_len += para_len

    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))

    return chunks


def load_standard_documents() -> list:
    """
    standards/ 폴더의 PDF/TXT 파일들을 읽어서 청크 목록 반환
    캐시가 있으면 캐시 사용
    """
    os.makedirs(STANDARDS_DIR, exist_ok=True)

    # 캐시 확인
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass

    chunks = []
    standards_path = Path(STANDARDS_DIR)

    for file_path in sorted(standards_path.glob('*')):
        if file_path.suffix.lower() == '.pdf':
            raw_text = extract_text_from_pdf(str(file_path))
        elif file_path.suffix.lower() in ['.txt', '.md']:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_text = f.read()
        else:
            continue

        clean = clean_text(raw_text)
        file_chunks = chunk_text(clean)

        for i, chunk in enumerate(file_chunks):
            chunks.append({
                'source':   file_path.name,
                'chunk_id': i,
                'text':     chunk,
            })

    # 캐시 저장
    if chunks:
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)

    return chunks


def get_relevant_chunks(query: str, chunks: list, top_k: int = 5) -> list:
    """
    쿼리와 관련된 청크를 키워드 매칭으로 찾기
    (벡터DB 없이 단순 키워드 기반 - 충분히 효과적)
    """
    query_words = set(re.findall(r'[가-힣a-zA-Z]+', query.lower()))

    scored = []
    for chunk in chunks:
        text = chunk['text'].lower()
        chunk_words = set(re.findall(r'[가-힣a-zA-Z]+', text))
        # 교집합 점수
        score = len(query_words & chunk_words)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]



# ──────────────────────────────────────────────
#  영문 약어 Suffix 사전 (영문 컬럼명 처리용)
# ──────────────────────────────────────────────
ENGLISH_SUFFIX_DICT = {
    '_id'      : {'domain': '식별자',   'data_type': 'NUMBER',        'abbr': 'ID',    'confidence': 'high'},
    '_cd'      : {'domain': '코드',     'data_type': 'CHAR',          'abbr': 'CD',    'confidence': 'high'},
    '_nm'      : {'domain': '명칭',     'data_type': 'VARCHAR2(200)',  'abbr': 'NM',    'confidence': 'high'},
    '_name'    : {'domain': '명칭',     'data_type': 'VARCHAR2(200)',  'abbr': 'NM',    'confidence': 'high'},
    '_no'      : {'domain': '번호',     'data_type': 'VARCHAR2(50)',   'abbr': 'NO',    'confidence': 'high'},
    '_dtm'     : {'domain': '일시',     'data_type': 'DATE',          'abbr': 'DTM',   'confidence': 'high'},
    '_dt'      : {'domain': '날짜',     'data_type': 'DATE',          'abbr': 'DT',    'confidence': 'high'},
    '_amt'     : {'domain': '금액',     'data_type': 'NUMBER(15)',     'abbr': 'AMT',   'confidence': 'high'},
    '_qty'     : {'domain': '수량',     'data_type': 'NUMBER(10)',     'abbr': 'QTY',   'confidence': 'high'},
    '_cnt'     : {'domain': '수',       'data_type': 'NUMBER(10)',     'abbr': 'CNT',   'confidence': 'high'},
    '_yn'      : {'domain': '여부',     'data_type': 'CHAR(1)',        'abbr': 'YN',    'confidence': 'high'},
    '_seq'     : {'domain': '순번',     'data_type': 'NUMBER(10)',     'abbr': 'SEQ',   'confidence': 'high'},
    '_tp'      : {'domain': '구분',     'data_type': 'CHAR',          'abbr': 'TP',    'confidence': 'high'},
    '_sts'     : {'domain': '상태',     'data_type': 'CHAR',          'abbr': 'STS',   'confidence': 'high'},
    '_rt'      : {'domain': '비율',     'data_type': 'NUMBER(5,2)',   'abbr': 'RT',    'confidence': 'high'},
    '_addr'    : {'domain': '주소',     'data_type': 'VARCHAR2(500)',  'abbr': 'ADDR',  'confidence': 'high'},
    '_tel'     : {'domain': '전화번호', 'data_type': 'VARCHAR2(20)',   'abbr': 'TEL',   'confidence': 'high'},
    '_email'   : {'domain': '이메일',   'data_type': 'VARCHAR2(100)',  'abbr': 'EMAIL', 'confidence': 'high'},
    '_url'     : {'domain': 'URL',      'data_type': 'VARCHAR2(500)',  'abbr': 'URL',   'confidence': 'high'},
    '_path'    : {'domain': '경로',     'data_type': 'VARCHAR2(500)',  'abbr': 'PATH',  'confidence': 'high'},
    '_size'    : {'domain': '크기',     'data_type': 'NUMBER(15)',     'abbr': 'SIZE',  'confidence': 'high'},
    '_desc'    : {'domain': '설명',     'data_type': 'VARCHAR2(4000)', 'abbr': 'DESC',  'confidence': 'high'},
    '_cont'    : {'domain': '내용',     'data_type': 'VARCHAR2(4000)', 'abbr': 'CONT',  'confidence': 'high'},
    '_yr'      : {'domain': '연도',     'data_type': 'CHAR(4)',        'abbr': 'YR',    'confidence': 'high'},
    '_ym'      : {'domain': '연월',     'data_type': 'CHAR(6)',        'abbr': 'YM',    'confidence': 'high'},
    '_level'   : {'domain': '단계',     'data_type': 'NUMBER(3)',      'abbr': 'LEVEL', 'confidence': 'medium'},
    '_type'    : {'domain': '구분',     'data_type': 'CHAR',          'abbr': 'TP',    'confidence': 'medium'},
    '_code'    : {'domain': '코드',     'data_type': 'CHAR',          'abbr': 'CD',    'confidence': 'medium'},
    '_date'    : {'domain': '날짜',     'data_type': 'DATE',          'abbr': 'DT',    'confidence': 'medium'},
    '_num'     : {'domain': '번호',     'data_type': 'NUMBER',        'abbr': 'NO',    'confidence': 'medium'},
    '_count'   : {'domain': '수',       'data_type': 'NUMBER(10)',     'abbr': 'CNT',   'confidence': 'medium'},
    '_amount'  : {'domain': '금액',     'data_type': 'NUMBER(15)',     'abbr': 'AMT',   'confidence': 'medium'},
    '_flag'    : {'domain': '여부',     'data_type': 'CHAR(1)',        'abbr': 'YN',    'confidence': 'medium'},
    '_memo'    : {'domain': '메모',     'data_type': 'VARCHAR2(4000)', 'abbr': 'MEMO',  'confidence': 'medium'},
    '_remark'  : {'domain': '비고',     'data_type': 'VARCHAR2(4000)', 'abbr': 'RMK',   'confidence': 'medium'},
    '_grade'   : {'domain': '등급',     'data_type': 'CHAR',          'abbr': 'GRADE', 'confidence': 'medium'},
}

def _is_english_colname(name: str) -> bool:
    """영문/약어 형태의 컬럼명인지 판별 (한글 없고 언더스코어 포함)"""
    import re
    return bool(re.match(r'^[a-zA-Z0-9_]+$', name))


def _suggest_from_english(col_name: str) -> dict:
    """
    영문 컬럼명 → 표준화 추천
    예) category_id → 식별자/NUMBER/high
        use_yn      → 여부/CHAR(1)/high
        catg_nm     → 명칭/VARCHAR2(200)/high
    """
    col_lower = col_name.lower()
    recommended = col_name.upper()  # 기본값: 대문자 그대로

    # suffix 순서 중요: 긴 것부터 먼저 매칭 (예: _dtm > _dt)
    sorted_suffixes = sorted(ENGLISH_SUFFIX_DICT.keys(), key=len, reverse=True)

    for suffix in sorted_suffixes:
        if col_lower.endswith(suffix):
            meta = ENGLISH_SUFFIX_DICT[suffix]
            return {
                'input':       col_name,
                'recommended': recommended,
                'domain':      meta['domain'],
                'data_type':   meta['data_type'],
                'example':     f"{col_name} → {recommended}",
                'confidence':  meta['confidence'],
                'prefix_abbr': col_name.upper().replace(suffix.upper(), ''),
                'suffix_abbr': meta['abbr'],
            }

    # suffix 매칭 실패 → low
    return {
        'input':       col_name,
        'recommended': recommended,
        'domain':      '',
        'data_type':   '',
        'example':     '',
        'confidence':  'low',
        'prefix_abbr': '',
        'suffix_abbr': '',
    }


def suggest_standard_name(korean_name: str) -> dict:
    """
    컬럼명 → 표준 영문약어명 추천 (규칙 기반)
    - 한글 컬럼명: 한글 형식단어 사전으로 매칭
    - 영문 컬럼명: 영문 suffix 사전으로 매칭
    Claude API 없이도 기본 추천 가능
    """
    # 영문 컬럼명이면 영문 suffix 기반으로 처리
    if _is_english_colname(korean_name):
        return _suggest_from_english(korean_name)

    suggestions = {
        'input':        korean_name,
        'prefix_abbr':  '',
        'suffix_abbr':  '',
        'recommended':  '',
        'domain':       '',
        'data_type':    '',
        'example':      '',
        'confidence':   'low',
    }

    # 형식단어(suffix) 매칭
    matched_suffix = None
    matched_prefix = None

    for word, meta in STANDARD_WORD_DICT.items():
        if korean_name.endswith(word):
            matched_suffix = (word, meta)
            break

    # 수식어(prefix) 매칭
    remaining = korean_name
    if matched_suffix:
        remaining = korean_name[:-len(matched_suffix[0])]

    for word, abbr in STANDARD_PREFIX_DICT.items():
        if word in remaining:
            matched_prefix = (word, abbr)
            break

    # 추천명 조합
    if matched_suffix:
        suffix_abbr = matched_suffix[1]['abbr']
        prefix_abbr = matched_prefix[1] if matched_prefix else remaining.upper()[:6]

        suggestions['suffix_abbr']  = suffix_abbr
        suggestions['prefix_abbr']  = prefix_abbr
        suggestions['recommended']  = f"{prefix_abbr}_{suffix_abbr}"
        suggestions['domain']       = matched_suffix[1]['domain']
        suggestions['data_type']    = matched_suffix[1]['type']
        suggestions['example']      = matched_suffix[1]['example']
        suggestions['confidence']   = 'high' if matched_prefix else 'medium'
    else:
        suggestions['recommended']  = korean_name.upper()[:20]
        suggestions['confidence']   = 'low'

    return suggestions