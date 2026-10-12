import os
import sys
from dotenv import load_dotenv

load_dotenv()
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import json
import io
import threading
from datetime import datetime
from datetime import timedelta
from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
import pandas as pd
import database
import email_service
import supabase_service
import nhansu_service
import auth_service
from config import DEFAULT_EMAIL, DEFAULT_IMAP_SERVER, DEFAULT_IMAP_PORT, SYNC_FOLDERS

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('SECRET_KEY', 'fpt-sg01-cem-dashboard-secret-2026')
app.permanent_session_lifetime = timedelta(days=7)
database.init_db()
auth_service.init_auth_table()

# -----------------------------------------------------------------
# AUTH: bat buoc dang nhap
# -----------------------------------------------------------------
_PUBLIC_ENDPOINTS = {'login_page', 'auth_check', 'auth_login', 'auth_register', 'static'}

@app.before_request
def _require_login():
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return None
    if session.get('user'):
        if session['user'] != auth_service.ADMIN_USER:
            session['is_admin'] = auth_service.get_role(session['user']) == 'ADMIN'
        admin_only = request.path.startswith('/api/admin') or (
            request.path.startswith('/api/nhansu') and request.path != '/api/nhansu/meta')
        if admin_only:
            if not session.get('is_admin'):
                return jsonify({"success": False, "error": "Chỉ Admin mới có quyền truy cập"}), 403
        return None
    if request.path.startswith('/api/'):
        return jsonify({"success": False, "error": "Chưa đăng nhập"}), 401
    return redirect(url_for('login_page'))

@app.route('/login')
def login_page():
    if session.get('user'):
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/api/auth/check', methods=['POST'])
def auth_check():
    """Buoc 1: kiem tra email. Tra ve status: admin | login | register."""
    username = ((request.get_json() or {}).get('username') or '').strip()
    if not username:
        return jsonify({"success": False, "error": "Vui lòng nhập Email"}), 400
    if username.lower() == auth_service.ADMIN_USER:
        return jsonify({"success": True, "status": "admin", "name": "Administrator"})
    hr = auth_service.find_hr_by_email(username)
    is_adm = auth_service.is_admin_email(username)
    if not hr and not is_adm:
        return jsonify({"success": False, "error": "Email không có trong danh sách Nhân Sự"}), 404
    name = nhansu_service.get_nv_name(hr) if hr else username
    status = "login" if auth_service.get_user(username) else "register"
    return jsonify({"success": True, "status": status, "name": name, "is_admin": is_adm})

def _set_session(user, name, is_admin):
    session.permanent = True
    session['user'] = user
    session['name'] = name
    session['is_admin'] = is_admin

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if username.lower() == auth_service.ADMIN_USER:
        if password == auth_service.ADMIN_PASS:
            _set_session('admin', 'Administrator', True)
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Sai mật khẩu"}), 401
    hr = auth_service.find_hr_by_email(username)
    is_adm = auth_service.is_admin_email(username)
    user = auth_service.get_user(username)
    if (not hr and not is_adm) or not user:
        return jsonify({"success": False, "error": "Tài khoản không hợp lệ"}), 401
    if user['password'] != password:
        return jsonify({"success": False, "error": "Sai mật khẩu"}), 401
    auth_service.touch_login(username)
    _set_session(user['username'], nhansu_service.get_nv_name(hr) if hr else username,
                 auth_service.get_role(username) == 'ADMIN')
    return jsonify({"success": True})

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    hr = auth_service.find_hr_by_email(username)
    is_adm = auth_service.is_admin_email(username)
    if not hr and not is_adm:
        return jsonify({"success": False, "error": "Email không có trong danh sách Nhân Sự"}), 404
    if auth_service.get_user(username):
        return jsonify({"success": False, "error": "Tài khoản đã tồn tại"}), 409
    if len(password) < 6:
        return jsonify({"success": False, "error": "Mật khẩu tối thiểu 6 ký tự"}), 400
    auth_service.register_user(username, password)
    _set_session(username.lower(), nhansu_service.get_nv_name(hr) if hr else username, is_adm)
    return jsonify({"success": True})

@app.route('/api/auth/me')
def auth_me():
    return jsonify({"success": True, "user": session.get('user'), "name": session.get('name'),
                    "is_admin": bool(session.get('is_admin'))})

# -----------------------------------------------------------------
# ADMIN: Danh sach Login
# -----------------------------------------------------------------
@app.route('/api/admin/logins')
def admin_list_logins():
    return jsonify({"success": True, "data": auth_service.list_users()})

@app.route('/api/admin/logins/<int:user_id>', methods=['PUT'])
def admin_update_login(user_id):
    password = (request.get_json() or {}).get('password') or ''
    if len(password) < 6:
        return jsonify({"success": False, "error": "Mật khẩu tối thiểu 6 ký tự"}), 400
    auth_service.update_password(user_id, password)
    return jsonify({"success": True})

@app.route('/api/admin/logins/<int:user_id>/role', methods=['PUT'])
def admin_update_role(user_id):
    role = ((request.get_json() or {}).get('role') or '').upper()
    if role not in ('USER', 'ADMIN'):
        return jsonify({"success": False, "error": "Quyền không hợp lệ"}), 400
    auth_service.set_role(user_id, role)
    return jsonify({"success": True})

@app.route('/api/admin/logins/<int:user_id>', methods=['DELETE'])
def admin_delete_login(user_id):
    auth_service.delete_user(user_id)
    return jsonify({"success": True})

