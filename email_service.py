import re
import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime
from bs4 import BeautifulSoup
import database
import supabase_service
from config import (
    DEFAULT_IMAP_SERVER,
    DEFAULT_IMAP_PORT,
    DEFAULT_EMAIL,
    DEFAULT_PASSWORD,
    SYNC_FOLDERS
)

def decode_mime(s):
    if not s:
        return ''
    try:
        parts = decode_header(s)
        res = []
        for text, enc in parts:
            if isinstance(text, bytes):
                enc_name = enc.lower() if enc else 'utf-8'
                if enc_name in ('unknown-8bit', 'none', 'default'):
                    enc_name = 'utf-8'
                try:
                    res.append(text.decode(enc_name, errors='ignore'))
                except Exception:
                    res.append(text.decode('utf-8', errors='ignore'))
            else:
                res.append(str(text))
        return ''.join(res)
    except Exception:
        return str(s)

def extract_district(address):
    if not address:
        return ""
    # Common VN address parsing patterns
    # E.g. "..., Phường Tăng Nhơn Phú, Hồ Chí Minh" or "..., Phường Thủ Đức, Hồ Chí Minh"
    parts = [p.strip() for p in address.split(",") if p.strip()]
    if len(parts) >= 2:
        return parts[-2]
    return ""

