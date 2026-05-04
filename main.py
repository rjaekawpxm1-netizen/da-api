"""
DA 도우미 FastAPI 백엔드
React ↔ FastAPI ↔ Oracle/MySQL/PostgreSQL
"""
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os, json, tempfile

from connector import DataConnector
from diagnosis_engine import DiagnosisEngine
from query_builder import QueryBuilder
from standard_loader import suggest_standard_name, STANDARD_WORD_DICT, STANDARD_PREFIX_DICT

app = FastAPI(title="DA 도우미 API", version="1.0.0")

# CORS 설정 (React 개발서버 + Vercel 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 배포 시 도메인 지정
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 세션 대신 인메모리 커넥터 관리 (단순화) ──────
_connectors: Dict[str, DataConnector] = {}

def get_connector(session_id: str) -> DataConnector:
    if session_id not in _connectors:
        _connectors[session_id] = DataConnector()
    return _connectors[session_id]


# ══════════════════════════════════════════════
#  모델 정의
# ══════════════════════════════════════════════

class DBConnectRequest(BaseModel):
    session_id: str
    db_type: str          # postgresql | mysql
    host: str
    port: str
    user: str
    password: str
    dbname: str

class OracleHostRequest(BaseModel):
    session_id: str
    host: str
    port: str
    service_name: str
    user: str
    password: str

class OracleTNSRequest(BaseModel):
    session_id: str
    tns_string: str
    user: str
    password: str

class DiagnosisRequest(BaseModel):
    session_id: str
    table: str
    column_rule_map: Dict[str, List[str]]  # { col: [rule_ids] }
    db_type: str = "sqlite"

class StandardizeRequest(BaseModel):
    columns: List[str]

class ProjectModel(BaseModel):
    org_name: str
    project_name: str
    manager: Optional[str] = ""


# ══════════════════════════════════════════════
#  헬스체크
# ══════════════════════════════════════════════

@app.get("/")
def root():
    return {"status": "ok", "message": "DA 도우미 API"}

@app.get("/health")
def health():
    return {"status": "healthy"}


# ══════════════════════════════════════════════
#  DB 연결
# ══════════════════════════════════════════════

@app.post("/api/connect/db")
def connect_db(req: DBConnectRequest):
    conn = get_connector(req.session_id)
    ok, msg = conn.connect_db(req.db_type, req.host, req.port, req.user, req.password, req.dbname)
    return {"success": ok, "message": msg}

@app.post("/api/connect/oracle-host")
def connect_oracle_host(req: OracleHostRequest):
    conn = get_connector(req.session_id)
    ok, msg = conn.connect_oracle_host(req.host, req.port, req.service_name, req.user, req.password)
    return {"success": ok, "message": msg}

@app.post("/api/connect/oracle-tns")
def connect_oracle_tns(req: OracleTNSRequest):
    conn = get_connector(req.session_id)
    ok, msg = conn.connect_oracle_tns(req.tns_string, req.user, req.password)
    return {"success": ok, "message": msg}

@app.post("/api/connect/oracle-wallet")
async def connect_oracle_wallet(
    session_id: str,
    tns_alias: str,
    user: str,
    password: str,
    wallet_password: str = "",
    files: List[UploadFile] = File(...),
):
    conn = get_connector(session_id)
    wallet_dict = {}
    for f in files:
        content = await f.read()
        wallet_dict[f.filename] = content
    ok, msg = conn.connect_oracle_wallet_files(wallet_dict, tns_alias, user, password, wallet_password)
    return {"success": ok, "message": msg}

@app.post("/api/connect/file")
async def connect_file(session_id: str, file: UploadFile = File(...)):
    conn = get_connector(session_id)
    # UploadFile → file-like object 변환
    import io
    content = await file.read()
    file_like = io.BytesIO(content)
    file_like.name = file.filename
    ok, msg = conn.load_file_to_sqlite(file_like)
    return {"success": ok, "message": msg}

@app.get("/api/connect/status/{session_id}")
def connect_status(session_id: str):
    if session_id not in _connectors:
        return {"connected": False}
    conn = _connectors[session_id]
    connected = conn.engine is not None
    db_type = ""
    if connected:
        db_type = conn.engine.dialect.name.upper()
    return {"connected": connected, "db_type": db_type}


# ══════════════════════════════════════════════
#  테이블 / 컬럼 정보
# ══════════════════════════════════════════════

@app.get("/api/tables/{session_id}")
def get_tables(session_id: str):
    conn = get_connector(session_id)
    if not conn.engine:
        raise HTTPException(400, "DB가 연결되지 않았습니다")
    return {"tables": conn.get_table_names()}

