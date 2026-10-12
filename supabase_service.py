"""Read-only access to the `bt` table used by the CLL >3 tag."""
from datetime import datetime, timedelta
import re

from config import (
    SUPABASE_DB_HOST, SUPABASE_DB_PORT, SUPABASE_DB_NAME, SUPABASE_DB_USER,
    SUPABASE_DB_PASSWORD, SUPABASE_BT_TABLE, SUPABASE_BT_CONTRACT_COL,
    SUPABASE_BT_STAFF_COL, SUPABASE_BT_CREATED_COL, SUPABASE_BT_COMPLETED_COL,
    SUPABASE_BT_STAFF_NOTE_COL, SUPABASE_BT_CC_NOTE_COL,
)


def _ident(value):
    if not re.fullmatch(r"[^\W\d]\w*", value or ""):
        raise ValueError("Tên bảng/cột Supabase không hợp lệ")
    return f'"{value}"'


def get_bt_occurrences(contract, received_timestamp, occurrence_count):
    """Return the most recent bt rows in the 30 days ending at email receipt."""
    if not contract or not received_timestamp:
        return []
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Thiếu thư viện psycopg. Hãy chạy pip install -r requirements.txt") from exc

    received_at = datetime.fromtimestamp(float(received_timestamp))
    start_at = received_at - timedelta(days=30)
    columns = {
        "contract": SUPABASE_BT_CONTRACT_COL, "staff": SUPABASE_BT_STAFF_COL,
        "created_at": SUPABASE_BT_CREATED_COL, "completed_at": SUPABASE_BT_COMPLETED_COL,
        "staff_note": SUPABASE_BT_STAFF_NOTE_COL, "cc_note": SUPABASE_BT_CC_NOTE_COL,
    }
    select_fields = ", ".join(f"{_ident(col)} AS {key}" for key, col in columns.items())
    query = f"""
        SELECT {select_fields}
        FROM {_ident(SUPABASE_BT_TABLE)}
        WHERE CAST({_ident(SUPABASE_BT_CONTRACT_COL)} AS TEXT) = %s
          AND CAST({_ident(SUPABASE_BT_COMPLETED_COL)} AS TIMESTAMP) >= %s
          AND CAST({_ident(SUPABASE_BT_COMPLETED_COL)} AS TIMESTAMP) <= %s
        ORDER BY CAST({_ident(SUPABASE_BT_COMPLETED_COL)} AS TIMESTAMP) DESC
        LIMIT %s
    """
    with psycopg.connect(host=SUPABASE_DB_HOST, port=SUPABASE_DB_PORT,
                          dbname=SUPABASE_DB_NAME, user=SUPABASE_DB_USER,
                          password=SUPABASE_DB_PASSWORD, sslmode="require",
                          connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(query, (contract, start_at, received_at, max(int(occurrence_count or 1), 1)))
            names = [col.name for col in cur.description]
            return [dict(zip(names, row)) for row in cur.fetchall()]


def get_staff_for_contracts_map(contracts):
    """Batch fetch latest staff (Inside Account) for a list of contract codes."""
    if not contracts:
        return {}
    clean_contracts = list({str(c).strip() for c in contracts if c and str(c).strip()})
    if not clean_contracts:
        return {}
    try:
        import psycopg
    except ImportError:
        return {}
    try:
        query = f"""
            SELECT {_ident(SUPABASE_BT_CONTRACT_COL)}, {_ident(SUPABASE_BT_STAFF_COL)}
            FROM {_ident(SUPABASE_BT_TABLE)}
            WHERE CAST({_ident(SUPABASE_BT_CONTRACT_COL)} AS TEXT) = ANY(%s)
            ORDER BY CAST({_ident(SUPABASE_BT_COMPLETED_COL)} AS TIMESTAMP) DESC
        """
        with psycopg.connect(host=SUPABASE_DB_HOST, port=SUPABASE_DB_PORT,
                              dbname=SUPABASE_DB_NAME, user=SUPABASE_DB_USER,
                              password=SUPABASE_DB_PASSWORD, sslmode="require",
                              connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute(query, (clean_contracts,))
                res = {}
                for c, s in cur.fetchall():
                    c_str = str(c).strip() if c else ""
                    s_str = str(s).strip() if s else ""
                    if c_str and s_str and c_str not in res:
                        res[c_str] = s_str
                return res
    except Exception as exc:
        print(f"[Supabase] get_staff_for_contracts_map error: {exc}")
        return {}


def get_staff_for_contract(contract, received_timestamp=None):
    """Return the most recent staff (Inside Account) for this contract in bt table."""
    if not contract:
        return ""
    mapping = get_staff_for_contracts_map([contract])
    return mapping.get(str(contract).strip(), "")


def sync_missing_cll_staff():
    """Find all cll_emails rows with missing staff, look up from Supabase, and update SQLite."""
    import database
    try:
        conn = database.get_connection()
        rows = conn.execute("SELECT id, contract FROM cll_emails WHERE (staff IS NULL OR TRIM(staff) = '') AND contract != ''").fetchall()
        conn.close()
        if not rows:
            return 0
        contracts = [r["contract"] for r in rows]
        mapping = get_staff_for_contracts_map(contracts)
        if not mapping:
            return 0
        updated = 0
        conn = database.get_connection()
        for r in rows:
            st = mapping.get(r["contract"])
            if st:
                conn.execute("UPDATE cll_emails SET staff = ? WHERE id = ?", (st, r["id"]))
                updated += 1
        conn.commit()
        conn.close()
        print(f"[Supabase] Backfilled staff for {updated}/{len(rows)} CLL records.")
        return updated
    except Exception as exc:
        print(f"[Supabase] sync_missing_cll_staff error: {exc}")
        return 0

