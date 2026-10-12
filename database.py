import os
import psycopg
import zstandard as zstd
from config import (
    SUPABASE_APP_DB_HOST,
    SUPABASE_APP_DB_PORT,
    SUPABASE_APP_DB_USER,
    SUPABASE_APP_DB_PASSWORD,
    SUPABASE_APP_DB_NAME,
)

cctx = zstd.ZstdCompressor(level=3)
dctx = zstd.ZstdDecompressor()

def compress_bytes(raw_bytes):
    if not raw_bytes:
        return None
    if isinstance(raw_bytes, str):
        raw_bytes = raw_bytes.encode('utf-8')
    return cctx.compress(raw_bytes)

def decompress_bytes(compressed_bytes):
    if not compressed_bytes:
        return ""
    try:
        if isinstance(compressed_bytes, memoryview):
            compressed_bytes = compressed_bytes.tobytes()
        return dctx.decompress(compressed_bytes).decode('utf-8', errors='ignore')
    except Exception:
        return ""


class PgRow(dict):
    """Row tương thích sqlite3.Row: hỗ trợ dict key, numeric index và dict(row)."""
    def __init__(self, cols, values):
        super().__init__(zip(cols, values))
        self._values = tuple(values)

    def __getitem__(self, item):
        if isinstance(item, int):
            return self._values[item]
        return super().__getitem__(item)

    def __iter__(self):
        return iter(self._values)


class PgCursorWrapper:
    def __init__(self, cursor):
        self._cur = cursor

    @property
    def description(self):
        return self._cur.description

    @property
    def rowcount(self):
        return self._cur.rowcount

    def _convert_query(self, query):
        if not isinstance(query, str):
            return query
        import re
        # Chuyển đổi cú pháp định danh SQLite [cột] sang PostgreSQL "cột"
        query = re.sub(r'\[([^\]]+)\]', r'"\1"', query)
        # Thoát các ký tự % literal thành %% để psycopg không nhầm lẫn với placeholder
        query = re.sub(r'%(?!%)', '%%', query)
        # Chuyển đổi placeholder '?' của SQLite sang '%s' của PostgreSQL
        return query.replace('?', '%s')

    def execute(self, query, params=None):
        query = self._convert_query(query)
        if params is not None:
            if isinstance(params, (list, tuple)):
                # Xử lý các đối tượng binary/memoryview nếu có
                clean_params = [p.tobytes() if isinstance(p, memoryview) else p for p in params]
                self._cur.execute(query, clean_params)
            else:
                self._cur.execute(query, params)
        else:
            self._cur.execute(query)
        return self

    def executemany(self, query, param_seq):
        query = self._convert_query(query)
        self._cur.executemany(query, param_seq)
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in self._cur.description]
        return PgRow(cols, row)

    def fetchall(self):
        rows = self._cur.fetchall()
        if not rows:
            return []
        cols = [d[0] for d in self._cur.description]
        return [PgRow(cols, r) for r in rows]

    def fetchmany(self, size=None):
        rows = self._cur.fetchmany(size)
        if not rows:
            return []
        cols = [d[0] for d in self._cur.description]
        return [PgRow(cols, r) for r in rows]

    def close(self):
        self._cur.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._cur.close()