def parse_cem_email(raw_bytes, subject, msg_date, folder, uid_str):
    msg = email.message_from_bytes(raw_bytes)
    
    html_content = ""
    text_content = ""
    
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdisp = str(part.get('Content-Disposition') or '')
            if 'attachment' not in cdisp:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or 'utf-8'
                    try:
                        dec = payload.decode(charset, errors='ignore')
                    except Exception:
                        dec = payload.decode('utf-8', errors='ignore')
                    if ctype == 'text/html':
                        html_content += dec
                    elif ctype == 'text/plain':
                        text_content += dec
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or 'utf-8'
            try:
                dec = payload.decode(charset, errors='ignore')
            except Exception:
                dec = payload.decode('utf-8', errors='ignore')
            html_content = dec
            text_content = dec

    # Parse date to timestamp
    timestamp_val = 0
    try:
        dt = parsedate_to_datetime(msg_date)
        timestamp_val = dt.timestamp()
    except Exception:
        timestamp_val = datetime.now().timestamp()

    # Detect reply/forward
    is_reply = 1 if re.match(r'^(RE:|FW:|FWD:)', subject, re.IGNORECASE) else 0

    # Extract contract from subject: CEM - CSAT 1, 2 CLDV - <CONTRACT> - ...
    contract_subject = ""
    contract_match = re.search(r'CLDV\s*-\s*([A-Za-z0-9]+)', subject, re.IGNORECASE)
    if contract_match:
        contract_subject = contract_match.group(1).strip()

    record = {
        "msg_uid": f"{folder}:{uid_str}",
        "folder": folder,
        "subject": subject,
        "email_date": msg_date,
        "timestamp_val": timestamp_val,
        "from_sender": decode_mime(msg.get('From')),
        "contract": contract_subject,
        "customer_name": "",
        "phone": "",
        "address": "",
        "district": "",
        "eval_type": "",
        "channel": "",
        "eval_time": "",
        "completed_time": "",
        "technician": "",
        "csat_score": None,
        "issue_group": "",
        "notes": "",
        "home_support": "",
        "raw_html": html_content or f"<pre>{text_content}</pre>",
        "raw_bytes": raw_bytes,
        "is_reply": is_reply
    }

    if html_content:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 1. Parse Key-Value fields (Table 0 or rows)
        for tr in soup.find_all('tr'):
            txt = tr.get_text(' ', strip=True)
            if 'Loại đánh giá:' in txt:
                record["eval_type"] = txt.split('Loại đánh giá:')[-1].strip()
            elif 'Kênh ghi nhận:' in txt:
                record["channel"] = txt.split('Kênh ghi nhận:')[-1].strip()
            elif 'Thời gian đánh giá:' in txt:
                record["eval_time"] = txt.split('Thời gian đánh giá:')[-1].strip()
            elif 'Thời gian hoàn tất Triển khai/Bảo trì:' in txt:
                record["completed_time"] = txt.split('Thời gian hoàn tất Triển khai/Bảo trì:')[-1].strip()
            elif 'Tên chủ hợp đồng:' in txt:
                record["customer_name"] = txt.split('Tên chủ hợp đồng:')[-1].strip()
            elif 'Số hợp đồng:' in txt:
                contract_val = txt.split('Số hợp đồng:')[-1].strip()
                if contract_val:
                    record["contract"] = contract_val
            elif 'SĐT đánh giá:' in txt:
                record["phone"] = txt.split('SĐT đánh giá:')[-1].strip()
            elif 'Địa chỉ:' in txt:
                record["address"] = txt.split('Địa chỉ:')[-1].strip()
                record["district"] = extract_district(record["address"])

        # 2. Parse Evaluation Table (NVKT, CSAT, Nhóm lỗi phản ánh, Ghi chú, Yêu cầu hỗ trợ tại nhà)
        tables = soup.find_all('table')
        for t in tables:
            headers = [th.get_text(strip=True).upper() for th in t.find_all(['th', 'td'])]
            if any('NVKT' in h for h in headers) and any('CSAT' in h for h in headers):
                rows = t.find_all('tr')
                if len(rows) > 0:
                    header_row = rows[0]
                    col_names = [td.get_text(strip=True).upper() for td in header_row.find_all(['th', 'td'])]
                    
                    nvkt_idx = -1
                    csat_idx = -1
                    issue_idx = -1
                    note_idx = -1
                    support_idx = -1
                    
                    for idx, col in enumerate(col_names):
                        if 'NVKT' in col: nvkt_idx = idx
                        elif 'CSAT' in col: csat_idx = idx
                        elif 'NHÓM LỖI' in col or 'PHẢN ÁNH' in col: issue_idx = idx
                        elif 'GHI CHÚ' in col: note_idx = idx
                        elif 'HỖ TRỢ' in col: support_idx = idx
                    
                    if len(rows) > 1:
                        data_row = rows[1]
                        cells = [td.get_text(" ", strip=True) for td in data_row.find_all(['th', 'td'])]
                        if nvkt_idx >= 0 and nvkt_idx < len(cells):
                            record["technician"] = cells[nvkt_idx]
                        if csat_idx >= 0 and csat_idx < len(cells):
                            csat_val = cells[csat_idx].strip()
                            try:
                                record["csat_score"] = int(csat_val)
                            except Exception:
                                record["csat_score"] = None
                        if issue_idx >= 0 and issue_idx < len(cells):
                            record["issue_group"] = cells[issue_idx]
                        if note_idx >= 0 and note_idx < len(cells):
                            record["notes"] = cells[note_idx]
                        if support_idx >= 0 and support_idx < len(cells):
                            record["home_support"] = cells[support_idx]
                break

    # If CSAT score still None, check if "CSAT 1" or "CSAT 2" in subject
    if record["csat_score"] is None:
        if "CSAT 1," in subject or "CSAT 1 " in subject:
            # Could be general template
            pass

    return record

