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
        connect_timeout=15,
        prepare_threshold=None
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

        # Bảng au_records (Tra Cứu AU)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS au_records (
            id BIGINT PRIMARY KEY,
            so_hop_dong TEXT DEFAULT '',
            tap_diem TEXT DEFAULT '',
            tstc TEXT DEFAULT '',
            duong TEXT DEFAULT '',
            ktv_t10 TEXT DEFAULT '',
            block TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_au_so_hop_dong ON au_records(so_hop_dong);
        CREATE INDEX IF NOT EXISTS idx_au_tap_diem ON au_records(tap_diem);
        CREATE INDEX IF NOT EXISTS idx_au_tstc ON au_records(tstc);
        CREATE INDEX IF NOT EXISTS idx_au_block ON au_records(block);
        """)

        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
            cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_au_trgm_so_hop_dong ON au_records USING gin (so_hop_dong gin_trgm_ops);
            CREATE INDEX IF NOT EXISTS idx_au_trgm_tap_diem ON au_records USING gin (tap_diem gin_trgm_ops);
            CREATE INDEX IF NOT EXISTS idx_au_trgm_tstc ON au_records USING gin (tstc gin_trgm_ops);
            CREATE INDEX IF NOT EXISTS idx_au_trgm_duong ON au_records USING gin (duong gin_trgm_ops);
            CREATE INDEX IF NOT EXISTS idx_au_trgm_ktv ON au_records USING gin (ktv_t10 gin_trgm_ops);
            """)
        except Exception as trgm_err:
            print(f"Warning: Could not create pg_trgm indexes for au_records: {trgm_err}")

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


# =========================================================================
# TRA CỨU AU: STATS, LOOKUP, IMPORT & CRUD
# =========================================================================
import time


