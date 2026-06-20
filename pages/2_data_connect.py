import streamlit as st
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
from core.connector import DataConnector

st.title("🔌 데이터 연결")
st.markdown("품질진단을 수행할 대상 DB에 접속하거나, 분석할 데이터 파일을 업로드하세요.")

if 'connector' not in st.session_state:
    st.session_state.connector = DataConnector()
if 'connected' not in st.session_state:
    st.session_state.connected = False

# ── 탭 구성 ───────────────────────────────────
tab_pg, tab_mysql, tab_ora_host, tab_ora_tns, tab_ora_wallet, tab_file = st.tabs([
    "🐘 PostgreSQL",
    "🐬 MySQL",
    "🔶 Oracle (host)",
    "🔶 Oracle (TNS)",
    "🔐 Oracle (Wallet)",
    "📁 파일 업로드",
])

# ── PostgreSQL ────────────────────────────────
with tab_pg:
    st.subheader("PostgreSQL 접속 정보")
    col1, col2 = st.columns(2)
    with col1:
        pg_host = st.text_input("Host", value="localhost", key="pg_host")
        pg_port = st.text_input("Port", value="5432",     key="pg_port")
    with col2:
        pg_db   = st.text_input("Database", key="pg_db")
        pg_user = st.text_input("User ID",  key="pg_user")
        pg_pw   = st.text_input("Password", type="password", key="pg_pw")

    if st.button("PostgreSQL 연결", type="primary"):
        if not all([pg_host, pg_port, pg_db, pg_user, pg_pw]):
            st.warning("모든 항목을 입력해주세요.")
        else:
            with st.spinner("연결 중..."):
                ok, msg = st.session_state.connector.connect_db(
                    'postgresql', pg_host, pg_port, pg_user, pg_pw, pg_db)
            st.session_state.connected = ok
            (st.success if ok else st.error)(msg)

# ── MySQL ─────────────────────────────────────
with tab_mysql:
    st.subheader("MySQL 접속 정보")
    col1, col2 = st.columns(2)
    with col1:
        my_host = st.text_input("Host", value="localhost", key="my_host")
        my_port = st.text_input("Port", value="3306",     key="my_port")
    with col2:
        my_db   = st.text_input("Database", key="my_db")
        my_user = st.text_input("User ID",  key="my_user")
        my_pw   = st.text_input("Password", type="password", key="my_pw")

    if st.button("MySQL 연결", type="primary"):
        if not all([my_host, my_port, my_db, my_user, my_pw]):
            st.warning("모든 항목을 입력해주세요.")
        else:
            with st.spinner("연결 중..."):
                ok, msg = st.session_state.connector.connect_db(
                    'mysql', my_host, my_port, my_user, my_pw, my_db)
            st.session_state.connected = ok
            (st.success if ok else st.error)(msg)

# ── Oracle (host 방식) ────────────────────────
with tab_ora_host:
    st.subheader("Oracle 접속 — host / port / service_name")
    st.caption("일반적인 방식. SID로 접속하는 경우도 service_name 란에 SID를 입력하세요.")
    col1, col2 = st.columns(2)
    with col1:
        ora_host = st.text_input("Host",   value="localhost", key="ora_host")
        ora_port = st.text_input("Port",   value="1521",      key="ora_port")
        ora_svc  = st.text_input("Service Name (또는 SID)",   key="ora_svc")
    with col2:
        ora_user = st.text_input("User ID",  key="ora_user")
        ora_pw   = st.text_input("Password", type="password", key="ora_pw")

    if st.button("Oracle 연결 (host)", type="primary"):
        if not all([ora_host, ora_port, ora_svc, ora_user, ora_pw]):
            st.warning("모든 항목을 입력해주세요.")
        else:
            with st.spinner("Oracle에 연결 중..."):
                ok, msg = st.session_state.connector.connect_oracle_host(
                    ora_host, ora_port, ora_svc, ora_user, ora_pw)
            st.session_state.connected = ok
            (st.success if ok else st.error)(msg)

# ── Oracle (TNS 방식) ─────────────────────────
with tab_ora_tns:
    st.subheader("Oracle 접속 — TNS 방식")
    st.caption("아래 세 가지 형식 중 하나를 입력하세요.")
    st.code(
        "① TNS명:           ORCL\n"
        "② Easy Connect:    192.168.1.10:1521/ORCL\n"
        "③ Full descriptor: (DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=...)(PORT=1521))(CONNECT_DATA=(SERVICE_NAME=...)))",
        language="text"
    )
    tns_str  = st.text_area("TNS 문자열", height=100, key="tns_str",
                             placeholder="위 세 가지 형식 중 하나를 붙여넣으세요")
    tns_user = st.text_input("User ID",  key="tns_user")
    tns_pw   = st.text_input("Password", type="password", key="tns_pw")

    if st.button("Oracle 연결 (TNS)", type="primary"):
        if not all([tns_str.strip(), tns_user, tns_pw]):
            st.warning("모든 항목을 입력해주세요.")
        else:
            with st.spinner("Oracle TNS로 연결 중..."):
                ok, msg = st.session_state.connector.connect_oracle_tns(
                    tns_str.strip(), tns_user, tns_pw)
            st.session_state.connected = ok
            (st.success if ok else st.error)(msg)

