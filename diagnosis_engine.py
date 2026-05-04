import pandas as pd

class DiagnosisEngine:
    def run_queries(self, engine, queries, progress_callback=None):
        results      = []
        error_store  = {}   # { index: detail_df } — DataFrame을 raw_results 밖에 보관
        total        = len(queries)

        for i, q in enumerate(queries):
            try:
                df = pd.read_sql(q['query'], con=engine)

                if df.empty:
                    results.append(self._make_result(q, 0, 0, 0.0))
                    error_store[i] = None
                    continue

                row_data  = df.iloc[0].to_dict()
                error_cnt = int(row_data.get('error_cnt', 0) or 0)
                total_cnt = int(row_data.get('total_cnt', 0) or 0)
                error_rate = round((error_cnt / total_cnt) * 100, 2) if total_cnt > 0 else 0.0
                error_rate = float(f"{error_rate:.2f}")

                # 오류 있고 detail_query 있으면 원본 데이터 조회 (최대 1000건)
                detail_df = None
                if error_cnt > 0 and q.get('detail_query'):
                    try:
                        dq = q['detail_query'].strip().rstrip(';')
                        # DB 방언에 따라 행 수 제한 쿼리 자동 적용
                        dialect = engine.dialect.name.lower()
                        if 'oracle' in dialect:
                            dq = f"SELECT * FROM ({dq}) WHERE ROWNUM <= 1000"
                        elif dialect in ('sqlite', 'postgresql', 'mysql'):
                            dq = f"{dq} LIMIT 1000"
                        detail_df = pd.read_sql(dq, con=engine)
                    except Exception:
                        detail_df = None

                results.append(self._make_result(q, total_cnt, error_cnt, error_rate))
                error_store[i] = detail_df

            except Exception as e:
                results.append({
                    "rule_id":   q.get('rule_id', ''),
                    "rule_name": q.get('rule_name', ''),
                    "table":     q.get('table', ''),
                    "column":    q.get('column', ''),
                    "total_cnt": -1,
                    "error_cnt": -1,
                    "error_rate": -1.0,
                    "error_msg": str(e),
                })
                error_store[i] = None

            if progress_callback:
                progress_callback(i + 1, total, q.get('rule_name',''), q.get('column',''))

        return results, error_store

    def _make_result(self, q, total_cnt, error_cnt, error_rate):
        return {
            "rule_id":   q.get('rule_id', ''),
            "rule_name": q.get('rule_name', ''),
            "table":     q.get('table', ''),
            "column":    q.get('column', ''),
            "total_cnt": total_cnt,
            "error_cnt": error_cnt,
            "error_rate": error_rate,
        }