class PgConnectionWrapper:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return PgCursorWrapper(self._conn.cursor())

    def execute(self, query, params=None):
        cur = self.cursor()
        cur.execute(query, params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._conn.rollback()
        else:
            self._conn.commit()
        self._conn.close()


def get_connection():
    raw_conn = psycopg.connect(
        host=SUPABASE_APP_DB_HOST,
        port=SUPABASE_APP_DB_PORT,
        user=SUPABASE_APP_DB_USER,
        password=SUPABASE_APP_DB_PASSWORD,
        dbname=SUPABASE_APP_DB_NAME,
        connect_timeout=15
    )
    return PgConnectionWrapper(raw_conn)


def init_db():
    conn = get_connection()
    with conn.cursor() as cur:
        # Hàm tương thích hàm date(ts, 'unixepoch', 'localtime') của SQLite
        cur.execute("""
        CREATE OR REPLACE FUNCTION date(ts DOUBLE PRECISION, mode1 TEXT, mode2 TEXT)
        RETURNS TEXT AS $$
        BEGIN
            IF ts IS NULL OR ts = 0 THEN
                RETURN '';
            END IF;
            RETURN to_char(to_timestamp(ts) AT TIME ZONE 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD');
        EXCEPTION WHEN OTHERS THEN
            RETURN '';
        END;
        $$ LANGUAGE plpgsql IMMUTABLE;

        CREATE OR REPLACE FUNCTION substr(ts TIMESTAMP WITHOUT TIME ZONE, s INT, l INT)
        RETURNS TEXT AS $$
        BEGIN
            RETURN substr(ts::text, s, l);
        END;
        $$ LANGUAGE plpgsql IMMUTABLE;

        CREATE OR REPLACE FUNCTION substr(ts TIMESTAMP WITH TIME ZONE, s INT, l INT)
        RETURNS TEXT AS $$
        BEGIN
            RETURN substr(ts::text, s, l);
        END;
        $$ LANGUAGE plpgsql IMMUTABLE;
        """)

        # Bảng cem_emails
        cur.execute("""
        CREATE TABLE IF NOT EXISTS cem_emails (
            id BIGSERIAL PRIMARY KEY,
            msg_uid TEXT UNIQUE,
            folder TEXT,
            subject TEXT,
            email_date TEXT,
            timestamp_val DOUBLE PRECISION DEFAULT 0,
            from_sender TEXT,
            contract TEXT,
            customer_name TEXT,
            phone TEXT,
            address TEXT,
            district TEXT,
            eval_type TEXT,
            channel TEXT,
            eval_time TEXT,
            completed_time TEXT,
            technician TEXT,
            csat_score INTEGER,
            issue_group TEXT,
            notes TEXT,
            home_support TEXT,
            raw_html TEXT,
            raw_zstd BYTEA,
            is_reply INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_cem_emails_technician ON cem_emails(technician);
        CREATE INDEX IF NOT EXISTS idx_cem_emails_csat_score ON cem_emails(csat_score);
        CREATE INDEX IF NOT EXISTS idx_cem_emails_eval_time ON cem_emails(eval_time);
        CREATE INDEX IF NOT EXISTS idx_cem_emails_contract ON cem_emails(contract);
        """)

        # Bảng giuc_tien_do_emails
        cur.execute("""
        CREATE TABLE IF NOT EXISTS giuc_tien_do_emails (
            id BIGSERIAL PRIMARY KEY,
            msg_uid TEXT UNIQUE,
            folder TEXT,
            subject TEXT,
            email_date TEXT,
            timestamp_val DOUBLE PRECISION DEFAULT 0,
            from_sender TEXT,
            assignee TEXT,
            contract TEXT,
            sr_ticket TEXT,
            priority TEXT,
            request_content TEXT,
            request_time TEXT,
            raw_html TEXT,
            raw_zstd BYTEA,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_giuc_assignee ON giuc_tien_do_emails(assignee);
        CREATE INDEX IF NOT EXISTS idx_giuc_contract ON giuc_tien_do_emails(contract);
        CREATE INDEX IF NOT EXISTS idx_giuc_timestamp ON giuc_tien_do_emails(timestamp_val);
        """)

        # Bảng cll_emails
        cur.execute("""
        CREATE TABLE IF NOT EXISTS cll_emails (
            id BIGSERIAL PRIMARY KEY,
            msg_uid TEXT UNIQUE,
            folder TEXT,
            subject TEXT,
            email_date TEXT,
            timestamp_val DOUBLE PRECISION DEFAULT 0,
            from_sender TEXT,
            contract TEXT,
            occurrence_count INTEGER DEFAULT 0,
            initial_status TEXT,
            raw_html TEXT,
            raw_zstd BYTEA,
            staff TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_cll_contract ON cll_emails(contract);
        CREATE INDEX IF NOT EXISTS idx_cll_staff ON cll_emails(staff);
        CREATE INDEX IF NOT EXISTS idx_cll_timestamp ON cll_emails(timestamp_val);
        """)

        # Bảng sync_logs
        cur.execute("""
        CREATE TABLE IF NOT EXISTS sync_logs (
            id BIGSERIAL PRIMARY KEY,
            sync_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT,
            emails_scanned INTEGER DEFAULT 0,
            emails_added INTEGER DEFAULT 0,
            message TEXT
        );
        """)

        # Bảng app_settings
        cur.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)

        # Bảng login_users
        cur.execute("""
        CREATE TABLE IF NOT EXISTS login_users (
            id BIGSERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TEXT,
            last_login TEXT,
            role TEXT DEFAULT 'USER'
        );
        """)
    conn.commit()
    conn.close()