# ── Oracle (Wallet 파일 업로드) ───────────────
with tab_ora_wallet:
    st.subheader("🔐 Oracle 접속 — Wallet 방식")

    st.info(
        "윈도우 PC의 Wallet 폴더(`C:\\dbeaver\\Wallet_dqmdb`) 안에 있는 파일들을 "
        "아래에 **드래그 앤 드롭**으로 올려주세요."
    )

    # 필요한 파일 안내
    col_guide1, col_guide2, col_guide3 = st.columns(3)
    col_guide1.markdown("✅ **cwallet.sso**\n\n자동로그인 키")
    col_guide2.markdown("✅ **tnsnames.ora**\n\n접속명 정의")
    col_guide3.markdown("✅ **sqlnet.ora**\n\n네트워크 설정")

    st.divider()

    # 파일 업로드 (여러 파일 한 번에)
    uploaded_wallet_files = st.file_uploader(
        "Wallet 폴더 안의 파일들을 모두 선택해서 올려주세요",
        accept_multiple_files=True,
        key="wallet_files",
        help="cwallet.sso, tnsnames.ora, sqlnet.ora 는 필수입니다. ewallet.p12 등 나머지도 함께 올리세요."
    )

    # 업로드된 파일 현황 표시
    if uploaded_wallet_files:
        uploaded_names = [f.name for f in uploaded_wallet_files]
        required = ["cwallet.sso", "tnsnames.ora", "sqlnet.ora"]
        missing  = [r for r in required if r not in uploaded_names]

        st.markdown(f"**업로드된 파일 ({len(uploaded_wallet_files)}개):** "
                    + ", ".join([f"`{n}`" for n in uploaded_names]))

        if missing:
            st.warning(f"⚠️ 필수 파일이 없습니다: {', '.join(missing)}")
        else:
            st.success("✅ 필수 파일 확인 완료! 아래 접속 정보를 입력하고 연결하세요.")

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        tns_alias    = st.text_input(
            "접속명 (Network Alias)",
            placeholder="dqmdb_high",
            key="tns_alias",
            help="DBeaver TNS 탭의 'Network Alias' 값을 입력하세요."
        )
        wallet_file_pw = st.text_input(
            "Wallet 비밀번호 (PEM 암호)",
            type="password",
            key="wallet_file_pw",
            help="ewallet.pem 파일의 암호화 비밀번호입니다. DBeaver에서 Wallet 생성 시 설정한 비밀번호."
        )
    with col2:
        wallet_user = st.text_input("DB User ID",  key="wallet_user", placeholder="casemp")
        wallet_pw   = st.text_input("DB Password", type="password",   key="wallet_pw")

    if st.button("🔐 Oracle Wallet 연결", type="primary"):
        if not uploaded_wallet_files:
            st.error("Wallet 파일을 먼저 업로드해주세요.")
        elif not all([tns_alias, wallet_user, wallet_pw]):
            st.warning("접속명, User ID, Password를 모두 입력해주세요.")
        else:
            # 업로드된 파일들을 딕셔너리로 변환 { 파일명: bytes }
            wallet_file_dict = {f.name: f.read() for f in uploaded_wallet_files}

            with st.spinner("Oracle Wallet으로 연결 중..."):
                ok, msg = st.session_state.connector.connect_oracle_wallet_files(
                    wallet_file_dict, tns_alias, wallet_user, wallet_pw,
                    wallet_pw=wallet_file_pw   # ewallet.pem 암호
                )
            st.session_state.connected = ok
            (st.success if ok else st.error)(msg)

# ── 파일 업로드 ───────────────────────────────
with tab_file:
    st.subheader("데이터 파일 업로드")
    st.info("CSV 또는 Excel 파일을 업로드하면 자동으로 SQLite DB에 적재되어 SQL 쿼리가 가능해집니다.")
    uploaded_file = st.file_uploader("파일 선택", type=['csv', 'xls', 'xlsx'])

    if st.button("파일 로드 및 적재", type="primary"):
        if uploaded_file is None:
            st.warning("먼저 파일을 업로드해주세요.")
        else:
            with st.spinner("파일을 읽고 임시 DB를 구성하는 중..."):
                ok, msg = st.session_state.connector.load_file_to_sqlite(uploaded_file)
            st.session_state.connected = ok
            (st.success if ok else st.error)(msg)

# ── 연결 성공 시 데이터 확인 ───────────────────
st.divider()
if st.session_state.connected:
    st.subheader("✅ 연결된 데이터 정보")
    tables = st.session_state.connector.get_table_names()

    if tables:
        st.write(f"**총 {len(tables)}개의 테이블을 발견했습니다.**")
        selected_table = st.selectbox("테이블 목록 확인", tables)
        if selected_table:
            columns = st.session_state.connector.get_columns(selected_table)
            st.write(f"**'{selected_table}'** 테이블의 컬럼 ({len(columns)}개):")
            st.write(", ".join([f"`{col}`" for col in columns]))
    else:
        st.info("연결은 성공했지만 테이블을 찾을 수 없습니다.")