# Start background sync to backfill any missing CLL staff from Supabase
if not os.getenv("VERCEL"):
    threading.Thread(target=supabase_service.sync_missing_cll_staff, daemon=True).start()

def _apply_cem_ns_filter(conditions, params, block, doi_truong):
    if not block and not doi_truong:
        return
    matched_insides, matched_names = nhansu_service.get_matching_identifiers(block=block, doi_truong=doi_truong)
    if not matched_insides and not matched_names:
        conditions.append("1 = 0")
        return
    targets = list(matched_insides) + [n.upper() for n in matched_names]
    placeholders = ",".join(["?"] * len(targets))
    conditions.append(f"UPPER(technician) IN ({placeholders})")
    params.extend([t.upper() for t in targets])

def _apply_giuc_ns_filter(conditions, params, block, doi_truong):
    if not block and not doi_truong:
        return
    matched_insides, matched_names = nhansu_service.get_matching_identifiers(block=block, doi_truong=doi_truong)
    if not matched_insides and not matched_names:
        conditions.append("1 = 0")
        return
    targets = list(matched_names) + [i.lower() for i in matched_insides]
    placeholders = ",".join(["?"] * len(targets))
    conditions.append(f"LOWER(assignee) IN ({placeholders})")
    params.extend([t.lower() for t in targets])

def _enrich_cem_rows(rows):
    for r in rows:
        tech = r.get('technician', '')
        info = nhansu_service.find_employee_info(tech)
        if info:
            r['ns_nv_name'] = info.get('name', '')
            r['ns_block'] = info.get('block', '')
            r['ns_doi_truong'] = info.get('doi_truong', '')
            r['ns_inside'] = info.get('inside', '')
            r['ns_ma_nv'] = info.get('ma_nv', '')
        else:
            r['ns_nv_name'] = ''
            r['ns_block'] = ''
            r['ns_doi_truong'] = ''
            r['ns_inside'] = ''
            r['ns_ma_nv'] = ''
    return rows

def _enrich_giuc_rows(rows):
    for r in rows:
        assignee = r.get('assignee', '')
        info = nhansu_service.find_employee_info(assignee)
        if info:
            r['ns_nv_name'] = info.get('name', '')
            r['ns_block'] = info.get('block', '')
            r['ns_doi_truong'] = info.get('doi_truong', '')
            r['ns_inside'] = info.get('inside', '')
            r['ns_ma_nv'] = info.get('ma_nv', '')
        else:
            r['ns_nv_name'] = ''
            r['ns_block'] = ''
            r['ns_doi_truong'] = ''
            r['ns_inside'] = ''
            r['ns_ma_nv'] = ''
    return rows

def _apply_cll_ns_filter(conditions, params, block, doi_truong):
    if not block and not doi_truong:
        return
    matched_insides, matched_names = nhansu_service.get_matching_identifiers(block=block, doi_truong=doi_truong)
    if not matched_insides and not matched_names:
        conditions.append("1 = 0")
        return
    targets = list(matched_insides) + [n.upper() for n in matched_names]
    placeholders = ",".join(["?"] * len(targets))
    conditions.append(f"UPPER(COALESCE(staff, '')) IN ({placeholders})")
    params.extend([t.upper() for t in targets])

def _enrich_cll_rows(rows):
    for r in rows:
        staff = r.get('staff', '')
        info = nhansu_service.find_employee_info(staff)
        if info:
            r['ns_nv_name'] = info.get('name', '')
            r['ns_block'] = info.get('block', '')
            r['ns_doi_truong'] = info.get('doi_truong', '')
            r['ns_inside'] = info.get('inside', '')
            r['ns_ma_nv'] = info.get('ma_nv', '')
        else:
            r['ns_nv_name'] = ''
            r['ns_block'] = ''
            r['ns_doi_truong'] = ''
            r['ns_inside'] = staff or ''
            r['ns_ma_nv'] = ''
    return rows

@app.route('/')
def index():
    return render_template('index.html', user=session.get('user'), user_name=session.get('name'),
                           is_admin=bool(session.get('is_admin')))

