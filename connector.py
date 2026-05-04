import pandas as pd
from sqlalchemy import create_engine, inspect, text
import os
import tempfile
import shutil

class DataConnector:
    def __init__(self):
        self.engine      = None
        self.db_type     = None
        self._wallet_dir = None

    def _cleanup_wallet(self):
        if self._wallet_dir and os.path.isdir(self._wallet_dir):
            shutil.rmtree(self._wallet_dir, ignore_errors=True)
            self._wallet_dir = None

    def connect_db(self, db_type, host, port, user, pw, dbname):
        try:
            if db_type.lower() == 'postgresql':
                db_url = f"postgresql://{user}:{pw}@{host}:{port}/{dbname}"
            elif db_type.lower() == 'mysql':
                db_url = f"mysql+pymysql://{user}:{pw}@{host}:{port}/{dbname}"
            else:
                return False, "지원하지 않는 DB 타입입니다."
            self.engine = create_engine(db_url)
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            self.db_type = 'RDB'
            return True, "DB 연결에 성공했습니다."
        except Exception as e:
            return False, f"DB 연결 실패: {str(e)}"

    def connect_oracle_host(self, host, port, service_name, user, pw):
        try:
            import oracledb
            try: oracledb.init_oracle_client()
            except: pass
            db_url = f"oracle+oracledb://{user}:{pw}@{host}:{port}/?service_name={service_name}"
            self.engine = create_engine(db_url, thick_mode=False)
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1 FROM DUAL"))
            self.db_type = 'RDB'
            return True, f"Oracle 연결 성공 (host): {host}:{port}/{service_name}"
        except Exception as e:
            return False, f"Oracle 연결 실패: {str(e)}"

    def connect_oracle_tns(self, tns_string, user, pw):
        try:
            import oracledb
            try: oracledb.init_oracle_client()
            except: pass
            db_url = f"oracle+oracledb://{user}:{pw}@{tns_string}"
            self.engine = create_engine(db_url, thick_mode=False)
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1 FROM DUAL"))
            self.db_type = 'RDB'
            return True, "Oracle 연결 성공 (TNS)"
        except Exception as e:
            return False, f"Oracle TNS 연결 실패: {str(e)}"

    def connect_oracle_wallet_files(self, wallet_files: dict, tns_alias: str,
                                     user: str, pw: str, wallet_pw: str = None):
        try:
            import oracledb
            self._cleanup_wallet()
            tmp_dir = tempfile.mkdtemp(prefix="ora_wallet_")
            self._wallet_dir = tmp_dir
            for filename, file_content in wallet_files.items():
                with open(os.path.join(tmp_dir, filename), "wb") as f:
                    f.write(file_content)
            required = ["tnsnames.ora", "sqlnet.ora"]
            missing  = [f for f in required if not os.path.exists(os.path.join(tmp_dir, f))]
            if missing:
                return False, f"필수 파일이 없습니다: {', '.join(missing)}"
            _wallet_pw = wallet_pw if wallet_pw and wallet_pw.strip() else None
            def _creator():
                return oracledb.connect(
                    user=user, password=pw, dsn=tns_alias,
                    config_dir=tmp_dir, wallet_location=tmp_dir,
                    wallet_password=_wallet_pw,
                    tcp_connect_timeout=15, retry_count=1, retry_delay=1,
                )
            self.engine = create_engine("oracle+oracledb://", creator=_creator)
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1 FROM DUAL"))
            self.db_type = 'RDB'
            return True, f"Oracle Wallet 연결 성공! (alias: {tns_alias})"
        except Exception as e:
            self._cleanup_wallet()
            return False, f"Oracle Wallet 연결 실패: {str(e)}"

    def load_file_to_sqlite(self, uploaded_file):
        try:
            if uploaded_file.name.endswith('.csv'):
                try:
                    df = pd.read_csv(uploaded_file, encoding='utf-8')
                except UnicodeDecodeError:
                    uploaded_file.seek(0)
                    df = pd.read_csv(uploaded_file, encoding='cp949')
            elif uploaded_file.name.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(uploaded_file)
            else:
                return False, "지원하지 않는 파일 형식입니다."
            self.engine = create_engine('sqlite:///temp.db')
            df.to_sql("uploaded_data", con=self.engine, if_exists='replace', index=False)
            self.db_type = 'FILE'
            return True, f"파일 로드 성공. ({len(df):,}행 / 임시 테이블: uploaded_data)"
        except Exception as e:
            return False, f"파일 처리 실패: {str(e)}"

    def get_table_names(self):
        if not self.engine: return []
        return inspect(self.engine).get_table_names()

    def get_columns(self, table_name):
        if not self.engine: return []
        return [col['name'] for col in inspect(self.engine).get_columns(table_name)]

    def get_column_types(self, table_name) -> dict:
        """
        컬럼명 → 타입 카테고리 반환
        반환: 'DATE' | 'NUMBER' | 'TEXT' | 'UNKNOWN'
        """
        if not self.engine:
            return {}
        dialect = self.engine.dialect.name.lower()
        result  = {}
        try:
            cols = inspect(self.engine).get_columns(table_name)
            for col in cols:
                name     = col['name']
                type_str = str(col['type']).upper()
                if any(t in type_str for t in ['DATE', 'TIME', 'TIMESTAMP']):
                    result[name] = 'DATE'
                elif any(t in type_str for t in ['INT', 'INTEGER', 'BIGINT', 'SMALLINT',
                                                   'NUMBER', 'NUMERIC', 'FLOAT',
                                                   'DOUBLE', 'DECIMAL', 'REAL']):
                    result[name] = 'NUMBER'
                elif any(t in type_str for t in ['VARCHAR', 'CHAR', 'TEXT',
                                                   'CLOB', 'NCHAR', 'STRING']):
                    result[name] = 'TEXT'
                else:
                    result[name] = 'UNKNOWN'
        except Exception:
            for col in self.get_columns(table_name):
                result[col] = 'UNKNOWN'
        return result