@app.get("/api/tables/{session_id}/{table_name}/columns")
def get_columns(session_id: str, table_name: str):
    conn = get_connector(session_id)
    if not conn.engine:
        raise HTTPException(400, "DB가 연결되지 않았습니다")
    columns = conn.get_columns(table_name)
    types   = conn.get_column_types(table_name)
    return {
        "columns": columns,
        "types": types,
    }


# ══════════════════════════════════════════════
#  진단 규칙 목록
# ══════════════════════════════════════════════

@app.get("/api/rules")
def get_rules():
    qb = QueryBuilder()
    all_rules = qb.load_all_templates()
    return {"rules": all_rules}


# ══════════════════════════════════════════════
#  진단 실행
# ══════════════════════════════════════════════

@app.post("/api/diagnose")
def run_diagnosis(req: DiagnosisRequest):
    conn = get_connector(req.session_id)
    if not conn.engine:
        raise HTTPException(400, "DB가 연결되지 않았습니다")

    qb = QueryBuilder()
    all_rules_by_dim = qb.load_all_templates()
    all_rules_flat   = []
    for dim_key, rules in all_rules_by_dim.items():
        for r in rules:
            r['_dim'] = dim_key
            all_rules_flat.append(r)

    queries = qb.build_queries_per_column(
        req.table, req.column_rule_map, all_rules_flat, req.db_type
    )

    engine = DiagnosisEngine()
    results, error_store = engine.run_queries(conn.engine, queries)

    # error_store의 DataFrame을 JSON으로 변환
    error_data = {}
    for idx, df in error_store.items():
        if df is not None and not df.empty:
            error_data[str(idx)] = df.head(100).to_dict(orient="records")
        else:
            error_data[str(idx)] = []

    return {
        "results": results,
        "error_data": error_data,
        "total": len(results),
    }


# ══════════════════════════════════════════════
#  데이터 표준화 추천
# ══════════════════════════════════════════════

@app.post("/api/standardize")
def standardize_columns(req: StandardizeRequest):
    results = {}
    for col in req.columns:
        results[col] = suggest_standard_name(col)
    return {"results": results}

@app.get("/api/standard-dict")
def get_standard_dict():
    return {
        "word_dict":   STANDARD_WORD_DICT,
        "prefix_dict": STANDARD_PREFIX_DICT,
    }


# ══════════════════════════════════════════════
#  AI 표준화 추천 (Claude API)
# ══════════════════════════════════════════════

@app.post("/api/ai/standardize")
def ai_standardize(session_id: str, table_name: str, req: StandardizeRequest):
    try:
        from llm_advisor import recommend_column_standards, load_standard_documents
        conn    = get_connector(session_id)
        types   = {}
        if conn.engine:
            types = conn.get_column_types(table_name) if table_name else {}
        chunks  = load_standard_documents()
        result  = recommend_column_standards(req.columns, table_name, types, chunks)
        return result
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/ai/analyze-diagnosis")
def ai_analyze(session_id: str, table_name: str, body: Dict[str, Any]):
    try:
        from llm_advisor import analyze_diagnosis_results
        result = analyze_diagnosis_results(body.get("results", []), table_name)
        return result
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/ai/erd")
def ai_erd(session_id: str):
    try:
        from llm_advisor import infer_erd_relationships
        conn = get_connector(session_id)
        if not conn.engine:
            raise HTTPException(400, "DB가 연결되지 않았습니다")
        tables = conn.get_table_names()
        tables_dict = {t: conn.get_columns(t) for t in tables[:10]}
        result = infer_erd_relationships(tables_dict)
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


# ══════════════════════════════════════════════
#  보고서 생성
# ══════════════════════════════════════════════

@app.post("/api/report/excel")
def generate_excel(body: Dict[str, Any]):
    try:
        from report_generator import ReportGenerator
        rg = ReportGenerator()
        path = rg.generate_excel(body.get("project_info", {}), body.get("results", []))
        with open(path, "rb") as f:
            content = f.read()
        import base64
        return {"file_base64": base64.b64encode(content).decode(), "filename": os.path.basename(path)}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/report/pdf")
def generate_pdf(body: Dict[str, Any]):
    try:
        from report_generator import ReportGenerator
        rg = ReportGenerator()
        path = rg.generate_pdf(body.get("project_info", {}), body.get("results", []))
        with open(path, "rb") as f:
            content = f.read()
        import base64
        return {"file_base64": base64.b64encode(content).decode(), "filename": os.path.basename(path)}
    except Exception as e:
        raise HTTPException(500, str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