def parse_giuc_tien_do_email(raw_bytes, subject, msg_date, folder, uid_str):
    msg = email.message_from_bytes(raw_bytes)
    html_content = ""
    text_content = ""

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdisp = str(part.get('Content-Disposition') or '')
            if 'attachment' not in cdisp:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or 'utf-8'
                    try:
                        dec = payload.decode(charset, errors='ignore')
                    except Exception:
                        dec = payload.decode('utf-8', errors='ignore')
                    if ctype == 'text/html':
                        html_content += dec
                    elif ctype == 'text/plain':
                        text_content += dec
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or 'utf-8'
            try:
                dec = payload.decode(charset, errors='ignore')
            except Exception:
                dec = payload.decode('utf-8', errors='ignore')
            html_content = dec
            text_content = dec

    timestamp_val = 0
    try:
        dt = parsedate_to_datetime(msg_date)
        timestamp_val = dt.timestamp()
    except Exception:
        timestamp_val = datetime.now().timestamp()

    plain_for_regex = text_content
    if html_content:
        soup = BeautifulSoup(html_content, 'html.parser')
        plain_for_regex = soup.get_text("\n", strip=True)

    record = {
        "msg_uid": f"GIUC:{folder}:{uid_str}",
        "folder": folder,
        "subject": subject,
        "email_date": msg_date,
        "timestamp_val": timestamp_val,
        "from_sender": decode_mime(msg.get('From')),
        "assignee": "",
        "contract": "",
        "sr_ticket": "",
        "priority": "Bình thường",
        "request_content": "",
        "request_time": "",
        "raw_html": html_content or f"<pre>{text_content}</pre>",
        "raw_bytes": raw_bytes
    }

    # 1. Nhân viên xử lý: Khách hàng dang/đang chờ Anh/Chị (.+?) xử lý chăm sóc
    m_assignee = re.search(r'Khách hàng d[aáàạảã]ng chờ Anh/Chị\s+([^,\n\r]+?)\s+xử lý chăm sóc', plain_for_regex, re.IGNORECASE)
    if m_assignee:
        record["assignee"] = m_assignee.group(1).strip()

    # 2. Mã SR/Ticket
    m_ticket = re.search(r'Mã SR/Ticket\s*\n+([A-Za-z0-9\-]+)', plain_for_regex, re.IGNORECASE)
    if not m_ticket:
        m_ticket = re.search(r'Mã SR/Ticket[:\s]+([A-Za-z0-9\-]+)', plain_for_regex, re.IGNORECASE)
    if m_ticket:
        record["sr_ticket"] = m_ticket.group(1).strip()
        parts = record["sr_ticket"].split('-')
        if len(parts) >= 2:
            record["contract"] = parts[1].strip()
        else:
            c_match = re.search(r'(SG[A-Za-z0-9]+)', record["sr_ticket"])
            if c_match:
                record["contract"] = c_match.group(1)

    if not record["contract"]:
        m_subj_c = re.search(r'\[SOC\s*-\s*SR\]\s*([A-Za-z0-9]+)', subject, re.IGNORECASE)
        if m_subj_c:
            record["contract"] = m_subj_c.group(1).strip()

    # 3. Độ ưu tiên
    m_prio = re.search(r'Độ ưu tiên\s*\n+([^\n\r]+)', plain_for_regex, re.IGNORECASE)
    if not m_prio:
        m_prio = re.search(r'Độ ưu tiên[:\s]+([^\n\r]+)', plain_for_regex, re.IGNORECASE)
    if m_prio:
        record["priority"] = m_prio.group(1).strip()

    # 4. Thời gian gửi yêu cầu
    m_time = re.search(r'Thời gian gửi yêu cầu\s*\n+([^\n\r]+)', plain_for_regex, re.IGNORECASE)
    if not m_time:
        m_time = re.search(r'Thời gian gửi yêu cầu[:\s]+([^\n\r]+)', plain_for_regex, re.IGNORECASE)
    if m_time:
        record["request_time"] = m_time.group(1).strip()

    # 5. Nội dung yêu cầu
    m_content = re.search(r'Nội dung yêu cầu\s*\n+([^\n\r]+)', plain_for_regex, re.IGNORECASE)
    if not m_content:
        m_content = re.search(r'Nội dung yêu cầu[:\s]+([^\n\r]+)', plain_for_regex, re.IGNORECASE)
    if m_content:
        record["request_content"] = m_content.group(1).strip()

    return record

