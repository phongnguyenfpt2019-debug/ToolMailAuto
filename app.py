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
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
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


# -----------------------------------------------------------------
# TRA CỨU AU: API ENDPOINTS
# -----------------------------------------------------------------
import unicodedata
import re

def _normalize_au_col(c):
    c = str(c or '').strip().lower()
    c = c.replace('đ', 'd').replace('Đ', 'd')
    c = unicodedata.normalize('NFKD', c).encode('ASCII', 'ignore').decode('utf-8')
    return re.sub(r'[^a-z0-9]', '', c)

# Bảng từ khóa nhận diện cột AU (đã chuẩn hóa: chữ thường, không dấu, bỏ ký tự đặc biệt)
_AU_ORDER = ['so_hop_dong', 'tap_diem', 'tstc', 'duong', 'ktv_t10', 'block']
_AU_FIELD_KEYS = {
    'so_hop_dong': ['sohopdong', 'hopdong', 'sohd', 'shd', 'hd', 'mahd', 'mahopdong', 'contract',
                    'contractnumber', 'sohopong', 'hopong', 'mahopong', 'sehipong', 'soaohoipnoang'],
    'tap_diem': ['tapdiem', 'matapdiem', 'tapiem', 'td', 'diem', 'tepiom'],
    'tstc': ['tstc', 'matstc', 'ts'],
    'duong': ['duong', 'tenduong', 'uong', 'tenuong', 'diachi', 'street', 'address', 'eng', 'ongng'],
    'ktv_t10': ['ktvt10', 'ktv', 'nhanvien', 'technician'],
    'block': ['block', 'khoi', 'quan'],
}
_AU_SUBSTR_KEYS = {
    'so_hop_dong': ['hopdong', 'hopong', 'sohd', 'contract'],
    'tap_diem': ['tapdiem', 'tapiem'],
    'tstc': ['tstc'],
    'duong': ['duong', 'diachi', 'street', 'address'],
    'ktv_t10': ['ktv', 'nhanvien'],
    'block': ['block'],
}


def _au_cell_str(v):
    if v is None:
        return ''
    try:
        if pd.isna(v):
            return ''
    except (TypeError, ValueError):
        pass
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return '' if s.lower() in ('nan', 'none', 'nat') else s


def _au_map_columns(df):
    """Chọn cột cho từng trường: ưu tiên khớp tên chính xác -> khớp một phần -> theo vị trí template.
    Nếu nhiều cột cùng khớp, chọn cột có nhiều dữ liệu nhất (tránh cột trống ghi đè cột thật)."""
    cols = list(df.columns)
    norm = {c: _normalize_au_col(c) for c in cols}
    fill = {c: sum(1 for v in df[c].tolist() if _au_cell_str(v)) for c in cols}
    col_map, used = {}, set()

    def pick(field, cands):
        cands = [c for c in cands if c not in used and norm[c] not in ('id', 'stt', 'sothutu')]
        if cands:
            best = max(cands, key=lambda c: fill[c])
            col_map[field] = best
            used.add(best)

    for field in _AU_ORDER:  # 1) khớp chính xác
        pick(field, [c for c in cols if norm[c] in _AU_FIELD_KEYS[field]])
    for field in _AU_ORDER:  # 2) khớp một phần
        if field not in col_map:
            pick(field, [c for c in cols if any(k in norm[c] for k in _AU_SUBSTR_KEYS[field])])

    # 3) Theo thứ tự cột template nếu chưa tìm thấy hoặc cột tìm được không có dữ liệu
    offset = 1 if cols and norm[cols[0]] in ('id', 'stt', 'sothutu') else 0
    if len(cols) >= 5:
        for i, field in enumerate(_AU_ORDER):
            cur = col_map.get(field)
            if cur is not None and fill[cur] > 0:
                continue
            pos = offset + i
            if pos < len(cols) and cols[pos] not in used and fill[cols[pos]] > 0:
                if cur is not None:
                    used.discard(cur)
                col_map[field] = cols[pos]
                used.add(cols[pos])
    return col_map