@app.route('/api/stats')
def get_stats():
    conn = database.get_connection()
    cursor = conn.cursor()

    only_survey = request.args.get('only_survey', 'true') == 'true'
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    block = request.args.get('block', '').strip()
    doi_truong = request.args.get('doi_truong', '').strip()

    conditions = []
    params = []

    if only_survey:
        conditions.append("csat_score IS NOT NULL")
    
    if date_from:
        conditions.append("(eval_time >= ? OR (eval_time = '' AND SUBSTR(created_at, 1, 10) >= ?))")
        params.extend([f"{date_from} 00:00:00", date_from])

    if date_to:
        conditions.append("(eval_time <= ? OR (eval_time = '' AND SUBSTR(created_at, 1, 10) <= ?))")
        params.extend([f"{date_to} 23:59:59", date_to])

    _apply_cem_ns_filter(conditions, params, block, doi_truong)

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else "WHERE 1=1"

    # Overall counters
    cursor.execute(f"SELECT COUNT(*) FROM cem_emails {where_clause}", params)
    total_records = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM cem_emails {where_clause} AND csat_score = 1", params)
    total_csat_1 = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM cem_emails {where_clause} AND csat_score = 2", params)
    total_csat_2 = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(DISTINCT technician) FROM cem_emails {where_clause} AND technician != ''", params)
    total_techs = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(DISTINCT contract) FROM cem_emails {where_clause} AND contract != ''", params)
    total_contracts = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM cem_emails {where_clause} AND (home_support LIKE '%có%' OR home_support LIKE '%yes%' OR home_support = '1')", params)
    total_home_support = cursor.fetchone()[0]

    # Top Technicians
    cursor.execute(f"""
        SELECT technician, COUNT(*) as count,
               SUM(CASE WHEN csat_score = 1 THEN 1 ELSE 0 END) as csat1_cnt,
               SUM(CASE WHEN csat_score = 2 THEN 1 ELSE 0 END) as csat2_cnt
        FROM cem_emails
        {where_clause} AND technician != ''
        GROUP BY technician
        ORDER BY count DESC
        LIMIT 10
    """, params)
    top_techs = [dict(r) for r in cursor.fetchall()]

    # Top Issues
    cursor.execute(f"""
        SELECT issue_group, COUNT(*) as count
        FROM cem_emails
        {where_clause} AND issue_group != ''
        GROUP BY issue_group
        ORDER BY count DESC
        LIMIT 10
    """, params)
    top_issues = [dict(r) for r in cursor.fetchall()]

    # District Distribution
    cursor.execute(f"""
        SELECT district, COUNT(*) as count
        FROM cem_emails
        {where_clause} AND district != ''
        GROUP BY district
        ORDER BY count DESC
        LIMIT 10
    """, params)
    top_districts = [dict(r) for r in cursor.fetchall()]

    # Timeline (by eval_date or email_date)
    cursor.execute(f"""
        SELECT 
            CASE 
                WHEN eval_time != '' THEN SUBSTR(eval_time, 1, 10)
                ELSE SUBSTR(created_at, 1, 10)
            END as date_key,
            COUNT(*) as count,
            SUM(CASE WHEN csat_score = 1 THEN 1 ELSE 0 END) as csat1_cnt,
            SUM(CASE WHEN csat_score = 2 THEN 1 ELSE 0 END) as csat2_cnt
        FROM cem_emails
        {where_clause}
        GROUP BY date_key
        ORDER BY date_key ASC
        LIMIT 30
    """, params)
    timeline = [dict(r) for r in cursor.fetchall()]

    last_sync = database.get_last_sync()

    conn.close()

    return jsonify({
        "success": True,
        "kpi": {
            "total_records": total_records,
            "total_csat_1": total_csat_1,
            "total_csat_2": total_csat_2,
            "total_techs": total_techs,
            "total_contracts": total_contracts,
            "total_home_support": total_home_support
        },
        "top_techs": top_techs,
        "top_issues": top_issues,
        "top_districts": top_districts,
        "timeline": timeline,
        "last_sync": last_sync
    })