def save_email_record(record):
    conn = get_connection()
    try:
        raw_to_compress = record.get("raw_bytes") or record.get("raw_html") or ""
        compressed_blob = compress_bytes(raw_to_compress)

        conn.execute("""
        INSERT INTO cem_emails (
            msg_uid, folder, subject, email_date, timestamp_val, from_sender,
            contract, customer_name, phone, address, district,
            eval_type, channel, eval_time, completed_time,
            technician, csat_score, issue_group, notes,
            home_support, raw_html, raw_zstd, is_reply
        ) VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?
        )
        ON CONFLICT(msg_uid) DO UPDATE SET
            folder=excluded.folder,
            subject=excluded.subject,
            email_date=excluded.email_date,
            timestamp_val=excluded.timestamp_val,
            from_sender=excluded.from_sender,
            contract=CASE WHEN excluded.contract != '' THEN excluded.contract ELSE cem_emails.contract END,
            customer_name=CASE WHEN excluded.customer_name != '' THEN excluded.customer_name ELSE cem_emails.customer_name END,
            phone=CASE WHEN excluded.phone != '' THEN excluded.phone ELSE cem_emails.phone END,
            address=CASE WHEN excluded.address != '' THEN excluded.address ELSE cem_emails.address END,
            district=CASE WHEN excluded.district != '' THEN excluded.district ELSE cem_emails.district END,
            eval_type=CASE WHEN excluded.eval_type != '' THEN excluded.eval_type ELSE cem_emails.eval_type END,
            channel=CASE WHEN excluded.channel != '' THEN excluded.channel ELSE cem_emails.channel END,
            eval_time=CASE WHEN excluded.eval_time != '' THEN excluded.eval_time ELSE cem_emails.eval_time END,
            completed_time=CASE WHEN excluded.completed_time != '' THEN excluded.completed_time ELSE cem_emails.completed_time END,
            technician=CASE WHEN excluded.technician != '' THEN excluded.technician ELSE cem_emails.technician END,
            csat_score=CASE WHEN excluded.csat_score IS NOT NULL THEN excluded.csat_score ELSE cem_emails.csat_score END,
            issue_group=CASE WHEN excluded.issue_group != '' THEN excluded.issue_group ELSE cem_emails.issue_group END,
            notes=CASE WHEN excluded.notes != '' THEN excluded.notes ELSE cem_emails.notes END,
            home_support=CASE WHEN excluded.home_support != '' THEN excluded.home_support ELSE cem_emails.home_support END,
            raw_html=CASE WHEN excluded.raw_html != '' THEN excluded.raw_html ELSE cem_emails.raw_html END,
            raw_zstd=CASE WHEN excluded.raw_zstd IS NOT NULL THEN excluded.raw_zstd ELSE cem_emails.raw_zstd END,
            is_reply=excluded.is_reply
        """, (
            record.get("msg_uid"),
            record.get("folder"),
            record.get("subject"),
            record.get("email_date"),
            record.get("timestamp_val", 0),
            record.get("from_sender"),
            record.get("contract", ""),
            record.get("customer_name", ""),
            record.get("phone", ""),
            record.get("address", ""),
            record.get("district", ""),
            record.get("eval_type", ""),
            record.get("channel", ""),
            record.get("eval_time", ""),
            record.get("completed_time", ""),
            record.get("technician", ""),
            record.get("csat_score"),
            record.get("issue_group", ""),
            record.get("notes", ""),
            record.get("home_support", ""),
            record.get("raw_html", ""),
            compressed_blob,
            record.get("is_reply", 0)
        ))
        conn.commit()
        return True
    except Exception as e:
        print(f"Database error on save_email_record: {e}")
        return False
    finally:
        conn.close()