def _au_read_dataframe(file, filename):
    """Đọc file dạng chuỗi (giữ nguyên số 0 đầu của số HĐ) và tự dò dòng tiêu đề trong 10 dòng đầu."""
    if filename.endswith(('.xlsx', '.xls')):
        raw = pd.read_excel(file, header=None, dtype=str)
    else:
        content = file.read()
        raw = None
        for enc in ('utf-8-sig', 'utf-8', 'cp1258', 'latin-1'):
            try:
                raw = pd.read_csv(io.BytesIO(content), header=None, dtype=str, encoding=enc)
                break
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
        if raw is None:
            raise ValueError('Không đọc được file CSV')
    raw = raw.dropna(how='all').dropna(axis=1, how='all').reset_index(drop=True)
    if raw.empty:
        return raw

    def score(row_vals):
        names = [_normalize_au_col(v) for v in row_vals if _au_cell_str(v)]
        hit = 0
        for field in _AU_ORDER:
            if any(n in _AU_FIELD_KEYS[field] or any(k in n for k in _AU_SUBSTR_KEYS[field]) for n in names):
                hit += 1
        return hit

    header_idx = max(range(min(10, len(raw))), key=lambda i: score(raw.iloc[i].tolist()))
    if score(raw.iloc[header_idx].tolist()) == 0:
        header_idx = 0
    headers, seen = [], {}
    for j, v in enumerate(raw.iloc[header_idx].tolist()):
        h = _au_cell_str(v) or f'Cot_{j + 1}'
        if h in seen:
            seen[h] += 1
            h = f'{h}.{seen[h]}'
        else:
            seen[h] = 0
        headers.append(h)
    df = raw.iloc[header_idx + 1:].reset_index(drop=True)
    df.columns = headers
    return df

@app.route('/api/au/stats')
def api_au_stats():
    search = request.args.get('search', '').strip()
    so_hop_dong = request.args.get('so_hop_dong', '').strip()
    tap_diem = request.args.get('tap_diem', '').strip()
    tstc = request.args.get('tstc', '').strip()
    duong = request.args.get('duong', '').strip()
    ktv = request.args.get('ktv', '').strip()
    block = request.args.get('block', '').strip()

    stats = database.get_au_stats(
        search=search,
        so_hop_dong=so_hop_dong,
        tap_diem=tap_diem,
        tstc=tstc,
        duong=duong,
        ktv=ktv,
        block=block
    )
    return jsonify({"success": True, "stats": stats})

@app.route('/api/au')
def api_au_list():
    search = request.args.get('search', '').strip()
    so_hop_dong = request.args.get('so_hop_dong', '').strip()
    tap_diem = request.args.get('tap_diem', '').strip()
    tstc = request.args.get('tstc', '').strip()
    duong = request.args.get('duong', '').strip()
    ktv = request.args.get('ktv', '').strip()
    block = request.args.get('block', '').strip()
    page = max(int(request.args.get('page', 1)), 1)
    limit = min(max(int(request.args.get('limit', 30)), 1), 200)

    result = database.get_au_records(
        search=search,
        so_hop_dong=so_hop_dong,
        tap_diem=tap_diem,
        tstc=tstc,
        duong=duong,
        ktv=ktv,
        block=block,
        page=page,
        limit=limit
    )
    result["success"] = True
    return jsonify(result)

@app.route('/api/au/filters')
def api_au_filters():
    filters = database.get_au_filters()
    return jsonify({"success": True, **filters})

@app.route('/api/au/template')
def api_au_template():
    """Tạo và tải file mẫu Excel import AU chuẩn (Không có cột ID - ID là trường bảo mật hệ thống tự quản lý)"""
    df = pd.DataFrame([
        {
            "Số hợp đồng": "SGN01-HD12345",
            "Tập điểm": "TD-Q1-001",
            "TSTC": "TSTC-8899",
            "Đường": "Nguyễn Thị Minh Khai",
            "KTV* T10": "Nguyễn Văn A",
            "Block": "Block 1"
        },
        {
            "Số hợp đồng": "SGN01-HD67890",
            "Tập điểm": "TD-Q3-012",
            "TSTC": "TSTC-3344",
            "Đường": "Cách Mạng Tháng 8",
            "KTV* T10": "Trần Văn B",
            "Block": "Block 2"
        },
        {
            "Số hợp đồng": "SGN01-HD54321",
            "Tập điểm": "TD-Q10-008",
            "TSTC": "TSTC-7711",
            "Đường": "Lý Thường Kiệt",
            "KTV* T10": "Lê Văn C",
            "Block": "Block 3"
        }
    ])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Mau_Import_AU')
        ws = writer.sheets['Mau_Import_AU']
        from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
        header_fill = PatternFill(start_color="1E40AF", end_color="1E40AF", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        thin_border = Border(
            left=Side(style='thin', color='D4D4D8'),
            right=Side(style='thin', color='D4D4D8'),
            top=Side(style='thin', color='D4D4D8'),
            bottom=Side(style='thin', color='D4D4D8')
        )
        for col_idx, col in enumerate(ws.iter_cols(min_row=1, max_row=ws.max_row, min_col=1, max_col=ws.max_column), start=1):
            cell_header = col[0]
            cell_header.fill = header_fill
            cell_header.font = header_font
            cell_header.alignment = Alignment(horizontal="center", vertical="center")
            col_letter = cell_header.column_letter
            max_len = max(len(str(c.value or '')) for c in col)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 15)
            for cell in col:
                cell.border = thin_border
                if cell.row > 1:
                    cell.alignment = Alignment(vertical="center")

    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="Template_Import_AU.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route('/api/au/import', methods=['POST'])