def parse_cll_email(raw_bytes, subject, msg_date, folder, uid_str):
    """Parse Checklist Bảo trì alerts, e.g. "SGABL6236 phát sinh checklist 3 lần"."""
    msg = email.message_from_bytes(raw_bytes)
    html_content = ""
    text_content = ""
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if 'attachment' in str(part.get('Content-Disposition') or ''):
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        try:
            value = payload.decode(part.get_content_charset() or 'utf-8', errors='ignore')
        except Exception:
            value = payload.decode('utf-8', errors='ignore')
        if part.get_content_type() == 'text/html':
            html_content += value
        elif part.get_content_type() == 'text/plain':
            text_content += value

    try:
        timestamp_val = parsedate_to_datetime(msg_date).timestamp()
    except Exception:
        timestamp_val = datetime.now().timestamp()
    # Some alerts omit the space between "Checklist" and "Bảo trì".
    contract_match = re.search(r'Checklist\s*Bảo\s+trì\s*[–-]\s*([A-Za-z0-9]+)', subject, re.IGNORECASE)
    count_match = re.search(r'phát\s+sinh\s+checklist\s+(\d+)\s+lần', subject, re.IGNORECASE)
    initial_status = ""
    if html_content:
        soup = BeautifulSoup(html_content, 'html.parser')
        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            if not rows:
                continue
            headers = [c.get_text(' ', strip=True).casefold() for c in rows[0].find_all(['th', 'td'])]
            for index, header in enumerate(headers):
                if 'tình trạng ban đầu' in header:
                    cells = rows[1].find_all(['th', 'td'])
                    if index < len(cells):
                        initial_status = cells[index].get_text(' ', strip=True)
                    break
            if initial_status:
                break
            # Actual Checklist alerts can contain only the data row; in that
            # format the fifth cell is "Tình trạng ban đầu".
            if len(rows) == 1:
                cells = rows[0].find_all(['th', 'td'])
                if len(cells) >= 5:
                    initial_status = cells[4].get_text(' ', strip=True)
                    break
    return {
        'msg_uid': f'CLL:{folder}:{uid_str}', 'folder': folder, 'subject': subject,
        'email_date': msg_date, 'timestamp_val': timestamp_val,
        'from_sender': decode_mime(msg.get('From')),
        'contract': contract_match.group(1).strip() if contract_match else '',
        'occurrence_count': int(count_match.group(1)) if count_match else 0,
        'initial_status': initial_status,
        'raw_html': html_content or f'<pre>{text_content}</pre>', 'raw_bytes': raw_bytes,
    }

