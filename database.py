import os
import sqlite3
import zstandard as zstd
from config import DATA_DIR, DB_PATH

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
        return dctx.decompress(compressed_bytes).decode('utf-8', errors='ignore')
    except Exception:
        return ""

def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cem_emails (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        msg_uid TEXT UNIQUE,
        folder TEXT,
        subject TEXT,
        email_date TEXT,
        timestamp_val REAL,
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
        raw_zstd BLOB,
        is_reply INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Ensure raw_zstd column exists if db was created earlier
    cursor.execute("PRAGMA table_info(cem_emails)")
    cols = [r[1] for r in cursor.fetchall()]
    if 'raw_zstd' not in cols:
        cursor.execute("ALTER TABLE cem_emails ADD COLUMN raw_zstd BLOB")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS giuc_tien_do_emails (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        msg_uid TEXT UNIQUE,
        folder TEXT,
        subject TEXT,
        email_date TEXT,
        timestamp_val REAL,
        from_sender TEXT,
        assignee TEXT,
        contract TEXT,
        sr_ticket TEXT,
        priority TEXT,
        request_content TEXT,
        request_time TEXT,
        raw_html TEXT,
        raw_zstd BLOB,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cll_emails (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        msg_uid TEXT UNIQUE,
        folder TEXT,
        subject TEXT,
        email_date TEXT,
        timestamp_val REAL,
        from_sender TEXT,
        contract TEXT,
        occurrence_count INTEGER,
        initial_status TEXT,
        raw_html TEXT,
        raw_zstd BLOB,
        staff TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    try:
        cursor.execute("ALTER TABLE cll_emails ADD COLUMN staff TEXT")
    except Exception:
        pass

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sync_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sync_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT,
        emails_scanned INTEGER,
        emails_added INTEGER,
        message TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """)

    conn.commit()
    conn.close()

def get_connection():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def save_email_record(record):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Compress raw content with zstandard
        raw_to_compress = record.get("raw_bytes") or record.get("raw_html") or ""
        compressed_blob = compress_bytes(raw_to_compress)

        cursor.execute("""
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
    cursor = conn.cursor()
    try:
        raw_to_compress = record.get("raw_bytes") or record.get("raw_html") or ""
        compressed_blob = compress_bytes(raw_to_compress)

        cursor.execute("""
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
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO sync_logs (status, emails_scanned, emails_added, message)
    VALUES (?, ?, ?, ?)
    """, (status, scanned, added, message))
    conn.commit()
    conn.close()

def get_last_sync():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sync_logs ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def get_setting(key, default=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row['value']
    return default

def set_setting(key, value):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO app_settings (key, value) VALUES (?, ?)
    ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, str(value)))
    conn.commit()
    conn.close()