def save_giuc_tien_do_record(record):
    conn = get_connection()
    try:
        raw_to_compress = record.get("raw_bytes") or record.get("raw_html") or ""
        compressed_blob = compress_bytes(raw_to_compress)

        conn.execute("""
        INSERT INTO giuc_tien_do_emails (
            msg_uid, folder, subject, email_date, timestamp_val, from_sender,
            assignee, contract, sr_ticket, priority, request_content, request_time,
            raw_html, raw_zstd
        ) VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?
        )
        ON CONFLICT(msg_uid) DO UPDATE SET
            folder=excluded.folder,
            subject=excluded.subject,
            email_date=excluded.email_date,
            timestamp_val=excluded.timestamp_val,
            from_sender=excluded.from_sender,
            assignee=CASE WHEN excluded.assignee != '' THEN excluded.assignee ELSE giuc_tien_do_emails.assignee END,
            contract=CASE WHEN excluded.contract != '' THEN excluded.contract ELSE giuc_tien_do_emails.contract END,
            sr_ticket=CASE WHEN excluded.sr_ticket != '' THEN excluded.sr_ticket ELSE giuc_tien_do_emails.sr_ticket END,
            priority=CASE WHEN excluded.priority != '' THEN excluded.priority ELSE giuc_tien_do_emails.priority END,
            request_content=CASE WHEN excluded.request_content != '' THEN excluded.request_content ELSE giuc_tien_do_emails.request_content END,
            request_time=CASE WHEN excluded.request_time != '' THEN excluded.request_time ELSE giuc_tien_do_emails.request_time END,
            raw_html=CASE WHEN excluded.raw_html != '' THEN excluded.raw_html ELSE giuc_tien_do_emails.raw_html END,
            raw_zstd=CASE WHEN excluded.raw_zstd IS NOT NULL THEN excluded.raw_zstd ELSE giuc_tien_do_emails.raw_zstd END
        """, (
            record.get("msg_uid"),
            record.get("folder"),
            record.get("subject"),
            record.get("email_date"),
            record.get("timestamp_val", 0),
            record.get("from_sender"),
            record.get("assignee", ""),
            record.get("contract", ""),
            record.get("sr_ticket", ""),
            record.get("priority", ""),
            record.get("request_content", ""),
            record.get("request_time", ""),
            record.get("raw_html", ""),
            compressed_blob
        ))
        conn.commit()
        return True
    except Exception as e:
        print(f"Database error on save_giuc_tien_do_record: {e}")
        return False
    finally:
        conn.close()


def save_cll_record(record):
    conn = get_connection()
    try:
        raw_to_compress = record.get("raw_bytes") or record.get("raw_html") or ""
        conn.execute("""
            INSERT INTO cll_emails (
                msg_uid, folder, subject, email_date, timestamp_val, from_sender,
                contract, occurrence_count, initial_status, raw_html, raw_zstd, staff
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(msg_uid) DO UPDATE SET
                subject=excluded.subject, email_date=excluded.email_date,
                timestamp_val=excluded.timestamp_val, from_sender=excluded.from_sender,
                contract=excluded.contract, occurrence_count=excluded.occurrence_count,
                initial_status=excluded.initial_status, raw_html=excluded.raw_html,
                raw_zstd=excluded.raw_zstd,
                staff=COALESCE(excluded.staff, cll_emails.staff)
        """, (
            record.get("msg_uid"), record.get("folder"), record.get("subject"),
            record.get("email_date"), record.get("timestamp_val", 0), record.get("from_sender"),
            record.get("contract", ""), record.get("occurrence_count", 0),
            record.get("initial_status", ""), record.get("raw_html", ""),
            compress_bytes(raw_to_compress),
            record.get("staff", "")
        ))
        conn.commit()
        return True
    except Exception as e:
        print(f"Database error on save_cll_record: {e}")
        return False
    finally:
        conn.close()


def update_cll_staff(item_id, staff):
    conn = get_connection()
    try:
        conn.execute("UPDATE cll_emails SET staff = ? WHERE id = ?", (staff, item_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Database error on update_cll_staff: {e}")
        return False
    finally:
        conn.close()


def log_sync(status, scanned, added, message):
    conn = get_connection()
    try:
        conn.execute("""
        INSERT INTO sync_logs (status, emails_scanned, emails_added, message)
        VALUES (?, ?, ?, ?)
        """, (status, scanned, added, message))
        conn.commit()
    except Exception as e:
        print(f"Database error on log_sync: {e}")
    finally:
        conn.close()


def get_last_sync():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM sync_logs ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def get_setting(key, default=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        row = cur.fetchone()
        if row:
            return row['value']
        return default
    finally:
        conn.close()


def set_setting(key, value):
    conn = get_connection()
    try:
        conn.execute("""
        INSERT INTO app_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, str(value)))
        conn.commit()
    finally:
        conn.close()