def api_au_import():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "Vui lòng chọn file Excel hoặc CSV"}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({"success": False, "error": "Chưa chọn file để tải lên"}), 400

    mode = request.form.get('mode', 'replace').strip()
    filename = file.filename.lower()

    try:
        if not filename.endswith(('.xlsx', '.xls', '.csv')):
            return jsonify({"success": False, "error": "Định dạng file không hỗ trợ. Vui lòng tải lên .xlsx, .xls hoặc .csv"}), 400

        df = _au_read_dataframe(file, filename)
        if df.empty:
            return jsonify({"success": False, "error": "File không có dữ liệu"}), 400

        col_map = _au_map_columns(df)
        print(f"[AU Import] Cột trong file: {list(df.columns)} -> Ánh xạ: {col_map}")

        records = []
        for _, row in df.iterrows():
            so_hop_dong = _au_cell_str(row[col_map['so_hop_dong']]) if 'so_hop_dong' in col_map else ""
            tap_diem = _au_cell_str(row[col_map['tap_diem']]) if 'tap_diem' in col_map else ""
            tstc = _au_cell_str(row[col_map['tstc']]) if 'tstc' in col_map else ""
            duong = _au_cell_str(row[col_map['duong']]) if 'duong' in col_map else ""
            ktv_t10 = _au_cell_str(row[col_map['ktv_t10']]) if 'ktv_t10' in col_map else ""
            block = _au_cell_str(row[col_map['block']]) if 'block' in col_map else ""

            # Bỏ qua dòng hoàn toàn rỗng
            if not any([so_hop_dong, tap_diem, tstc, duong, ktv_t10, block]):
                continue

            records.append({
                "so_hop_dong": so_hop_dong,
                "tap_diem": tap_diem,
                "tstc": tstc,
                "duong": duong,
                "ktv_t10": ktv_t10,
                "block": block
            })

        if not records:
            return jsonify({"success": False, "error": "Không tìm thấy dữ liệu hợp lệ trong file. Vui lòng kiểm tra lại tên cột theo mẫu."}), 400

        result = database.import_au_records(records, mode=mode)
        if result.get("success"):
            labels = {'so_hop_dong': 'Số HĐ', 'tap_diem': 'Tập điểm', 'tstc': 'TSTC',
                      'duong': 'Đường', 'ktv_t10': 'KTV', 'block': 'Block'}
            map_txt = ', '.join(f"{labels[f]}←[{col_map[f]}]" if f in col_map else f"{labels[f]}←(không thấy)"
                                for f in _AU_ORDER)
            return jsonify({
                "success": True,
                "count": result.get("count", 0),
                "max_id": result.get("max_id", 0),
                "mapping": {f: str(col_map.get(f, '')) for f in _AU_ORDER},
                "message": f"Import thành công {result.get('count', 0)} bản ghi. Cột: {map_txt}"
            })
        else:
            return jsonify({"success": False, "error": result.get("error", "Lỗi import dữ liệu")}), 500

    except Exception as e:
        return jsonify({"success": False, "error": f"Lỗi đọc file: {str(e)}"}), 500

@app.route('/api/au/export/excel')
def api_au_export_excel():
    search = request.args.get('search', '').strip()
    so_hop_dong = request.args.get('so_hop_dong', '').strip()
    tap_diem = request.args.get('tap_diem', '').strip()
    tstc = request.args.get('tstc', '').strip()
    duong = request.args.get('duong', '').strip()
    ktv = request.args.get('ktv', '').strip()
    block = request.args.get('block', '').strip()

    result = database.get_au_records(
        search=search,
        so_hop_dong=so_hop_dong,
        tap_diem=tap_diem,
        tstc=tstc,
        duong=duong,
        ktv=ktv,
        block=block,
        page=1,
        limit=100000
    )
    records = result.get('records', [])

    export_data = []
    for r in records:
        export_data.append({
            "ID": r.get('id'),
            "Số hợp đồng": r.get('so_hop_dong', ''),
            "Tập điểm": r.get('tap_diem', ''),
            "TSTC": r.get('tstc', ''),
            "Đường": r.get('duong', ''),
            "KTV* T10": r.get('ktv_t10', ''),
            "Block": r.get('block', '')
        })

    df = pd.DataFrame(export_data) if export_data else pd.DataFrame(columns=["ID", "Số hợp đồng", "Tập điểm", "TSTC", "Đường", "KTV* T10", "Block"])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Tra_Cuu_AU')
        ws = writer.sheets['Tra_Cuu_AU']
        for col in ws.columns:
            max_len = max(len(str(c.value or '')) for c in col)
            col_letter = col[0].column_letter
            ws.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 45)

    output.seek(0)
    filename = f"Tra_Cuu_AU_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route('/api/au/export/csv')