def sync_mailbox(user=None, password=None, host=None, port=None, folders=None):
    mail_user = user or database.get_setting("mail_user", DEFAULT_EMAIL)
    mail_pass = password or database.get_setting("mail_pass", DEFAULT_PASSWORD)
    mail_host = host or database.get_setting("mail_host", DEFAULT_IMAP_SERVER)
    mail_port = port or int(database.get_setting("mail_port", DEFAULT_IMAP_PORT))
    
    target_folders = folders or SYNC_FOLDERS

    database.init_db()
    
    scanned_count = 0
    added_cem = 0
    added_giuc = 0
    added_cll = 0
    errors = []

    try:
        mail = imaplib.IMAP4_SSL(mail_host, mail_port)
        mail.login(mail_user, mail_pass)
    except Exception as e:
        err_msg = f"Đăng nhập thất bại: {str(e)}"
        database.log_sync("ERROR", 0, 0, err_msg)
        return {"success": False, "error": err_msg}

    for folder in target_folders:
        try:
            res, _ = mail.select(f'"{folder}"', readonly=True)
            if res != 'OK':
                continue
            
            # --- 1. IMAP search for CEM - CSAT 1, 2 CLDV ---
            res, ids = mail.uid('search', None, 'SUBJECT "CEM"')
            uids = ids[0].split() if ids and ids[0] else []
            res2, ids2 = mail.uid('search', None, 'SUBJECT "CSAT 1, 2 CLDV"')
            uids2 = ids2[0].split() if ids2 and ids2[0] else []
            cem_uids = list(dict.fromkeys(uids + uids2))
            scanned_count += len(cem_uids)

            for uid_bytes in cem_uids:
                uid_str = uid_bytes.decode('utf-8', errors='ignore')
                res, data = mail.uid('fetch', uid_bytes, '(RFC822)')
                if not data or not data[0]:
                    continue
                raw_bytes = data[0][1]
                msg = email.message_from_bytes(raw_bytes)
                subj = decode_mime(msg.get('Subject'))
                clean_subj = re.sub(r'^(RE:\s*|FW:\s*|FWD:\s*)+', '', subj, flags=re.IGNORECASE).strip()
                if "CEM - CSAT 1, 2 CLDV" in subj.upper() or "CSAT 1, 2 CLDV" in clean_subj.upper():
                    mdate = msg.get('Date', '')
                    record = parse_cem_email(raw_bytes, subj, mdate, folder, uid_str)
                    if database.save_email_record(record):
                        added_cem += 1

            # --- 2. IMAP search for Giục tiến độ ([SOC - SR] ... KH có yêu cầu Giục tiến độ) ---
            res_giuc, ids_giuc = mail.uid('search', None, 'SUBJECT "SOC - SR"')
            giuc_uids = ids_giuc[0].split() if ids_giuc and ids_giuc[0] else []
            scanned_count += len(giuc_uids)

            for uid_bytes in giuc_uids:
                uid_str = uid_bytes.decode('utf-8', errors='ignore')
                res, data = mail.uid('fetch', uid_bytes, '(RFC822)')
                if not data or not data[0]:
                    continue
                raw_bytes = data[0][1]
                msg = email.message_from_bytes(raw_bytes)
                subj = decode_mime(msg.get('Subject'))
                if "GIỤC TIẾN ĐỘ" in subj.upper() or "GIUC TIEN DO" in subj.upper() or "TIẾN ĐỘ" in subj.upper():
                    mdate = msg.get('Date', '')
                    g_record = parse_giuc_tien_do_email(raw_bytes, subj, mdate, folder, uid_str)
                    if database.save_giuc_tien_do_record(g_record):
                        added_giuc += 1

            # --- 3. CLL >3: Checklist Bảo trì alerts ---
            res_cll, ids_cll = mail.uid('search', None, 'SUBJECT "Checklist"')
            cll_uids = ids_cll[0].split() if ids_cll and ids_cll[0] else []
            scanned_count += len(cll_uids)
            for uid_bytes in cll_uids:
                uid_str = uid_bytes.decode('utf-8', errors='ignore')
                res, data = mail.uid('fetch', uid_bytes, '(RFC822)')
                if not data or not data[0]:
                    continue
                raw_bytes = data[0][1]
                msg = email.message_from_bytes(raw_bytes)
                subj = decode_mime(msg.get('Subject'))
                if re.search(r'Checklist\s*Bảo\s+trì\s*[–-]', subj, re.IGNORECASE):
                    record = parse_cll_email(raw_bytes, subj, msg.get('Date', ''), folder, uid_str)
                    if record['contract'] and record['occurrence_count'] >= 3:
                        try:
                            record['staff'] = supabase_service.get_staff_for_contract(record['contract'], record.get('timestamp_val'))
                        except Exception:
                            pass
                        if database.save_cll_record(record):
                            added_cll += 1
                        
        except Exception as e:
            errors.append(f"Lỗi thư mục {folder}: {str(e)}")

    try:
        mail.logout()
    except Exception:
        pass

    total_added = added_cem + added_giuc + added_cll
    msg = f"Đồng bộ hoàn tất: Đã quét {scanned_count} mail. Lưu {added_cem} CEM, {added_giuc} Giục tiến độ và {added_cll} CLL >3 (nén zstandard)."
    if errors:
        msg += f" (Ghi nhận {len(errors)} cảnh báo)"
    database.log_sync("SUCCESS", scanned_count, total_added, msg)

    return {
        "success": True,
        "scanned": scanned_count,
        "added": total_added,
        "added_cem": added_cem,
        "added_giuc": added_giuc,
        "added_cll": added_cll,
        "message": msg,
        "errors": errors
    }

import threading
import time

_auto_sync_thread = None
_auto_sync_running = False

def _auto_sync_loop(interval_seconds=300):
    global _auto_sync_running
    print(f"[Auto-Sync] Bắt đầu tiến trình tự động đồng bộ mail định kỳ ({interval_seconds}s / lần)...")
    while _auto_sync_running:
        try:
            print(f"[Auto-Sync] Đang tự động quét mail mới từ mail.fpt.net...")
            res = sync_mailbox()
            print(f"[Auto-Sync] Kết quả: {res.get('message')}")
        except Exception as e:
            print(f"[Auto-Sync Lỗi] {e}")
        
        # Sleep for interval in small increments so we can exit cleanly
        for _ in range(int(interval_seconds)):
            if not _auto_sync_running:
                break
            time.sleep(1)

def start_auto_sync(interval_seconds=300):
    global _auto_sync_thread, _auto_sync_running
    if _auto_sync_thread and _auto_sync_thread.is_alive():
        return
    _auto_sync_running = True
    _auto_sync_thread = threading.Thread(target=_auto_sync_loop, args=(interval_seconds,), daemon=True)
    _auto_sync_thread.start()