@app.route('/api/emails')
def get_emails():
    search = request.args.get('search', '').strip()
    csat_filter = request.args.get('csat', '').strip()
    tech_filter = request.args.get('technician', '').strip()
    issue_filter = request.args.get('issue', '').strip()
    only_survey = request.args.get('only_survey', 'false') == 'true'
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    block = request.args.get('block', '').strip()
    doi_truong = request.args.get('doi_truong', '').strip()
    
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 25))
    offset = (page - 1) * limit

    conditions = []
    params = []

    if only_survey:
        conditions.append("csat_score IS NOT NULL")

    if csat_filter:
        conditions.append("csat_score = ?")
        params.append(int(csat_filter))

    if tech_filter:
        conditions.append("technician LIKE ?")
        params.append(f"%{tech_filter}%")

    if issue_filter:
        conditions.append("issue_group LIKE ?")
        params.append(f"%{issue_filter}%")

    if date_from:
        conditions.append("eval_time >= ?")
        params.append(f"{date_from} 00:00:00")

    if date_to:
        conditions.append("eval_time <= ?")
        params.append(f"{date_to} 23:59:59")

    _apply_cem_ns_filter(conditions, params, block, doi_truong)

    if search:
        search_pattern = f"%{search}%"
        conditions.append("""(
            contract LIKE ? OR 
            customer_name LIKE ? OR 
            phone LIKE ? OR 
            technician LIKE ? OR 
            issue_group LIKE ? OR 
            address LIKE ? OR 
            subject LIKE ?
        )""")
        params.extend([search_pattern] * 7)

    where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""

    conn = database.get_connection()
    cursor = conn.cursor()

    # Total count
    cursor.execute(f"SELECT COUNT(*) FROM cem_emails {where_sql}", params)
    total_count = cursor.fetchone()[0]

    # Records
    cursor.execute(f"""
        SELECT id, msg_uid, folder, subject, email_date, timestamp_val, from_sender,
               contract, customer_name, phone, address, district, eval_type, channel,
               eval_time, completed_time, technician, csat_score, issue_group,
               notes, home_support, is_reply, created_at
        FROM cem_emails
        {where_sql}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset])

    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    rows = _enrich_cem_rows(rows)

    return jsonify({
        "success": True,
        "total": total_count,
        "page": page,
        "limit": limit,
        "data": rows
    })

@app.route('/api/email/<int:email_id>')
def get_email_detail(email_id):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cem_emails WHERE id = ?", (email_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({"success": False, "error": "Email không tồn tại"}), 404
    d = dict(row)
    if 'raw_zstd' in d:
        if not d.get('raw_html') and d['raw_zstd']:
            d['raw_html'] = database.decompress_bytes(d['raw_zstd'])
        del d['raw_zstd']
    tech = d.get('technician', '')
    info = nhansu_service.find_employee_info(tech)
    if info:
        d['ns_nv_name'] = info.get('name', '')
        d['ns_block'] = info.get('block', '')
        d['ns_doi_truong'] = info.get('doi_truong', '')
        d['ns_inside'] = info.get('inside', '')
        d['ns_ma_nv'] = info.get('ma_nv', '')
    return jsonify({"success": True, "data": d})

@app.route('/api/sync', methods=['POST'])
def trigger_sync():
    data = request.get_json() or {}
    user = data.get('email')
    password = data.get('password')
    host = data.get('host')
    folders = data.get('folders')
    
    result = email_service.sync_mailbox(user=user, password=password, host=host, folders=folders)
    return jsonify(result)

@app.route('/api/export/excel')
def export_excel():
    search = request.args.get('search', '').strip()
    csat_filter = request.args.get('csat', '').strip()
    only_survey = request.args.get('only_survey', 'false') == 'true'
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    block = request.args.get('block', '').strip()
    doi_truong = request.args.get('doi_truong', '').strip()

    conditions = []
    params = []

    if only_survey:
        conditions.append("csat_score IS NOT NULL")
    if csat_filter:
        conditions.append("csat_score = ?")
        params.append(int(csat_filter))
    if date_from:
        conditions.append("(eval_time >= ? OR (eval_time = '' AND SUBSTR(created_at, 1, 10) >= ?))")
        params.extend([f"{date_from} 00:00:00", date_from])
    if date_to:
        conditions.append("(eval_time <= ? OR (eval_time = '' AND SUBSTR(created_at, 1, 10) <= ?))")
        params.extend([f"{date_to} 23:59:59", date_to])
    
    _apply_cem_ns_filter(conditions, params, block, doi_truong)

    if search:
        search_pattern = f"%{search}%"
        conditions.append("(contract LIKE ? OR customer_name LIKE ? OR phone LIKE ? OR technician LIKE ? OR issue_group LIKE ?)")
        params.extend([search_pattern] * 5)

    where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""

    conn = database.get_connection()
    df = pd.read_sql_query(f"""
        SELECT 
            id as [STT],
            contract as [Số hợp đồng],
            customer_name as [Tên khách hàng],
            phone as [Số điện thoại],
            csat_score as [Điểm CSAT],
            technician as [NVKT (Inside)],
            issue_group as [Nhóm lỗi phản ánh],
            notes as [Ghi chú],
            home_support as [Hỗ trợ tại nhà],
            eval_time as [Thời gian đánh giá],
            completed_time as [Hoàn tất bảo trì],
            channel as [Kênh ghi nhận],
            address as [Địa chỉ],
            subject as [Tiêu đề email],
            folder as [Thư mục]
        FROM cem_emails
        {where_sql}
        ORDER BY id DESC
    """, conn, params=params)
    conn.close()

    # Link with Nhan Su for Block and Doi Truong
    inside_map, name_map = nhansu_service.get_employee_lookup()
    df.insert(6, 'Họ tên KTV', df['NVKT (Inside)'].apply(lambda x: inside_map.get(str(x).strip().upper(), {}).get('name', '')))
    df.insert(7, 'Block', df['NVKT (Inside)'].apply(lambda x: inside_map.get(str(x).strip().upper(), {}).get('block', '')))
    df.insert(8, 'Đội trưởng', df['NVKT (Inside)'].apply(lambda x: inside_map.get(str(x).strip().upper(), {}).get('doi_truong', '')))

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='CEM_CSAT')
        # Auto-adjust column widths
        worksheet = writer.sheets['CEM_CSAT']
        for col in worksheet.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = col[0].column_letter
            worksheet.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 45)

    output.seek(0)
    filename = f"CEM_CSAT_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route('/api/export/csv')
def export_csv():
    search = request.args.get('search', '').strip()
    csat_filter = request.args.get('csat', '').strip()
    only_survey = request.args.get('only_survey', 'false') == 'true'
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    block = request.args.get('block', '').strip()
    doi_truong = request.args.get('doi_truong', '').strip()

    conditions = []
    params = []

    if only_survey:
        conditions.append("csat_score IS NOT NULL")
    if csat_filter:
        conditions.append("csat_score = ?")
        params.append(int(csat_filter))
    if date_from:
        conditions.append("(eval_time >= ? OR (eval_time = '' AND SUBSTR(created_at, 1, 10) >= ?))")
        params.extend([f"{date_from} 00:00:00", date_from])
    if date_to:
        conditions.append("(eval_time <= ? OR (eval_time = '' AND SUBSTR(created_at, 1, 10) <= ?))")
        params.extend([f"{date_to} 23:59:59", date_to])
    
    _apply_cem_ns_filter(conditions, params, block, doi_truong)

    if search:
        search_pattern = f"%{search}%"
        conditions.append("(contract LIKE ? OR customer_name LIKE ? OR phone LIKE ? OR technician LIKE ? OR issue_group LIKE ?)")
        params.extend([search_pattern] * 5)

    where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""

    conn = database.get_connection()
    df = pd.read_sql_query(f"""
        SELECT 
            contract as [Số hợp đồng],
            customer_name as [Tên khách hàng],
            phone as [Số điện thoại],
            csat_score as [Điểm CSAT],
            technician as [NVKT (Inside)],
            issue_group as [Nhóm lỗi phản ánh],
            notes as [Ghi chú],
            home_support as [Hỗ trợ tại nhà],
            eval_time as [Thời gian đánh giá],
            completed_time as [Hoàn tất bảo trì],
            channel as [Kênh ghi nhận],
            address as [Địa chỉ],
            subject as [Tiêu đề email]
        FROM cem_emails
        {where_sql}
        ORDER BY id DESC
    """, conn, params=params)
    conn.close()

    inside_map, name_map = nhansu_service.get_employee_lookup()
    df.insert(5, 'Họ tên KTV', df['NVKT (Inside)'].apply(lambda x: inside_map.get(str(x).strip().upper(), {}).get('name', '')))
    df.insert(6, 'Block', df['NVKT (Inside)'].apply(lambda x: inside_map.get(str(x).strip().upper(), {}).get('block', '')))
    df.insert(7, 'Đội trưởng', df['NVKT (Inside)'].apply(lambda x: inside_map.get(str(x).strip().upper(), {}).get('doi_truong', '')))

    output = io.StringIO()
    df.to_csv(output, index=False, encoding='utf-8-sig')
    mem = io.BytesIO(output.getvalue().encode('utf-8-sig'))
    filename = f"CEM_CSAT_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return send_file(
        mem,
        as_attachment=True,
        download_name=filename,
        mimetype="text/csv"
    )

@app.route('/api/metadata')
def get_metadata():
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT technician FROM cem_emails WHERE technician != '' ORDER BY technician")
    techs = [r[0] for r in cursor.fetchall()]
    cursor.execute("SELECT DISTINCT issue_group FROM cem_emails WHERE issue_group != '' ORDER BY issue_group")
    issues = [r[0] for r in cursor.fetchall()]
    cursor.execute("SELECT COUNT(*) FROM cem_emails WHERE csat_score IS NOT NULL")
    cem_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM giuc_tien_do_emails")
    giuc_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM cll_emails")
    cll_cnt = cursor.fetchone()[0]
    conn.close()
    return jsonify({
        "technicians": techs,
        "issue_groups": issues,
        "cem_count": cem_cnt,
        "giuc_count": giuc_cnt,
        "cll_count": cll_cnt,
        "default_email": DEFAULT_EMAIL,
        "default_host": DEFAULT_IMAP_SERVER,
        "default_port": DEFAULT_IMAP_PORT
    })

# -----------------------------------------------------------------
# API: CLL >3 (Checklist Bảo trì phát sinh từ 3 lần trong 30 ngày)
# -----------------------------------------------------------------
CLL_DATE_EXPR = """date(timestamp_val, 'unixepoch', 'localtime')"""

def _cll_conditions():
    search = request.args.get('search', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    block = request.args.get('block', '').strip()
    doi_truong = request.args.get('doi_truong', '').strip()
    conditions, params = [], []
    if date_from:
        conditions.append(f"({CLL_DATE_EXPR}) >= ?")
        params.append(date_from)
    if date_to:
        conditions.append(f"({CLL_DATE_EXPR}) <= ?")
        params.append(date_to)
    if search:
        conditions.append("(contract LIKE ? OR initial_status LIKE ? OR subject LIKE ? OR staff LIKE ?)")
        params.extend([f"%{search}%"] * 4)
    _apply_cll_ns_filter(conditions, params, block, doi_truong)
    return ("WHERE " + " AND ".join(conditions)) if conditions else "", params

@app.route('/api/cll/stats')
def get_cll_stats():
    where_sql, params = _cll_conditions()
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM cll_emails {where_sql}", params)
    total = cursor.fetchone()[0]
    cursor.execute(f"SELECT COUNT(DISTINCT contract) FROM cll_emails {where_sql}", params)
    contracts = cursor.fetchone()[0]
    cursor.execute(f"SELECT COALESCE(MAX(occurrence_count), 0) FROM cll_emails {where_sql}", params)
    max_occurrences = cursor.fetchone()[0]
    conn.close()
    return jsonify({"success": True, "kpi": {"total": total, "contracts": contracts, "max_occurrences": max_occurrences}})

@app.route('/api/cll')
def get_cll():
    page = max(int(request.args.get('page', 1)), 1)
    limit = min(max(int(request.args.get('limit', 15)), 1), 100)
    where_sql, params = _cll_conditions()
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM cll_emails {where_sql}", params)
    total = cursor.fetchone()[0]
    cursor.execute(f"""
        SELECT id, subject, email_date, timestamp_val, from_sender, contract,
               occurrence_count, initial_status, staff
        FROM cll_emails {where_sql}
        ORDER BY timestamp_val DESC, id DESC LIMIT ? OFFSET ?
    """, params + [limit, (page - 1) * limit])
    records = [dict(row) for row in cursor.fetchall()]
    conn.close()
    records = _enrich_cll_rows(records)
    return jsonify({"success": True, "total": total, "page": page, "limit": limit, "records": records})

@app.route('/api/cll/<int:item_id>')
def get_cll_detail(item_id):
    conn = database.get_connection()
    row = conn.execute("SELECT * FROM cll_emails WHERE id = ?", (item_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"success": False, "error": "Bản ghi không tồn tại"}), 404
    record = dict(row)
    if not record.get('raw_html') and record.get('raw_zstd'):
        record['raw_html'] = database.decompress_bytes(record['raw_zstd'])
    record.pop('raw_zstd', None)
    try:
        record['occurrences'] = supabase_service.get_bt_occurrences(
            record['contract'], record['timestamp_val'], record['occurrence_count'])
        if record['occurrences'] and not record.get('staff'):
            latest_staff = record['occurrences'][0].get('staff')
            if latest_staff:
                record['staff'] = latest_staff
                database.update_cll_staff(item_id, latest_staff)
    except Exception as exc:
        return jsonify({"success": False, "error": f"Không thể đọc Supabase: {exc}", "record": record}), 502
    _enrich_cll_rows([record])
    return jsonify({"success": True, "record": record})

# -----------------------------------------------------------------
# API: Giục tiến độ (Service Request: KH có yêu cầu Giục tiến độ)
# -----------------------------------------------------------------
REQ_DATE_EXPR = """date(timestamp_val, 'unixepoch', 'localtime')"""

@app.route('/api/giuc-tien-do/stats')
def get_giuc_tien_do_stats():
    search = request.args.get('search', '').strip()
    priority = request.args.get('priority', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    block = request.args.get('block', '').strip()
    doi_truong = request.args.get('doi_truong', '').strip()

    conditions = []
    params = []

    if priority:
        conditions.append("priority LIKE ?")
        params.append(f"%{priority}%")
    if date_from:
        conditions.append(f"({REQ_DATE_EXPR}) >= ?")
        params.append(date_from)
    if date_to:
        conditions.append(f"({REQ_DATE_EXPR}) <= ?")
        params.append(date_to)
    if search:
        search_pattern = f"%{search}%"
        conditions.append("(contract LIKE ? OR assignee LIKE ? OR sr_ticket LIKE ? OR request_content LIKE ?)")
        params.extend([search_pattern] * 4)

    _apply_giuc_ns_filter(conditions, params, block, doi_truong)

    where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""

    conn = database.get_connection()
    cursor = conn.cursor()

    cursor.execute(f"SELECT COUNT(*) FROM giuc_tien_do_emails {where_sql}", params)
    total = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM giuc_tien_do_emails {where_sql} {'AND' if where_sql else 'WHERE'} priority LIKE '%Khẩn%'", params)
    khan_cnt = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM giuc_tien_do_emails {where_sql} {'AND' if where_sql else 'WHERE'} priority LIKE '%Cao%'", params)
    cao_cnt = cursor.fetchone()[0]
    urgent_cnt = khan_cnt + cao_cnt

    cursor.execute(f"SELECT COUNT(*) FROM giuc_tien_do_emails {where_sql} {'AND' if where_sql else 'WHERE'} priority LIKE '%Bình thường%'", params)
    normal_cnt = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(DISTINCT assignee) FROM giuc_tien_do_emails {where_sql} {'AND' if where_sql else 'WHERE'} assignee != ''", params)
    assignees_cnt = cursor.fetchone()[0]

    # Top assignees
    cursor.execute(f"""
        SELECT assignee, COUNT(*) as count
        FROM giuc_tien_do_emails
        {where_sql} {'AND' if where_sql else 'WHERE'} assignee != ''
        GROUP BY assignee
        ORDER BY count DESC
        LIMIT 10
    """, params)
    top_assignees = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return jsonify({
        "success": True,
        "kpi": {
            "total": total,
            "urgent": urgent_cnt,
            "total_khan": khan_cnt,
            "total_cao": cao_cnt,
            "normal": normal_cnt,
            "assignees": assignees_cnt,
            "total_records": total,
            "total_urgent": urgent_cnt,
            "total_normal": normal_cnt,
            "total_assignees": assignees_cnt
        },
        "top_assignees": top_assignees
    })

@app.route('/api/giuc-tien-do')
def get_giuc_tien_do():
    search = request.args.get('search', '').strip()
    priority = request.args.get('priority', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    block = request.args.get('block', '').strip()
    doi_truong = request.args.get('doi_truong', '').strip()

    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 15))
    offset = (page - 1) * limit

    conditions = []
    params = []

    if priority:
        conditions.append("priority LIKE ?")
        params.append(f"%{priority}%")
    if date_from:
        conditions.append(f"({REQ_DATE_EXPR}) >= ?")
        params.append(date_from)
    if date_to:
        conditions.append(f"({REQ_DATE_EXPR}) <= ?")
        params.append(date_to)
    if search:
        search_pattern = f"%{search}%"
        conditions.append("(contract LIKE ? OR assignee LIKE ? OR sr_ticket LIKE ? OR request_content LIKE ?)")
        params.extend([search_pattern] * 4)

    _apply_giuc_ns_filter(conditions, params, block, doi_truong)

    where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""

    conn = database.get_connection()
    cursor = conn.cursor()

    cursor.execute(f"SELECT COUNT(*) FROM giuc_tien_do_emails {where_sql}", params)
    total_count = cursor.fetchone()[0]

    cursor.execute(f"""
        SELECT id, msg_uid, folder, subject, email_date, timestamp_val, from_sender,
               assignee, contract, sr_ticket, priority, request_content, request_time,
               created_at
        FROM giuc_tien_do_emails
        {where_sql}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset])

    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    rows = _enrich_giuc_rows(rows)

    return jsonify({
        "success": True,
        "total": total_count,
        "page": page,
        "limit": limit,
        "records": rows,
        "data": rows
    })