def api_au_export_csv():
    search = request.args.get('search', '').strip()
    so_hop_dong = request.args.get('so_hop_dong', '').strip()
    tap_diem = request.args.get('tap_diem', '').strip()
    tstc = request.args.get('tstc', '').strip()
    duong = request.args.get('duong', '').strip()
    ktv = request.args.get('ktv', '').strip()
    block = request.args.get('block', '').strip()

    result = database.get_au_records(
        search=search,
        so_hop_dong=so_hop_dong,
        tap_diem=tap_diem,
        tstc=tstc,
        duong=duong,
        ktv=ktv,
        block=block,
        page=1,
        limit=100000
    )
    records = result.get('records', [])

    export_data = []
    for r in records:
        export_data.append({
            "ID": r.get('id'),
            "Số hợp đồng": r.get('so_hop_dong', ''),
            "Tập điểm": r.get('tap_diem', ''),
            "TSTC": r.get('tstc', ''),
            "Đường": r.get('duong', ''),
            "KTV* T10": r.get('ktv_t10', ''),
            "Block": r.get('block', '')
        })

    df = pd.DataFrame(export_data) if export_data else pd.DataFrame(columns=["ID", "Số hợp đồng", "Tập điểm", "TSTC", "Đường", "KTV* T10", "Block"])

    output = io.StringIO()
    df.to_csv(output, index=False, encoding='utf-8-sig')
    csv_bytes = io.BytesIO(output.getvalue().encode('utf-8-sig'))
    filename = f"Tra_Cuu_AU_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return send_file(
        csv_bytes,
        as_attachment=True,
        download_name=filename,
        mimetype="text/csv"
    )

@app.route('/api/au/record', methods=['POST'])
def api_au_add():
    data = request.get_json() or {}
    res = database.add_au_record(data)
    if res.get('success'):
        return jsonify(res)
    return jsonify(res), 400

@app.route('/api/au/record/<int:au_id>', methods=['PUT'])
def api_au_update(au_id):
    data = request.get_json() or {}
    res = database.update_au_record(au_id, data)
    if res.get('success'):
        return jsonify(res)
    return jsonify(res), 400

AU_DELETE_PASSWORD = os.getenv("AU_DELETE_PASSWORD", "doitruongsg1")

@app.route('/api/au/record/<int:au_id>', methods=['DELETE', 'POST'])
def api_au_delete(au_id):
    req_pass = request.args.get('password', '')
    if not req_pass and request.is_json:
        req_pass = (request.get_json() or {}).get('password', '')
    if req_pass != AU_DELETE_PASSWORD:
        return jsonify({"success": False, "error": "Mật khẩu xác nhận xóa không đúng! Vui lòng nhập đúng mật khẩu: doitruongsg1"}), 403

    res = database.delete_au_record(au_id)
    if res.get('success'):
        return jsonify(res)
    return jsonify(res), 400

@app.route('/api/au/clear', methods=['POST'])
def api_au_clear():
    data = request.get_json() or {}
    req_pass = data.get('password') or request.args.get('password', '')
    if req_pass != AU_DELETE_PASSWORD:
        return jsonify({"success": False, "error": "Mật khẩu xác nhận xóa không đúng! Vui lòng nhập đúng mật khẩu: doitruongsg1"}), 403

    res = database.clear_all_au_records()
    if res.get('success'):
        return jsonify({"success": True, "message": "Đã xóa toàn bộ dữ liệu AU thành công"})
    return jsonify(res), 400


if __name__ == '__main__':
    database.init_db()
    # Khởi động đồng bộ ngầm định kỳ 5 phút/lần (300 giây)
    email_service.start_auto_sync(interval_seconds=300)
    # Khởi động auto-sync nhân sự từ Google Sheets (mỗi 5 phút)
    nhansu_service.start_auto_sync(interval_seconds=300)
    port = int(os.environ.get('PORT', 5050))
    print(f"Khởi chạy CEM CSAT Dashboard tại: http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
