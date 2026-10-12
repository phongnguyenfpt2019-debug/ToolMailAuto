"""
nhansu_service.py
-----------------
Dich vu Nhan Su: doc du lieu tu Google Sheets va gui mail thong bao tu dong.

Sheet: Chi Nhanh Sai Gon 01
SHEET_ID : 17QLc9SlfpPPrR-d1R2BkBxA7DmCI5ZCuhmQffP5F6pY
GID      : 32204814
"""

import smtplib
import threading
import json
import os
import hashlib
import csv
import io
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from urllib import request as urlreq, error as urlerr
from config import DATA_DIR

# ─────────────────────────── Config ───────────────────────────
SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "17QLc9SlfpPPrR-d1R2BkBxA7DmCI5ZCuhmQffP5F6pY")
GID      = os.getenv("GOOGLE_SHEET_GID", "32204814")

CSV_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    f"/export?format=csv&gid={GID}"
)

# SMTP FPT Mail
SMTP_HOST    = os.getenv("SMTP_HOST", "mail.fpt.net")
SMTP_PORT    = int(os.getenv("SMTP_PORT", "587"))
SENDER_EMAIL = os.getenv("SMTP_SENDER_EMAIL", os.getenv("DEFAULT_EMAIL", "phuongnam.phongnh5@fpt.net"))
SENDER_PASS  = os.getenv("SMTP_SENDER_PASS", os.getenv("DEFAULT_PASSWORD", ""))

_DATA_DIR   = DATA_DIR
_HASH_FILE  = os.path.join(_DATA_DIR, "nhansu_hash.json")
_CACHE_FILE = os.path.join(_DATA_DIR, "nhansu_cache.json")

# ─────────────────────────── Column names ───────────────────────────
COLS_NV      = ["Ho Ten NV", "Họ Tên NV", "Inside Account"]   # fallback order
COL_BLOCK    = "Block"
COL_DT_NAME  = "Ho ten Doi truong"    # will try multiple keys
COL_DT_NAMES = ["Ho ten Doi truong", "Họ tên Đội trưởng", "Ho tên Đội trưởng"]
COL_EMAIL    = "Email"
COL_MA_NV    = "Ma NV"
COL_MA_NAMES = ["Ma NV", "Mã NV"]
COL_STATUS   = "Tinh trang Tai khoan"
COL_CONTRACT = "Tinh trang Hop dong"
COL_CHUCVU   = "Chuc danh"
COL_LOAIHD   = "Loai HDLD"
COL_SDT      = "So dien thoai"
COL_VUNG     = "Vung"
COL_DOITAC   = "Doi tac"
COL_NGAYVAO  = "Ngay Vo Cong Ty"


def _ensure_data_dir():
    os.makedirs(_DATA_DIR, exist_ok=True)


def _get_col(row: dict, candidates: list) -> str:
    """Try multiple possible column name variants and return first match."""
    for key in row:
        stripped = key.strip()
        for cand in candidates:
            if stripped == cand or stripped.replace(" ", "") == cand.replace(" ", ""):
                return row[key].strip() if row[key] else ""
    return ""


# ─────────────────────────── Fetch ───────────────────────────