@app.route('/api/giuc-tien-do/<int:item_id>')
def get_giuc_tien_do_detail(item_id):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM giuc_tien_do_emails WHERE id = ?", (item_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({"success": False, "error": "Bản ghi không tồn tại"}), 404
    d = dict(row)
    if 'raw_zstd' in d:
        if not d.get('raw_html') and d['raw_zstd']:
            d['raw_html'] = database.decompress_bytes(d['raw_zstd'])
        del d['raw_zstd']
    assignee = d.get('assignee', '')
    info = nhansu_service.find_employee_info(assignee)
    if info:
        d['ns_nv_name'] = info.get('name', '')
        d['ns_block'] = info.get('block', '')
        d['ns_doi_truong'] = info.get('doi_truong', '')
        d['ns_inside'] = info.get('inside', '')
        d['ns_ma_nv'] = info.get('ma_nv', '')
    return jsonify({"success": True, "record": d, "data": d})

@app.route('/api/giuc-tien-do/export/excel')
def export_giuc_excel():
    search = request.args.get('search', '').strip()
    priority = request.args.get('priority', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    block = request.args.get('block', '').strip()
    doi_truong = request.args.get('doi_truong', '').strip()

    conditions = []
    params = []

    if priority:
        conditions.append("priority LIKE ?")
        params.append(f"%{priority}%")
    if date_from:
        conditions.append(f"({REQ_DATE_EXPR}) >= ?")
        params.append(date_from)
    if date_to:
        conditions.append(f"({REQ_DATE_EXPR}) <= ?")
        params.append(date_to)
    if search:
        search_pattern = f"%{search}%"
        conditions.append("(contract LIKE ? OR assignee LIKE ? OR sr_ticket LIKE ? OR request_content LIKE ?)")
        params.extend([search_pattern] * 4)

    _apply_giuc_ns_filter(conditions, params, block, doi_truong)

    where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""

    conn = database.get_connection()
    df = pd.read_sql_query(f"""
        SELECT 
            id as [STT],
            contract as [Số hợp đồng],
            sr_ticket as [Mã SR/Ticket],
            assignee as [Nhân viên xử lý],
            priority as [Độ ưu tiên],
            request_content as [Nội dung yêu cầu],
            request_time as [Thời gian gửi yêu cầu],
            subject as [Tiêu đề email],
            from_sender as [Người gửi]
        FROM giuc_tien_do_emails
        {where_sql}
        ORDER BY id DESC
    """, conn, params=params)
    conn.close()

    # Link with Nhan Su
    inside_map, name_map = nhansu_service.get_employee_lookup()
    df.insert(4, 'Inside Account', df['Nhân viên xử lý'].apply(lambda x: name_map.get(str(x).strip().lower(), {}).get('inside', '')))
    df.insert(5, 'Block', df['Nhân viên xử lý'].apply(lambda x: name_map.get(str(x).strip().lower(), {}).get('block', '')))
    df.insert(6, 'Đội trưởng', df['Nhân viên xử lý'].apply(lambda x: name_map.get(str(x).strip().lower(), {}).get('doi_truong', '')))

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Giuc_Tien_Do')
        worksheet = writer.sheets['Giuc_Tien_Do']
        for col in worksheet.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = col[0].column_letter
            worksheet.column_dimensions[col_letter].width = min(max(max_len + 3, 14), 50)

    output.seek(0)
    filename = f"Giuc_Tien_Do_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route('/api/giuc-tien-do/export/csv')
def export_giuc_csv():
    search = request.args.get('search', '').strip()
    priority = request.args.get('priority', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    block = request.args.get('block', '').strip()
    doi_truong = request.args.get('doi_truong', '').strip()

    conditions = []
    params = []

    if priority:
        conditions.append("priority LIKE ?")
        params.append(f"%{priority}%")
    if date_from:
        conditions.append(f"({REQ_DATE_EXPR}) >= ?")
        params.append(date_from)
    if date_to:
        conditions.append(f"({REQ_DATE_EXPR}) <= ?")
        params.append(date_to)
    if search:
        search_pattern = f"%{search}%"
        conditions.append("(contract LIKE ? OR assignee LIKE ? OR sr_ticket LIKE ? OR request_content LIKE ?)")
        params.extend([search_pattern] * 4)

    _apply_giuc_ns_filter(conditions, params, block, doi_truong)

    where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""

    conn = database.get_connection()
    df = pd.read_sql_query(f"""
        SELECT 
            contract as [Số hợp đồng],
            sr_ticket as [Mã SR/Ticket],
            assignee as [Nhân viên xử lý],
            priority as [Độ ưu tiên],
            request_content as [Nội dung yêu cầu],
            request_time as [Thời gian gửi yêu cầu]
        FROM giuc_tien_do_emails
        {where_sql}
        ORDER BY id DESC
    """, conn, params=params)
    conn.close()

    inside_map, name_map = nhansu_service.get_employee_lookup()
    df.insert(3, 'Inside Account', df['Nhân viên xử lý'].apply(lambda x: name_map.get(str(x).strip().lower(), {}).get('inside', '')))
    df.insert(4, 'Block', df['Nhân viên xử lý'].apply(lambda x: name_map.get(str(x).strip().lower(), {}).get('block', '')))
    df.insert(5, 'Đội trưởng', df['Nhân viên xử lý'].apply(lambda x: name_map.get(str(x).strip().lower(), {}).get('doi_truong', '')))

    output = io.StringIO()
    df.to_csv(output, index=False, encoding='utf-8-sig')
    mem = io.BytesIO(output.getvalue().encode('utf-8-sig'))
    filename = f"Giuc_Tien_Do_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return send_file(
        mem,
        as_attachment=True,
        download_name=filename,
        mimetype="text/csv"
    )

# -----------------------------------------------------------------
# API: NHÂN SỰ — Google Sheets Chi Nhánh Sài Gòn 01
# -----------------------------------------------------------------

@app.route('/api/nhansu/meta')
def nhansu_meta():
    """Tra ve danh sach Block va Doi Truong de hien thi bo loc."""
    try:
        rows = nhansu_service.get_cached_or_fetch()
        blocks = nhansu_service.get_blocks(rows)
        doi_truongs = nhansu_service.get_doi_truong_list(rows)
        return jsonify({
            "success": True,
            "blocks": blocks,
            "doi_truongs": doi_truongs,
            "total": len(rows)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/nhansu')
def get_nhansu():
    """Lay danh sach nhan su co phan trang va bo loc."""
    block      = request.args.get('block', '').strip()
    doi_truong = request.args.get('doi_truong', '').strip()
    search     = request.args.get('search', '').strip()
    page       = max(int(request.args.get('page', 1)), 1)
    limit      = min(max(int(request.args.get('limit', 20)), 1), 200)

    try:
        rows = nhansu_service.get_cached_or_fetch()
        filtered = nhansu_service.filter_rows(rows, block=block, doi_truong=doi_truong, search=search)
        total = len(filtered)
        offset = (page - 1) * limit
        page_rows = filtered[offset: offset + limit]

        # Chuyen thanh dict an toan (unicode)
        def safe_row(r):
            return {
                "nv":       nhansu_service.get_nv_name(r),
                "ma_nv":    nhansu_service.get_ma_nv(r),
                "block":    nhansu_service.get_block(r),
                "doi_truong": nhansu_service.get_doi_truong(r),
                "email":    nhansu_service.get_email(r),
                "chuc_danh":    r.get('Chức danh', r.get('Chuc danh', '')),
                "tt_hd":    r.get('Tình trạng Hợp đồng', r.get('Tinh trang Hop dong', '')),
                "tt_tk":    r.get('Tình trạng Tài khoản', r.get('Tinh trang Tai khoan', '')),
                "sdt":      r.get('Số điện thoại', r.get('So dien thoai', '')),
                "loai_hd":  r.get('Loại HĐLĐ', r.get('Loai HDLD', '')),
                "ngay_vao": r.get('Ngày Vô Công Ty', r.get('Ngay Vo Cong Ty', '')),
                "vung":     r.get('Vùng', r.get('Vung', '')),
                "doi_tac":  r.get('Đối tác', r.get('Doi tac', '')),
                "inside_account": r.get('Inside Account', ''),
                "sdt_frt":  r.get('Số điện thoại FRT', r.get('So dien thoai FRT', '')),
                "ma_dt":    r.get('Mã NV Đội trưởng', r.get('Ma NV Doi truong', '')),
            }

        return jsonify({
            "success": True,
            "total": total,
            "page": page,
            "limit": limit,
            "data": [safe_row(r) for r in page_rows]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/nhansu/refresh', methods=['POST'])
def nhansu_refresh():
    """Force refresh du lieu tu Google Sheets."""
    try:
        rows = nhansu_service.fetch_sheet_data()
        if rows:
            nhansu_service._save_cache(rows)
            nhansu_service._save_hash(nhansu_service._compute_hash(rows))
        return jsonify({"success": True, "total": len(rows), "message": f"Da tai lai {len(rows)} ban ghi."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/nhansu/send-mail', methods=['POST'])
def nhansu_send_mail():
    """Gui mail thu cong voi tieu de + noi dung hien tai."""
    data       = request.get_json() or {}
    subject    = data.get('subject', '[FPT Telecom - CN Sài Gòn 01] Thông tin Nhân Sự').strip()
    block      = data.get('block', '')
    doi_truong = data.get('doi_truong', '')
    extra_to   = data.get('extra_to', [])   # them email tuy chinh
    try:
        rows = nhansu_service.get_cached_or_fetch()
        filtered = nhansu_service.filter_rows(rows, block=block, doi_truong=doi_truong)
        # Thu thap email tu Sheet
        sheet_emails = [
            nhansu_service.get_email(r) for r in filtered
            if nhansu_service.get_email(r) and '@' in nhansu_service.get_email(r)
        ]
        recipients = list(set([nhansu_service.SENDER_EMAIL] + sheet_emails + extra_to))
        ok = nhansu_service.send_notification_email(
            recipients=recipients,
            subject=subject,
            rows=filtered or rows,
            context="Thông tin nhân sự theo yêu cầu"
        )
        return jsonify({"success": ok, "sent_to": recipients})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == '__main__':
    database.init_db()
    # Khởi động đồng bộ ngầm định kỳ 5 phút/lần (300 giây)
    email_service.start_auto_sync(interval_seconds=300)
    # Khởi động auto-sync nhân sự từ Google Sheets (mỗi 5 phút)
    nhansu_service.start_auto_sync(interval_seconds=300)
    port = int(os.environ.get('PORT', 5050))
    print(f"Khởi chạy CEM CSAT Dashboard tại: http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
