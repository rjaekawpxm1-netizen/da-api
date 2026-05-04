import yaml
import os

class QueryBuilder:
    def load_templates(self, template_type):
        base_dir = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(base_dir, 'templates', f'{template_type}.yaml')
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            if not data or 'rules' not in data:
                return []
            return data['rules']

    def load_all_templates(self) -> dict:
        """전체 템플릿을 dimension별로 반환: { 'completeness': [rules...], ... }"""
        dimension_map = {
            'completeness': '완전성',
            'consistency':  '일관성',
            'accuracy':     '정확성',
            'usefulness':   '유용성',
            'uniqueness':   '유일성',
            'validity':     '유효성',
        }
        result = {}
        for key in dimension_map:
            try:
                result[key] = self.load_templates(key)
            except FileNotFoundError:
                result[key] = []
        return result

    def _quoter(self, db_type: str):
        """DB 종류에 따른 식별자 인용 함수 반환"""
        if db_type == 'oracle':
            return lambda name: name          # Oracle: 따옴표 없음
        return lambda name: f'"{name}"'       # SQLite/PG/MySQL: 쌍따옴표

    def build_queries_per_column(self, table: str, column_rule_map: dict,
                                  all_rules: list, db_type: str = 'sqlite') -> list:
        """
        column_rule_map: { 'col_name': ['COMP_001', 'CONS_001', ...], ... }
        컬럼마다 적용할 rule_id 목록이 다른 경우를 처리
        """
        q       = self._quoter(db_type)
        queries = []

        # rule_id → rule 딕셔너리
        rule_dict = {r['id']: r for r in all_rules}

        # table-level 규칙은 별도 처리 (모든 컬럼 조합 검사)
        all_selected_rule_ids = set()
        for ids in column_rule_map.values():
            all_selected_rule_ids.update(ids)

        # 1. column-level 규칙: 컬럼별로 선택된 rule만 실행
        for col, selected_ids in column_rule_map.items():
            for rule_id in selected_ids:
                rule = rule_dict.get(rule_id)
                if not rule or rule.get('level', 'column') != 'column':
                    continue

                qcol   = q(col)
                qtable = q(table)
                query  = (rule['query_template']
                          .replace("'{col}'", f"'{col}'")
                          .replace("{col}",   qcol)
                          .replace("{table}", qtable))

                detail_query = rule.get('detail_query', '')
                if detail_query:
                    detail_query = (detail_query
                                    .replace("{col}",   qcol)
                                    .replace("{table}", qtable))

                queries.append({
                    "rule_id":     rule['id'],
                    "rule_name":   rule['name'],
                    "table":       table,
                    "column":      col,
                    "query":       query,
                    "detail_query": detail_query,
                })

        # 2. table-level 규칙: 선택된 컬럼 전체를 대상으로 1번만 실행
        columns = list(column_rule_map.keys())
        if columns:
            col_list      = ", ".join([q(c) for c in columns])
            col_names_str = " + ".join(columns)
            if db_type == 'oracle':
                concat_cols = " || '_' || ".join(
                    [f"NVL(TO_CHAR({q(c)}), '')" for c in columns])
            else:
                concat_cols = " || '_' || ".join(
                    [f"COALESCE(CAST({q(c)} AS TEXT), '')" for c in columns])

            for rule_id in all_selected_rule_ids:
                rule = rule_dict.get(rule_id)
                if not rule or rule.get('level') != 'table':
                    continue

                qtable = q(table)
                query  = (rule['query_template']
                          .replace("{col_names}",  f"'{col_names_str}'")
                          .replace("{col_list}",   col_list)
                          .replace("{concat_cols}", concat_cols)
                          .replace("{table}",      qtable))

                detail_query = rule.get('detail_query', '')
                if detail_query:
                    detail_query = (detail_query
                                    .replace("{col_names}",  f"'{col_names_str}'")
                                    .replace("{col_list}",   col_list)
                                    .replace("{concat_cols}", concat_cols)
                                    .replace("{table}",      qtable))

                queries.append({
                    "rule_id":     rule['id'],
                    "rule_name":   rule['name'],
                    "table":       table,
                    "column":      f"복합키({col_names_str})",
                    "query":       query,
                    "detail_query": detail_query,
                })

        return queries

    def build_queries(self, table, columns, rules, db_type='sqlite'):
        """하위 호환용 — 기존 방식 (모든 컬럼에 모든 규칙 적용)"""
        column_rule_map = {col: [r['id'] for r in rules] for col in columns}
        return self.build_queries_per_column(table, column_rule_map, rules, db_type)