def fetch_sheet_data() -> list:
    """Tai du lieu tu Google Sheets (CSV public export). Tra ve list dict."""
    try:
        req = urlreq.Request(CSV_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urlreq.urlopen(req, timeout=25) as resp:
            content = resp.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        rows = []
        for row in reader:
            # Normalize keys: strip whitespace
            cleaned = {}
            for k, v in row.items():
                if k is not None:
                    cleaned[k.strip()] = (v.strip() if v else "")
            rows.append(cleaned)
        return rows
    except Exception as e:
        print(f"[NhanSu] Loi tai Sheet: {e}")
        return []


def _compute_hash(rows: list) -> str:
    raw = json.dumps(rows, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()


def _load_hash() -> str:
    _ensure_data_dir()
    if os.path.exists(_HASH_FILE):
        try:
            with open(_HASH_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("hash", "")
        except Exception:
            pass
    return ""


def _save_hash(h: str):
    _ensure_data_dir()
    with open(_HASH_FILE, "w", encoding="utf-8") as f:
        json.dump({"hash": h, "updated_at": datetime.now().isoformat()}, f)


def _save_cache(rows: list):
    _ensure_data_dir()
    with open(_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def _load_cache() -> list:
    _ensure_data_dir()
    if os.path.exists(_CACHE_FILE):
        try:
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


# ─────────────────────────── Helpers ───────────────────────────

def get_nv_name(row: dict) -> str:
    """Lay ten nhan vien tu 'Ho Ten NV' hoac 'Inside Account'."""
    # Try exact then fuzzy
    for col in ["Họ Tên NV", "Ho Ten NV", "ho ten nv"]:
        v = row.get(col, "").strip()
        if v:
            return v
    # Fuzzy: any key containing "ho ten nv" or "ho tên"
    for k, v in row.items():
        kl = k.lower().replace(" ", "")
        if ("hotn" in kl or "hotennv" in kl) and v.strip():
            return v.strip()
    # Fallback: Inside Account
    for col in ["Inside Account", "inside account"]:
        v = row.get(col, "").strip()
        if v:
            return v
    for k, v in row.items():
        if "inside" in k.lower() and v.strip():
            return v.strip()
    return ""


def get_ma_nv(row: dict) -> str:
    for col in ["Mã NV", "Ma NV"]:
        v = row.get(col, "").strip()
        if v:
            return v
    for k, v in row.items():
        if "m" in k.lower() and "nv" in k.lower() and v.strip():
            return v.strip()
    return ""


def get_doi_truong(row: dict) -> str:
    for col in ["Họ tên Đội trưởng", "Ho ten Doi truong", "Họ Tên Đội Trưởng"]:
        v = row.get(col, "").strip()
        if v:
            return v
    for k, v in row.items():
        kl = k.lower()
        if ("doi" in kl or "đội" in kl) and ("truong" in kl or "trưởng" in kl) and v.strip():
            return v.strip()
    return ""


def get_block(row: dict) -> str:
    v = row.get("Block", "").strip()
    return v


def get_email(row: dict) -> str:
    v = row.get("Email", "").strip()
    if not v:
        for k, val in row.items():
            if k.lower() == "email" and val.strip():
                return val.strip()
    return v


def get_blocks(rows: list) -> list:
    blocks = sorted({get_block(r) for r in rows if get_block(r)})
    return blocks


def get_doi_truong_list(rows: list) -> list:
    names = sorted({get_doi_truong(r) for r in rows if get_doi_truong(r)})
    return names


def filter_rows(rows: list, block: str = "", doi_truong: str = "", search: str = "") -> list:
    result = []
    for row in rows:
        if block and get_block(row) != block:
            continue
        if doi_truong and get_doi_truong(row) != doi_truong:
            continue
        if search:
            s = search.lower()
            nv = get_nv_name(row).lower()
            ma = get_ma_nv(row).lower()
            inside = row.get("Inside Account", "").lower()
            if s not in nv and s not in ma and s not in inside:
                continue
        result.append(row)
    return result


# ─────────────────────────── Email ───────────────────────────

def _build_email_html(rows: list, context: str = "Cap nhat nhan su") -> str:
    rows_html = ""
    for row in rows:
        nv     = get_nv_name(row)
        ma     = get_ma_nv(row)
        blk    = get_block(row)
        dt     = get_doi_truong(row)
        em     = get_email(row)
        sdt    = row.get("Số điện thoại", row.get("So dien thoai", ""))
        chucvu = row.get("Chức danh", row.get("Chuc danh", ""))
        tthd   = row.get("Tình trạng Hợp đồng", row.get("Tinh trang Hop dong", ""))
        ngayvao= row.get("Ngày Vô Công Ty", row.get("Ngay Vo Cong Ty", ""))
        rows_html += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;white-space:nowrap">{nv}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f1f5f9">{ma}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f1f5f9">{blk}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f1f5f9">{chucvu}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f1f5f9">{tthd}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;white-space:nowrap">{dt}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f1f5f9">{sdt}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f1f5f9">{em}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f1f5f9">{ngayvao}</td>
        </tr>"""

    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;">
<div style="max-width:820px;margin:28px auto;background:#fff;border-radius:14px;
            border:1px solid #e2e8f0;overflow:hidden;box-shadow:0 4px 16px rgba(0,0,0,.1);">
  <!-- Header -->
  <div style="background:linear-gradient(135deg,#f26f21 0%,#ff9a56 100%);padding:22px 30px;display:flex;align-items:center;gap:16px;">
    <img src="https://management.mypt.vn/images/FPT_Telecom_logo.svg" height="40"
         style="filter:brightness(0) invert(1);display:block;" alt="FPT Telecom">
    <div>
      <div style="color:#fff;font-weight:800;font-size:15px;letter-spacing:.3px;">CHI NHÁNH SÀI GÒN 01</div>
      <div style="color:#ffe8d6;font-size:11px;margin-top:2px;">Hệ Thống Nhân Sự · Cập Nhật Tự Động</div>
    </div>
  </div>
  <!-- Body -->
  <div style="padding:26px 30px;">
    <h2 style="margin:0 0 8px;font-size:17px;color:#1e293b;">{context}</h2>
    <p style="margin:0 0 20px;font-size:13px;color:#64748b;line-height:1.6;">
      Hệ thống phát hiện thay đổi trong dữ liệu nhân sự lúc <strong>{now_str}</strong>.
      Danh sách chi tiết bên dưới. Vui lòng kiểm tra và xác nhận thông tin.
    </p>
    <div style="overflow-x:auto;">
    <table style="width:100%;border-collapse:collapse;font-size:12px;min-width:700px;">
      <thead>
        <tr style="background:#fff7ed;">
          <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #f26f21;color:#c2410c;white-space:nowrap">Họ Tên NV</th>
          <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #f26f21;color:#c2410c">Mã NV</th>
          <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #f26f21;color:#c2410c">Block</th>
          <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #f26f21;color:#c2410c">Chức Danh</th>
          <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #f26f21;color:#c2410c">Tình Trạng HĐ</th>
          <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #f26f21;color:#c2410c;white-space:nowrap">Đội Trưởng</th>
          <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #f26f21;color:#c2410c">SĐT</th>
          <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #f26f21;color:#c2410c">Email</th>
          <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #f26f21;color:#c2410c;white-space:nowrap">Ngày Vào</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    </div>
    <p style="margin:20px 0 0;font-size:12px;color:#94a3b8;">
      Tổng cộng: <strong style="color:#1e293b">{len(rows)}</strong> nhân viên trong danh sách.
    </p>
  </div>
  <!-- Footer -->
  <div style="background:#f8fafc;padding:14px 30px;border-top:1px solid #e2e8f0;
              font-size:11px;color:#94a3b8;">
    Email tự động gửi bởi FPT Telecom CSKH &amp; Vận Hành · {SENDER_EMAIL}
  </div>
</div>
</body></html>"""


def send_notification_email(recipients: list, subject: str, rows: list, context: str = "Cap nhat nhan su"):
    """Gui mail thong bao qua SMTP FPT."""
    if not recipients:
        print("[NhanSu] Khong co nguoi nhan, bo qua gui mail.")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = SENDER_EMAIL
        msg["To"]      = ", ".join(recipients)
        html = _build_email_html(rows, context)
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASS)
            server.sendmail(SENDER_EMAIL, recipients, msg.as_string())
        print(f"[NhanSu] Da gui mail den: {recipients}")
        return True
    except Exception as e:
        print(f"[NhanSu] Loi gui mail: {e}")
        return False


# ─────────────────────────── Auto-sync ───────────────────────────

_stop_event = threading.Event()


def _auto_sync_loop(interval_seconds: int = 300):
    print(f"[NhanSu] Auto-sync khoi dong (moi {interval_seconds}s)")
    while not _stop_event.is_set():
        try:
            rows = fetch_sheet_data()
            if rows:
                new_hash = _compute_hash(rows)
                old_hash = _load_hash()
                if new_hash != old_hash:
                    print("[NhanSu] Phat hien du lieu moi tu Sheet → da cap nhat cache (khong gui mail tu dong).")
                    _save_cache(rows)
                    _save_hash(new_hash)
                else:
                    if not os.path.exists(_CACHE_FILE):
                        _save_cache(rows)
        except Exception as e:
            print(f"[NhanSu] Loi auto-sync: {e}")
        _stop_event.wait(interval_seconds)


def start_auto_sync(interval_seconds: int = 300):
    t = threading.Thread(target=_auto_sync_loop, args=(interval_seconds,), daemon=True)
    t.start()
    return t


def stop_auto_sync():
    _stop_event.set()


# ─────────────────────────── Public API ───────────────────────────

def get_cached_or_fetch() -> list:
    """Tra ve cache neu co, nguoc lai fetch moi tu Sheet."""
    cache = _load_cache()
    if cache:
        return cache
    rows = fetch_sheet_data()
    if rows:
        _save_cache(rows)
        _save_hash(_compute_hash(rows))
    return rows


_lookup_cache = None
_lookup_cache_time = 0

def get_employee_lookup() -> tuple[dict, dict]:
    """
    Tra ve (inside_map, name_map) de tra cuu nhanh:
    inside_map: { 'PNC01.HOIDV': info_dict, ... } (keys in uppercase)
    name_map:   { 'lê văn tánh': info_dict, ... } (keys in lowercase)
    """
    global _lookup_cache, _lookup_cache_time
    import time
    now = time.time()
    if _lookup_cache and (now - _lookup_cache_time < 30):
        return _lookup_cache

    rows = get_cached_or_fetch()
    inside_map = {}
    name_map = {}
    for r in rows:
        name = get_nv_name(r).strip()
        inside = r.get("Inside Account", "").strip()
        block = get_block(r).strip()
        dt = get_doi_truong(r).strip()
        ma_nv = get_ma_nv(r).strip()
        email = get_email(r).strip()
        info = {
            "name": name,
            "inside": inside,
            "block": block,
            "doi_truong": dt,
            "ma_nv": ma_nv,
            "email": email
        }
        if inside:
            inside_map[inside.upper()] = info
        if name:
            name_map[name.lower()] = info

    _lookup_cache = (inside_map, name_map)
    _lookup_cache_time = now
    return inside_map, name_map


def find_employee_info(identifier: str) -> dict | None:
    """Tim thong tin nhan vien bang Inside Account hoac Ho Ten NV."""
    if not identifier:
        return None
    raw = str(identifier).strip()
    if not raw:
        return None
    inside_map, name_map = get_employee_lookup()
    if raw.upper() in inside_map:
        return inside_map[raw.upper()]
    if raw.lower() in name_map:
        return name_map[raw.lower()]
    # Fuzzy partial match
    raw_lower = raw.lower()
    for name, info in name_map.items():
        if raw_lower in name or name in raw_lower:
            return info
    return None


def get_matching_identifiers(block: str = "", doi_truong: str = "") -> tuple[set, set]:
    """
    Lay danh sach Inside Accounts (uppercase) va Ho Ten (lowercase)
    thuoc ve Block hoac/va Doi Truong da chon.
    """
    block = (block or "").strip()
    doi_truong = (doi_truong or "").strip()
    if not block and not doi_truong:
        return set(), set()

    rows = get_cached_or_fetch()
    matched_insides = set()
    matched_names = set()

    for r in rows:
        r_block = get_block(r).strip()
        r_dt = get_doi_truong(r).strip()
        if block and r_block != block:
            continue
        if doi_truong and r_dt != doi_truong:
            continue
        inside = r.get("Inside Account", "").strip()
        name = get_nv_name(r).strip()
        if inside:
            matched_insides.add(inside.upper())
        if name:
            matched_names.add(name.lower())

    return matched_insides, matched_names

