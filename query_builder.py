import yaml
import os


class QueryBuilder:
    """
    진단 쿼리 생성기.
    YAML 템플릿의 플레이스홀더를 DB 방언에 맞게 치환하여 호환 쿼리 생성.

    플레이스홀더:
      {table}       테이블명
      {col}         컬럼명 (인용 적용)
      '{col}'       column_name 출력용 리터럴 (원본 컬럼명, 인용 X)
      {CAST_TEXT}   컬럼을 문자열로 캐스팅
      {NOT_NUMERIC} 숫자/소수점 외 문자 포함 검사 조건식
      {FROM_DUMMY}  더미 FROM 절 (Oracle: FROM DUAL)
      {SUBQ_ALIAS}  서브쿼리 별칭 (MySQL 필수)
      {col_names}   복합키 표시명
      {col_list}    복합키 컬럼 목록
    """

    DIALECT = {
        'oracle': {
            'cast_text':   lambda col: f"TO_CHAR({col})",
            'from_dummy':  "FROM DUAL",
            'subq_alias':  "",
            'not_numeric': lambda col: f"REGEXP_LIKE(TO_CHAR({col}), '[^0-9.]')",
            'quote':       lambda name: name,
        },
        'sqlite': {
            'cast_text':   lambda col: f"CAST({col} AS TEXT)",
            'from_dummy':  "",
            'subq_alias':  "AS sub",
            'not_numeric': lambda col: f"CAST({col} AS TEXT) GLOB '*[^0-9.]*'",
            'quote':       lambda name: f'"{name}"',
        },
        'postgresql': {
            'cast_text':   lambda col: f"CAST({col} AS VARCHAR)",
            'from_dummy':  "",
            'subq_alias':  "AS sub",
            'not_numeric': lambda col: f"CAST({col} AS VARCHAR) ~ '[^0-9.]'",
            'quote':       lambda name: f'"{name}"',
        },
        'mysql': {
            'cast_text':   lambda col: f"CAST({col} AS CHAR)",
            'from_dummy':  "",
            'subq_alias':  "AS sub",
            'not_numeric': lambda col: f"CAST({col} AS CHAR) REGEXP '[^0-9.]'",
            'quote':       lambda name: f'`{name}`',
        },
    }

    def load_templates(self, template_type):
        base_dir = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(base_dir, 'templates', f'{template_type}.yaml')
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            if not data or 'rules' not in data:
                return []
            return data['rules']

    def load_all_templates(self) -> dict:
        dimension_map = ['completeness', 'consistency', 'accuracy',
                         'usefulness', 'uniqueness', 'validity']
        result = {}
        for key in dimension_map:
            try:
                result[key] = self.load_templates(key)
            except FileNotFoundError:
                result[key] = []
        return result

    def _dialect(self, db_type: str) -> dict:
        return self.DIALECT.get(db_type, self.DIALECT['sqlite'])

    def _render_column(self, template: str, d: dict, table: str, col: str) -> str:
        """column-level 쿼리 렌더링"""
        col_q   = d['quote'](col)
        table_q = d['quote'](table)
        sql = template

        # 1. column_name 리터럴 '{col}' → 원본 컬럼명 (인용 X)
        sql = sql.replace("'{col}'", f"@@COLNAME@@")

        # 2. {NOT_NUMERIC} (CAST 포함 조건식 전체 치환)
        if "{NOT_NUMERIC}" in sql:
            # YAML 패턴: "{CAST_TEXT} {NOT_NUMERIC}" → 조건식 전체로
            cast_expr = d['cast_text'](col_q)
            sql = sql.replace(f"{{CAST_TEXT}} {{NOT_NUMERIC}}", d['not_numeric'](col_q))
            sql = sql.replace("{NOT_NUMERIC}", "")

        # 3. {CAST_TEXT} → 방언 캐스팅
        sql = sql.replace("{CAST_TEXT}", d['cast_text'](col_q))

        # 4. {col} → 인용 컬럼명
        sql = sql.replace("{col}", col_q)

        # 5. {table}
        sql = sql.replace("{table}", table_q)

        # 6. 공통 방언
        sql = sql.replace("{FROM_DUMMY}", d['from_dummy'])
        sql = sql.replace("{SUBQ_ALIAS}", d['subq_alias'])

        # 7. column_name 리터럴 복원 (원본 컬럼명)
        sql = sql.replace("@@COLNAME@@", f"'{col}'")

        return sql.strip()

    def _render_table(self, template: str, d: dict, table: str,
                      col_names: str, col_list: str) -> str:
        """table-level 쿼리 렌더링"""
        table_q = d['quote'](table)
        sql = template
        sql = sql.replace("{col_names}", f"'{col_names}'")
        sql = sql.replace("{col_list}", col_list)
        sql = sql.replace("{table}", table_q)
        sql = sql.replace("{FROM_DUMMY}", d['from_dummy'])
        sql = sql.replace("{SUBQ_ALIAS}", d['subq_alias'])
        return sql.strip()

    def build_queries_per_column(self, table: str, column_rule_map: dict,
                                  all_rules: list, db_type: str = 'sqlite',
                                  column_types: dict = None) -> list:
        d         = self._dialect(db_type)
        quote     = d['quote']
        rule_dict = {r['id']: r for r in all_rules}
        queries   = []

        all_selected_ids = set()
        for ids in column_rule_map.values():
            all_selected_ids.update(ids)

        # ── 1. column-level ──
        for col, selected_ids in column_rule_map.items():
            col_type = (column_types or {}).get(col, 'UNKNOWN')

            for rule_id in selected_ids:
                rule = rule_dict.get(rule_id)
                if not rule or rule.get('level', 'column') != 'column':
                    continue

                # applies_to 타입 필터 (오탐 방지)
                applies = rule.get('applies_to')
                if applies and col_type != 'UNKNOWN' and col_type != applies:
                    continue

                query  = self._render_column(rule['query_template'], d, table, col)
                detail = rule.get('detail_query', '')
                if detail:
                    detail = self._render_column(detail, d, table, col)

                queries.append({
                    "rule_id": rule['id'], "rule_name": rule['name'],
                    "table": table, "column": col,
                    "query": query, "detail_query": detail,
                })

        # ── 2. table-level ──
        columns = list(column_rule_map.keys())
        if columns:
            col_list_q    = ", ".join([quote(c) for c in columns])
            col_names_str = " + ".join(columns)

            for rule_id in all_selected_ids:
                rule = rule_dict.get(rule_id)
                if not rule or rule.get('level') != 'table':
                    continue

                query  = self._render_table(rule['query_template'], d, table,
                                            col_names_str, col_list_q)
                detail = rule.get('detail_query', '')
                if detail:
                    detail = self._render_table(detail, d, table,
                                                col_names_str, col_list_q)

                queries.append({
                    "rule_id": rule['id'], "rule_name": rule['name'],
                    "table": table, "column": f"복합키({col_names_str})",
                    "query": query, "detail_query": detail,
                })

        return queries

    def build_queries(self, table, columns, rules, db_type='sqlite', column_types=None):
        """하위 호환: 모든 컬럼에 모든 규칙 적용"""
        column_rule_map = {col: [r['id'] for r in rules] for col in columns}
        return self.build_queries_per_column(table, column_rule_map, rules,
                                              db_type, column_types)