def get_au_stats():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                COUNT(*) AS total,
                COUNT(DISTINCT NULLIF(so_hop_dong, '')) AS contracts,
                COUNT(DISTINCT NULLIF(tap_diem, '')) AS tap_diems,
                COUNT(DISTINCT NULLIF(tstc, '')) AS tstcs,
                COUNT(DISTINCT NULLIF(block, '')) AS blocks
            FROM au_records
        """)
        row = cur.fetchone()
        return {
            "total": row['total'] if row else 0,
            "contracts": row['contracts'] if row else 0,
            "tap_diems": row['tap_diems'] if row else 0,
            "tstcs": row['tstcs'] if row else 0,
            "blocks": row['blocks'] if row else 0,
        }
    except Exception as e:
        print(f"Error in get_au_stats: {e}")
        return {"total": 0, "contracts": 0, "tap_diems": 0, "tstcs": 0, "blocks": 0}
    finally:
        conn.close()


def get_au_max_id(cur=None):
    if cur:
        cur.execute("SELECT COALESCE(MAX(id), 0) FROM au_records")
        res = cur.fetchone()
        return res[0] if res else 0
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT COALESCE(MAX(id), 0) FROM au_records")
        res = c.fetchone()
        return res[0] if res else 0
    finally:
        conn.close()


def get_au_records(search="", so_hop_dong="", tap_diem="", tstc="", duong="", ktv="", block="", page=1, limit=30):
    start_t = time.perf_counter()
    conn = get_connection()
    try:
        cur = conn.cursor()
        conditions = []
        params = []

        # 1. Tìm kiếm tổng hợp thông minh (Số hợp đồng / Tập điểm / TSTC / Đường / KTV)
        if search:
            kw = f"%{search.strip()}%"
            conditions.append("(so_hop_dong ILIKE ? OR tap_diem ILIKE ? OR tstc ILIKE ? OR duong ILIKE ? OR ktv_t10 ILIKE ?)")
            params.extend([kw, kw, kw, kw, kw])

        # 2. Bộ lọc trường chi tiết theo yêu cầu
        if so_hop_dong:
            conditions.append("so_hop_dong ILIKE ?")
            params.append(f"%{so_hop_dong.strip()}%")
        if tap_diem:
            conditions.append("tap_diem ILIKE ?")
            params.append(f"%{tap_diem.strip()}%")
        if tstc:
            conditions.append("tstc ILIKE ?")
            params.append(f"%{tstc.strip()}%")
        if duong:
            conditions.append("duong ILIKE ?")
            params.append(f"%{duong.strip()}%")
        if ktv:
            conditions.append("ktv_t10 ILIKE ?")
            params.append(f"%{ktv.strip()}%")
        if block:
            conditions.append("block ILIKE ?")
            params.append(f"%{block.strip()}%")

        where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""

        # Tổng số kết quả phù hợp
        cur.execute(f"SELECT COUNT(*) FROM au_records {where_sql}", params)
        count_row = cur.fetchone()
        total = count_row[0] if count_row else 0

        # Lấy dữ liệu phân trang
        offset = max(0, (page - 1) * limit)
        cur.execute(f"""
            SELECT id, so_hop_dong, tap_diem, tstc, duong, ktv_t10, block, created_at, updated_at
            FROM au_records
            {where_sql}
            ORDER BY id ASC
            LIMIT ? OFFSET ?
        """, params + [limit, offset])
        rows = [dict(r) for r in cur.fetchall()]

        elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)
        total_pages = (total + limit - 1) // limit if limit > 0 else 1

        return {
            "records": rows,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "query_time_ms": elapsed_ms
        }
    except Exception as e:
        print(f"Error in get_au_records: {e}")
        return {"records": [], "total": 0, "page": page, "limit": limit, "total_pages": 0, "query_time_ms": 0, "error": str(e)}
    finally:
        conn.close()


def import_au_records(records, mode='append'):
    """
    Import danh sách AU theo template:
    ID của bản ghi mới tự động là MAX+1 liên tiếp
    """
    if not records:
        return {"success": True, "count": 0, "message": "Không có dữ liệu để import"}

    conn = get_connection()
    try:
        cur = conn.cursor()
        if mode == 'replace':
            cur.execute("DELETE FROM au_records")
            current_max_id = 0
        else:
            cur.execute("SELECT COALESCE(MAX(id), 0) FROM au_records")
            r = cur.fetchone()
            current_max_id = r[0] if r else 0

        insert_rows = []
        for rec in records:
            current_max_id += 1
            insert_rows.append((
                current_max_id,
                str(rec.get('so_hop_dong', '') or '').strip(),
                str(rec.get('tap_diem', '') or '').strip(),
                str(rec.get('tstc', '') or '').strip(),
                str(rec.get('duong', '') or '').strip(),
                str(rec.get('ktv_t10', '') or '').strip(),
                str(rec.get('block', '') or '').strip(),
            ))

        query = """
        INSERT INTO au_records (
            id, so_hop_dong, tap_diem, tstc, duong, ktv_t10, block
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (id) DO UPDATE SET
            so_hop_dong = excluded.so_hop_dong,
            tap_diem = excluded.tap_diem,
            tstc = excluded.tstc,
            duong = excluded.duong,
            ktv_t10 = excluded.ktv_t10,
            block = excluded.block,
            updated_at = CURRENT_TIMESTAMP
        """
        cur.executemany(query, insert_rows)
        conn.commit()
        return {"success": True, "count": len(insert_rows), "max_id": current_max_id}
    except Exception as e:
        conn.rollback()
        print(f"Error importing au_records: {e}")
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def add_au_record(data):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM au_records")
        new_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO au_records (id, so_hop_dong, tap_diem, tstc, duong, ktv_t10, block)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            new_id,
            str(data.get('so_hop_dong', '') or '').strip(),
            str(data.get('tap_diem', '') or '').strip(),
            str(data.get('tstc', '') or '').strip(),
            str(data.get('duong', '') or '').strip(),
            str(data.get('ktv_t10', '') or '').strip(),
            str(data.get('block', '') or '').strip()
        ))
        conn.commit()
        return {"success": True, "id": new_id}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def update_au_record(au_id, data):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE au_records
            SET so_hop_dong = ?, tap_diem = ?, tstc = ?, duong = ?, ktv_t10 = ?, block = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            str(data.get('so_hop_dong', '') or '').strip(),
            str(data.get('tap_diem', '') or '').strip(),
            str(data.get('tstc', '') or '').strip(),
            str(data.get('duong', '') or '').strip(),
            str(data.get('ktv_t10', '') or '').strip(),
            str(data.get('block', '') or '').strip(),
            au_id
        ))
        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def delete_au_record(au_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM au_records WHERE id = ?", (au_id,))
        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def clear_all_au_records():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM au_records")
        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def get_au_filters():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT block FROM au_records WHERE block IS NOT NULL AND block != '' ORDER BY block")
        blocks = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT ktv_t10 FROM au_records WHERE ktv_t10 IS NOT NULL AND ktv_t10 != '' ORDER BY ktv_t10")
        ktvs = [r[0] for r in cur.fetchall()]
        return {"blocks": blocks, "ktvs": ktvs}
    except Exception as e:
        print(f"Error in get_au_filters: {e}")
        return {"blocks": [], "ktvs": []}
    finally:
        conn.close()

