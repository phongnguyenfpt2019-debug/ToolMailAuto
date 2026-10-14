// FPT Telecom CEM CSAT & Giục Tiến Độ Dashboard Logic

let currentTag = 'cem'; // 'cem' | 'giuc'
let currentPage = 1;
const pageSize = 15;
let currentCsatFilter = '';
let currentSearch = '';
let currentDateFrom = '';
let currentDateTo = '';
let currentCemBlock = '';
let currentCemDoiTruong = '';
let searchDebounceTimeout = null;

// Giục tiến độ state
let currentGiucPage = 1;
let currentGiucPrio = '';
let currentGiucSearch = '';
let currentGiucDateFrom = '';
let currentGiucDateTo = '';
let currentGiucBlock = '';
let currentGiucDoiTruong = '';
let giucSearchDebounceTimeout = null;
let currentCllPage = 1;
let currentCllSearch = '';
let currentCllDateFrom = '';
let currentCllDateTo = '';
let currentCllBlock = '';
let currentCllDoiTruong = '';
let cllSearchDebounceTimeout = null;

// Nhân Sự state
let currentNsPage = 1;
let currentNsBlock = '';
let currentNsDoiTruong = '';
let currentNsSearch = '';
let nsSearchDebounceTimeout = null;
const NS_PAGE_SIZE = 20;


// Chart instances
let chartCsatPie = null;
let chartTimeline = null;
let chartTechs = null;
let chartIssues = null;

document.addEventListener('DOMContentLoaded', () => {
    initDashboard();
    // Default show CEM tag
    switchTag('cem');
    // Periodic UI refresh every 60s to reflect background auto-sync (both CEM, Giục & AU)
    setInterval(() => {
        loadStats();
        loadGiucStats();
        loadCllStats();
        loadAuStats();
        if (currentTag === 'cem') {
            loadTable(currentPage);
        } else if (currentTag === 'giuc') {
            loadGiucTable(currentGiucPage);
        } else if (currentTag === 'au') {
            loadAuTable(currentAuPage);
        } else if (currentTag === 'nhansu') {
            loadNhanSuTable(currentNsPage);
        } else {
            loadCllTable(currentCllPage);
        }
    }, 60000);
});

async function initDashboard() {
    await Promise.all([
        loadNhanSuMeta(),
        loadStats(),
        loadTable(1),
        loadGiucStats(),
        loadCllStats(),
        loadAuStats()
    ]);
}

// -------------------------------------------------------------
// Switch Tag (CEM vs Giục Tiến Độ vs CLL vs AU vs HR)
// -------------------------------------------------------------
function switchTag(tag) {
    currentTag = tag;
    const viewCem    = document.getElementById('view-cem');
    const viewGiuc   = document.getElementById('view-giuc');
    const viewCll    = document.getElementById('view-cll');
    const viewAu     = document.getElementById('view-au');
    const viewNhanSu = document.getElementById('view-nhansu');
    const navCem     = document.getElementById('nav-item-cem');
    const navGiuc    = document.getElementById('nav-item-giuc');
    const navCll     = document.getElementById('nav-item-cll');
    const navAu      = document.getElementById('nav-item-au');
    const navNhanSu  = document.getElementById('nav-item-nhansu');
    const tagPill    = document.getElementById('topbar-tag-name');
    const topTitle   = document.getElementById('topbar-page-title');

    const viewLogins = document.getElementById('view-logins');
    const navLogins  = document.getElementById('nav-item-logins');

    // Hide all views & deactivate all nav items
    [viewCem, viewGiuc, viewCll, viewAu, viewNhanSu, viewLogins].forEach(v => v && v.classList.remove('active'));
    [navCem, navGiuc, navCll, navAu, navNhanSu, navLogins].forEach(n => n && n.classList.remove('active'));

    if (tag === 'cem') {
        if (viewCem) viewCem.classList.add('active');
        if (navCem) navCem.classList.add('active');
        if (tagPill) tagPill.textContent = 'CEM';
        if (topTitle) topTitle.textContent = 'Dashboard Tổng Hợp CEM - CSAT 1, 2 CLDV';
    } else if (tag === 'giuc') {
        if (viewGiuc) viewGiuc.classList.add('active');
        if (navGiuc) navGiuc.classList.add('active');
        if (tagPill) tagPill.textContent = 'GIỤC TIẾN ĐỘ';
        if (topTitle) topTitle.textContent = 'Quản Lý Yêu Cầu Giục Tiến Độ Từ Khách Hàng';
        loadGiucStats();
        loadGiucTable(1);
    } else if (tag === 'au') {
        if (viewAu) viewAu.classList.add('active');
        if (navAu) navAu.classList.add('active');
        if (tagPill) tagPill.textContent = 'TRA CỨU AU';
        if (topTitle) topTitle.textContent = 'Tra Cứu Thông Tin Hợp Đồng / Tập Điểm / TSTC';
        loadAuStats();
        loadAuFilters();
        loadAuTable(1);
    } else if (tag === 'nhansu') {
        if (viewNhanSu) viewNhanSu.classList.add('active');
        if (navNhanSu) navNhanSu.classList.add('active');
        if (tagPill) tagPill.textContent = 'ADMIN · HR';
        if (topTitle) topTitle.textContent = 'Quản Lý Nhân Sự — Chi Nhánh Sài Gòn 01';
        loadNhanSuMeta();
        loadNhanSuTable(1);
    } else if (tag === 'logins') {
        if (viewLogins) viewLogins.classList.add('active');
        if (navLogins) navLogins.classList.add('active');
        if (tagPill) tagPill.textContent = 'ADMIN · LOGIN';
        if (topTitle) topTitle.textContent = 'Danh Sách Tài Khoản Đăng Nhập';
        loadLoginsTable();
    } else {
        if (viewCll) viewCll.classList.add('active');
        if (navCll) navCll.classList.add('active');
        if (tagPill) tagPill.textContent = 'CLL >3';
        if (topTitle) topTitle.textContent = 'Checklist Bảo Trì Phát Sinh Từ 3 Lần';
        loadCllStats();
        loadCllTable(1);
    }
}

// -------------------------------------------------------------
// ADMIN: Menu + Danh sách Login
// -------------------------------------------------------------
let loginsData = [];
const loginsVisible = new Set();

function toggleAdminMenu() {
    const sub = document.getElementById('admin-submenu');
    const chev = document.getElementById('admin-chevron');
    if (!sub) return;
    const hidden = sub.classList.toggle('hidden');
    if (chev) chev.style.transform = hidden ? 'rotate(-90deg)' : '';
}

function escHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function loadLoginsTable() {
    if (!window.IS_ADMIN) return;
    const body = document.getElementById('table-logins-body');
    if (body) body.innerHTML = `<tr><td colspan="5" class="py-8 text-center text-slate-400"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Đang tải...</td></tr>`;
    try {
        const res = await fetch('/api/admin/logins');
        const json = await res.json();
        loginsData = json.success ? json.data : [];
    } catch (e) {
        loginsData = [];
    }
    const badge = document.getElementById('badge-logins-cnt');
    if (badge) badge.textContent = loginsData.length;
    renderLoginsTable();
}

function renderLoginsTable() {
    const body = document.getElementById('table-logins-body');
    if (!body) return;
    const q = (document.getElementById('filter-logins-search')?.value || '').trim().toLowerCase();
    const rows = loginsData.filter(u => !q || u.username.toLowerCase().includes(q));
    document.getElementById('table-logins-count').textContent = `${rows.length} tài khoản`;
    if (!rows.length) {
        body.innerHTML = `<tr><td colspan="5" class="py-8 text-center text-slate-400">Chưa có tài khoản nào</td></tr>`;
        return;
    }
    body.innerHTML = rows.map((u, i) => {
        const shown = loginsVisible.has(u.id);
        const pw = shown ? escHtml(u.password) : '•'.repeat(Math.min(u.password.length, 10));
        return `
        <tr class="hover:bg-slate-50 transition-colors">
            <td class="py-2.5 px-3 font-semibold text-slate-500">${i + 1}</td>
            <td class="py-2.5 px-3">
                <div class="font-semibold text-slate-800">${escHtml(u.username)}</div>
                <div class="text-[11px] text-slate-400">Tạo: ${escHtml(u.created_at || '')} · Đăng nhập: ${escHtml(u.last_login || '')}</div>
            </td>
            <td class="py-2.5 px-3">
                <div class="flex items-center gap-2">
                    <span class="font-mono text-slate-700">${pw}</span>
                    <button onclick="toggleLoginPw(${u.id})" title="Hiện/Ẩn" class="text-slate-400 hover:text-indigo-600">
                        <i class="fa-solid ${shown ? 'fa-eye-slash' : 'fa-eye'}"></i>
                    </button>
                </div>
            </td>
            <td class="py-2.5 px-3 text-center">${roleCell(u)}</td>
            <td class="py-2.5 px-3 text-center">
                <div class="inline-flex gap-1.5">
                    <button onclick="changeLoginPw(${u.id})" title="Đổi mật khẩu" class="px-2.5 py-1 rounded-md bg-indigo-50 text-indigo-700 hover:bg-indigo-100 font-semibold"><i class="fa-solid fa-pen"></i></button>
                    <button onclick="deleteLogin(${u.id})" title="Xóa" class="px-2.5 py-1 rounded-md bg-red-50 text-red-600 hover:bg-red-100 font-semibold"><i class="fa-solid fa-trash"></i></button>
                </div>
            </td>
        </tr>`;
    }).join('');
}

const DEFAULT_ADMIN_EMAILS = ['phuongnam.phongnh5@fpt.net'];

function roleCell(u) {
    const isAdm = (u.role || 'USER') === 'ADMIN';
    const badge = isAdm
        ? 'bg-orange-100 text-orange-700 border-orange-200'
        : 'bg-slate-100 text-slate-600 border-slate-200';
    if (DEFAULT_ADMIN_EMAILS.includes(u.username)) {
        return `<span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold border ${badge}" title="Admin mặc định"><i class="fa-solid fa-lock text-[9px]"></i> ADMIN</span>`;
    }
    return `<select onchange="changeLoginRole(${u.id}, this.value)"
                class="px-2 py-1 rounded-full text-[11px] font-bold border cursor-pointer focus:outline-none ${badge}">
                <option value="USER" ${!isAdm ? 'selected' : ''}>USER</option>
                <option value="ADMIN" ${isAdm ? 'selected' : ''}>ADMIN</option>
            </select>`;
}

async function changeLoginRole(id, role) {
    const res = await fetch(`/api/admin/logins/${id}/role`, {
        method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({role})
    });
    const json = await res.json();
    if (!json.success) alert(json.error || 'Lỗi cập nhật quyền');
    loadLoginsTable();
}

function toggleLoginPw(id) {
    loginsVisible.has(id) ? loginsVisible.delete(id) : loginsVisible.add(id);
    renderLoginsTable();
}

async function changeLoginPw(id) {
    const u = loginsData.find(x => x.id === id);
    const pw = prompt(`Nhập mật khẩu mới cho ${u ? u.username : ''} (tối thiểu 6 ký tự):`);
    if (pw === null) return;
    const res = await fetch(`/api/admin/logins/${id}`, {
        method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({password: pw})
    });
    const json = await res.json();
    if (!json.success) return alert(json.error || 'Lỗi cập nhật');
    loadLoginsTable();
}

async function deleteLogin(id) {
    const u = loginsData.find(x => x.id === id);
    if (!confirm(`Xóa tài khoản ${u ? u.username : ''}? Người dùng sẽ phải đăng ký lại mật khẩu.`)) return;
    await fetch(`/api/admin/logins/${id}`, {method: 'DELETE'});
    loadLoginsTable();
}

// Redirect to login if session expired
(function () {
    const _fetch = window.fetch;
    window.fetch = async (...args) => {
        const res = await _fetch(...args);
        if (res.status === 401) window.location.href = '/login';
        return res;
    };
})();
if (window.IS_ADMIN) document.addEventListener('DOMContentLoaded', loadLoginsTable);

// -------------------------------------------------------------
// Date Filtering Helpers (dựa vào Thời Gian Đánh Giá)
// -------------------------------------------------------------
function setQuickDate(preset) {
    document.querySelectorAll('.preset-btn').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-preset') === preset);
    });

    const now = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    const toYMD = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

    if (preset === 'all') {
        currentDateFrom = '';
        currentDateTo = '';
    } else if (preset === 'today') {
        currentDateFrom = toYMD(now);
        currentDateTo = toYMD(now);
    } else if (preset === 'yesterday') {
        const yest = new Date(now);
        yest.setDate(now.getDate() - 1);
        currentDateFrom = toYMD(yest);
        currentDateTo = toYMD(yest);
    } else if (preset === '7days') {
        const past7 = new Date(now);
        past7.setDate(now.getDate() - 6);
        currentDateFrom = toYMD(past7);
        currentDateTo = toYMD(now);
    } else if (preset === 'month') {
        const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
        currentDateFrom = toYMD(startOfMonth);
        currentDateTo = toYMD(now);
    }

    document.getElementById('filter-date-from').value = currentDateFrom;
    document.getElementById('filter-date-to').value = currentDateTo;

    refreshAll();
}

function handleDateChange() {
    currentDateFrom = document.getElementById('filter-date-from').value;
    currentDateTo = document.getElementById('filter-date-to').value;

    document.querySelectorAll('.preset-btn').forEach(btn => btn.classList.remove('active'));
    refreshAll();
}

function resetDateFilter() {
    setQuickDate('all');
}

function refreshAll() {
    loadStats();
    loadTable(1);
}

function handleCemNsFilter() {
    currentCemBlock = document.getElementById('filter-cem-block')?.value || '';
    currentCemDoiTruong = document.getElementById('filter-cem-doi-truong')?.value || '';
    loadStats();
    loadTable(1);
}

// -------------------------------------------------------------
// Load Statistics & Render Charts
// -------------------------------------------------------------
async function loadStats() {
    try {
        const onlySurvey = document.getElementById('filter-only-survey')?.checked ?? true;
        const params = new URLSearchParams({
            only_survey: onlySurvey,
            date_from: currentDateFrom,
            date_to: currentDateTo,
            block: currentCemBlock,
            doi_truong: currentCemDoiTruong
        });

        const res = await fetch(`/api/stats?${params.toString()}`);
        const data = await res.json();

        if (!data.success) return;

        // KPI Counters
        const kpi = data.kpi;
        animateNumber('kpi-total', kpi.total_records);
        animateNumber('kpi-csat1', kpi.total_csat_1);
        animateNumber('kpi-csat2', kpi.total_csat_2);
        animateNumber('kpi-techs', kpi.total_techs);
        animateNumber('kpi-home', kpi.total_home_support);

        // Sidebar badge
        const badgeEl = document.getElementById('badge-cem-cnt');
        if (badgeEl) badgeEl.textContent = `${kpi.total_records} ca`;

        // Percentages
        const total = kpi.total_csat_1 + kpi.total_csat_2;
        if (total > 0) {
            const p1 = Math.round((kpi.total_csat_1 / total) * 100);
            const p2 = 100 - p1;
            document.getElementById('kpi-csat1-pct').textContent = `${p1}% tổng ca`;
            document.getElementById('kpi-csat2-pct').textContent = `${p2}% tổng ca`;
        } else {
            document.getElementById('kpi-csat1-pct').textContent = `0% tổng ca`;
            document.getElementById('kpi-csat2-pct').textContent = `0% tổng ca`;
        }

        // Last sync info
        if (data.last_sync) {
            document.getElementById('last-sync-time').textContent = data.last_sync.sync_time;
        } else {
            document.getElementById('last-sync-time').textContent = 'Chưa đồng bộ';
        }

        // Render Charts with Light Theme styling
        renderDonutChart(kpi.total_csat_1, kpi.total_csat_2);
        renderTimelineChart(data.timeline);
        renderTechsChart(data.top_techs);
        renderIssuesChart(data.top_issues);

    } catch (err) {
        console.error("Lỗi tải thống kê:", err);
    }
}

// Donut Chart: CSAT 1 vs 2
function renderDonutChart(csat1, csat2) {
    const ctx = document.getElementById('chart-csat-pie').getContext('2d');
    if (chartCsatPie) chartCsatPie.destroy();

    const hasData = (csat1 + csat2) > 0;
    const dataVals = hasData ? [csat1, csat2] : [1, 1];
    const bgColors = hasData ? ['#dc2626', '#d97706'] : ['#e2e8f0', '#cbd5e1'];

    chartCsatPie = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['CSAT 1 (Rất không hài lòng)', 'CSAT 2 (Không hài lòng)'],
            datasets: [{
                data: dataVals,
                backgroundColor: bgColors,
                borderWidth: 3,
                borderColor: '#ffffff',
                hoverOffset: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#334155', font: { family: 'Plus Jakarta Sans', size: 12, weight: 600 } }
                },
                tooltip: {
                    callbacks: {
                        label: function(item) {
                            if (!hasData) return 'Chưa có dữ liệu';
                            const val = item.raw;
                            const pct = Math.round((val / (csat1 + csat2)) * 100);
                            return ` ${item.label}: ${val} ca (${pct}%)`;
                        }
                    }
                }
            },
            cutout: '68%'
        }
    });
}

// Timeline Chart: Daily Trends
function renderTimelineChart(timeline) {
    const ctx = document.getElementById('chart-timeline').getContext('2d');
    if (chartTimeline) chartTimeline.destroy();

    const labels = timeline.length ? timeline.map(t => t.date_key) : ['Chưa có dữ liệu'];
    const csat1Data = timeline.length ? timeline.map(t => t.csat1_cnt) : [0];
    const csat2Data = timeline.length ? timeline.map(t => t.csat2_cnt) : [0];

    chartTimeline = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'CSAT 1',
                    data: csat1Data,
                    borderColor: '#dc2626',
                    backgroundColor: 'rgba(220, 38, 38, 0.1)',
                    fill: true,
                    tension: 0.35,
                    borderWidth: 2,
                    pointRadius: 5,
                    pointBackgroundColor: '#dc2626'
                },
                {
                    label: 'CSAT 2',
                    data: csat2Data,
                    borderColor: '#d97706',
                    backgroundColor: 'rgba(217, 119, 6, 0.1)',
                    fill: true,
                    tension: 0.35,
                    borderWidth: 2,
                    pointRadius: 5,
                    pointBackgroundColor: '#d97706'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { color: '#334155', font: { family: 'Plus Jakarta Sans', size: 11, weight: 600 } }
                }
            },
            scales: {
                x: {
                    grid: { color: '#f1f5f9' },
                    ticks: { color: '#64748b', font: { size: 11 } }
                },
                y: {
                    beginAtZero: true,
                    grid: { color: '#f1f5f9' },
                    ticks: { stepSize: 1, color: '#64748b' }
                }
            }
        }
    });
}

// Techs Chart: Horizontal Bar
function renderTechsChart(techs) {
    const ctx = document.getElementById('chart-techs').getContext('2d');
    if (chartTechs) chartTechs.destroy();

    const labels = techs.length ? techs.map(t => t.technician) : ['Chưa có'];
    const dataVals = techs.length ? techs.map(t => t.count) : [0];

    chartTechs = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Số ca CSAT 1, 2',
                data: dataVals,
                backgroundColor: 'rgba(37, 99, 235, 0.85)',
                borderColor: '#2563eb',
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    grid: { color: '#f1f5f9' },
                    ticks: { stepSize: 1, color: '#64748b' }
                },
                y: {
                    grid: { display: false },
                    ticks: { color: '#334155', font: { family: 'JetBrains Mono', size: 11, weight: 600 } }
                }
            }
        }
    });
}

// Issues Chart: Bar
function renderIssuesChart(issues) {
    const ctx = document.getElementById('chart-issues').getContext('2d');
    if (chartIssues) chartIssues.destroy();

    const labels = issues.length ? issues.map(i => i.issue_group) : ['Chưa có'];
    const dataVals = issues.length ? issues.map(i => i.count) : [0];

    chartIssues = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Số ca phản ánh',
                data: dataVals,
                backgroundColor: 'rgba(242, 111, 33, 0.85)',
                borderColor: '#f26f21',
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: '#334155', font: { size: 11, weight: 600 } }
                },
                y: {
                    beginAtZero: true,
                    grid: { color: '#f1f5f9' },
                    ticks: { stepSize: 1, color: '#64748b' }
                }
            }
        }
    });
}

// -------------------------------------------------------------
// Data Table Functions (Grouped Columns: Basic & Evaluation)
// -------------------------------------------------------------
async function loadTable(page = 1) {
    currentPage = page;
    const tbody = document.getElementById('table-body');
    const onlySurvey = document.getElementById('filter-only-survey').checked;

    tbody.innerHTML = `
        <tr>
            <td colspan="11" class="text-center py-5">
                <div class="loading-state">
                    <i class="fa-solid fa-circle-notch fa-spin text-orange" style="font-size: 1.5rem;"></i>
                    <p style="margin-top: 8px; color: #64748b; font-weight: 600;">Đang nạp dữ liệu chi tiết...</p>
                </div>
            </td>
        </tr>
    `;

    try {
        const queryParams = new URLSearchParams({
            page: currentPage,
            limit: pageSize,
            csat: currentCsatFilter,
            search: currentSearch,
            date_from: currentDateFrom,
            date_to: currentDateTo,
            only_survey: onlySurvey,
            block: currentCemBlock,
            doi_truong: currentCemDoiTruong
        });

        const res = await fetch(`/api/emails?${queryParams.toString()}`);
        const result = await res.json();

        if (!result.success || !result.data.length) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="11" class="text-center py-5">
                        <div class="empty-state">
                            <i class="fa-regular fa-folder-open text-muted" style="font-size: 2.5rem; margin-bottom: 8px;"></i>
                            <h4 style="color: #334155; margin-bottom: 4px;">Không tìm thấy dữ liệu mail CEM phù hợp</h4>
                            <p style="color: #64748b; font-size: 0.85rem;">Thử thay đổi bộ lọc ngày hoặc nhấn <strong>"Đồng Bộ Mail Ngay"</strong> để tải mới từ mail.fpt.net</p>
                        </div>
                    </td>
                </tr>
            `;
            document.getElementById('table-total-count').textContent = '0 bản ghi';
            document.getElementById('pagination-info').textContent = 'Hiển thị 0 - 0 của 0';
            document.getElementById('btn-prev').disabled = true;
            document.getElementById('btn-next').disabled = true;
            return;
        }

        document.getElementById('table-total-count').textContent = `${result.total} bản ghi`;

        let rowsHtml = '';
        for (const item of result.data) {
            let csatBadge = '<span class="text-muted">-</span>';
            if (item.csat_score === 1) {
                csatBadge = `<span class="badge-csat badge-csat-1"><i class="fa-solid fa-circle-exclamation"></i> 1</span>`;
            } else if (item.csat_score === 2) {
                csatBadge = `<span class="badge-csat badge-csat-2"><i class="fa-solid fa-triangle-exclamation"></i> 2</span>`;
            }

            let techHtml = '<span class="text-muted">-</span>';
            if (item.technician) {
                const blockBadge = item.ns_block ? `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-orange-100 text-orange-700 ml-1" title="Block ${escapeHtml(item.ns_block)}">${escapeHtml(item.ns_block)}</span>` : '';
                const dtLine = item.ns_doi_truong ? `<div class="text-[11px] text-slate-500 mt-0.5" title="Đội Trưởng: ${escapeHtml(item.ns_doi_truong)}"><i class="fa-solid fa-user-shield text-[10px] text-orange-500 mr-1"></i>${escapeHtml(item.ns_doi_truong)}</div>` : '';
                const nvName = item.ns_nv_name ? `<div class="font-bold text-slate-800 text-xs">${escapeHtml(item.ns_nv_name)}</div>` : '';
                techHtml = `
                    <div>
                        ${nvName}
                        <div class="flex items-center flex-wrap gap-1 mt-0.5">
                            <span class="badge-tech">${escapeHtml(item.technician)}</span>
                            ${blockBadge}
                        </div>
                        ${dtLine}
                    </div>
                `;
            }

            rowsHtml += `
                <tr class="row-main">
                    <!-- NHÓM THÔNG TIN CƠ BẢN -->
                    <td><strong class="text-orange font-mono">${escapeHtml(item.contract || 'N/A')}</strong></td>
                    <td><strong style="color: #0f172a;">${escapeHtml(item.customer_name || 'Khách hàng')}</strong></td>
                    <td>${techHtml}</td>
                    <td class="font-mono">${escapeHtml(item.phone || '-')}</td>
                    <td class="td-basic-last" style="max-width: 200px; white-space: normal;"><small>${escapeHtml(item.address || '-')}</small></td>
                    
                    <!-- NHÓM THÔNG TIN ĐÁNH GIÁ -->
                    <td style="text-align: center;">${csatBadge}</td>
                    <td><span class="text-red font-semibold">${escapeHtml(item.issue_group || 'Chưa phân loại')}</span></td>
                    <td style="max-width: 180px; white-space: normal;"><small class="italic">${escapeHtml(item.notes || '-')}</small></td>
                    <td class="font-mono"><small>${escapeHtml(item.completed_time || '-')}</small></td>
                    <td class="td-eval-last"><strong class="text-orange font-mono"><small>${escapeHtml(item.eval_time || item.email_date || '-')}</small></strong></td>
                    
                    <!-- THAO TÁC -->
                    <td style="text-align: center;">
                        <button class="btn btn-sm btn-primary" onclick="openDetailModal(${item.id})">
                            <i class="fa-solid fa-eye"></i> Xem Thư Gốc
                        </button>
                    </td>
                </tr>
            `;
        }

        tbody.innerHTML = rowsHtml;

        // Pagination setup
        const startIdx = (currentPage - 1) * pageSize + 1;
        const endIdx = Math.min(currentPage * pageSize, result.total);
        document.getElementById('pagination-info').textContent = `Hiển thị ${startIdx} - ${endIdx} của ${result.total}`;
        document.getElementById('current-page').textContent = currentPage;

        document.getElementById('btn-prev').disabled = currentPage <= 1;
        document.getElementById('btn-next').disabled = endIdx >= result.total;

    } catch (err) {
        console.error("Lỗi tải bảng:", err);
        tbody.innerHTML = `<tr><td colspan="11" class="text-center py-5 text-red font-semibold">Lỗi khi tải dữ liệu! Vui lòng thử lại.</td></tr>`;
    }
}

function changePage(delta) {
    loadTable(currentPage + delta);
}

function handleSearch(event) {
    const val = event.target.value.trim();
    const clearBtn = document.querySelector('.btn-clear');
    clearBtn.style.display = val ? 'block' : 'none';

    clearTimeout(searchDebounceTimeout);
    searchDebounceTimeout = setTimeout(() => {
        currentSearch = val;
        loadTable(1);
    }, 350);
}

function clearSearch() {
    document.getElementById('filter-search').value = '';
    document.querySelector('.btn-clear').style.display = 'none';
    currentSearch = '';
    loadTable(1);
}

function filterCSAT(score) {
    currentCsatFilter = score;
    document.querySelectorAll('#view-cem .filter-pills .pill-btn').forEach(b => {
        b.classList.remove('active');
        if (b.getAttribute('data-csat') === score) {
            b.classList.add('active');
        }
    });

    // Cập nhật viền nổi bật KPI card tương ứng
    const cardTotal = document.getElementById('kpi-card-cem-total');
    const cardCsat1 = document.getElementById('kpi-card-cem-csat1');
    const cardCsat2 = document.getElementById('kpi-card-cem-csat2');
    [cardTotal, cardCsat1, cardCsat2].forEach(c => c && c.classList.remove('kpi-card-active'));
    if (score === '' && cardTotal) cardTotal.classList.add('kpi-card-active');
    else if (score === '1' && cardCsat1) cardCsat1.classList.add('kpi-card-active');
    else if (score === '2' && cardCsat2) cardCsat2.classList.add('kpi-card-active');

    loadTable(1);
}

function handleFilterChange() {
    loadStats();
    loadTable(1);
}

// -------------------------------------------------------------
// Detail Modal (Structured + Sandboxed Iframe)
// -------------------------------------------------------------
async function openDetailModal(id) {
    const modal = document.getElementById('detail-modal');
    const grid = document.getElementById('modal-detail-grid');
    const iframe = document.getElementById('modal-iframe');
    const title = document.getElementById('modal-contract-title');
    const badgeType = document.getElementById('modal-badge-type');

    if (badgeType) badgeType.textContent = 'CHI TIẾT THƯ GỐC CEM';
    if (title) title.textContent = 'Đang tải chi tiết...';
    if (grid) grid.innerHTML = '<div class="text-center py-5"><i class="fa-solid fa-circle-notch fa-spin text-orange" style="font-size: 1.5rem;"></i><p style="margin-top: 8px; color: #64748b;">Đang tải chi tiết email...</p></div>';
    if (iframe) iframe.srcdoc = '';

    modal.classList.add('show');
    switchModalTab('parsed');

    try {
        const res = await fetch(`/api/email/${id}`);
        const json = await res.json();
        if (!json.success) {
            if (grid) grid.innerHTML = `<div class="text-center py-5 text-red font-semibold">Lỗi: ${escapeHtml(json.error || 'Không tải được chi tiết')}</div>`;
            return showToast("Không tải được chi tiết email", "error");
        }

        const data = json.data;
        if (title) {
            title.innerHTML = `Hợp đồng: <span class="badge-contract">${escapeHtml(data.contract || 'N/A')}</span> | KH: <strong>${escapeHtml(data.customer_name || 'Khách hàng')}</strong>`;
        }

        let csatHtml = '<span class="text-muted">-</span>';
        if (data.csat_score === 1) {
            csatHtml = '<span class="badge-csat badge-csat-1"><i class="fa-solid fa-circle-exclamation"></i> 1 (Rất không hài lòng)</span>';
        } else if (data.csat_score === 2) {
            csatHtml = '<span class="badge-csat badge-csat-2"><i class="fa-solid fa-triangle-exclamation"></i> 2 (Không hài lòng)</span>';
        }

        const value = (label, val, cls = '') => `
            <div class="detail-row">
                <span class="detail-label">${label}:</span>
                <span class="detail-value ${cls}">${val}</span>
            </div>
        `;

        if (grid) {
            grid.innerHTML = `
                <div class="detail-section">
                    <h4><i class="fa-solid fa-id-card text-blue-600"></i> THÔNG TIN CƠ BẢN</h4>
                    ${value('Số Hợp Đồng', `<strong class="badge-contract">${escapeHtml(data.contract || 'N/A')}</strong>`)}
                    ${value('Khách Hàng', `<strong>${escapeHtml(data.customer_name || 'N/A')}</strong>`)}
                    ${value('SĐT Đánh Giá', `<span class="font-mono">${escapeHtml(data.phone || 'N/A')}</span>`)}
                    ${value('Địa Chỉ Khách Hàng', escapeHtml(data.address || 'N/A'))}
                    ${value('NVKT (Inside)', `<span class="badge-tech font-mono">${escapeHtml(data.technician || 'N/A')}</span>`)}
                    ${data.ns_nv_name ? value('Họ Tên NV (Nhân Sự)', `<strong class="text-slate-800">${escapeHtml(data.ns_nv_name)}</strong>`) : ''}
                    ${data.ns_block ? value('Block Phân Công', `<span class="px-2 py-0.5 rounded text-xs font-bold bg-orange-100 text-orange-700">${escapeHtml(data.ns_block)}</span>`) : ''}
                    ${data.ns_doi_truong ? value('Đội Trưởng', `<span class="font-semibold text-slate-700"><i class="fa-solid fa-user-shield text-orange-500 mr-1"></i>${escapeHtml(data.ns_doi_truong)}</span>`) : ''}
                </div>

                <div class="detail-section">
                    <h4><i class="fa-solid fa-star-half-stroke text-orange-600"></i> THÔNG TIN ĐÁNH GIÁ</h4>
                    ${value('Điểm CSAT', csatHtml)}
                    ${value('Nhóm Lỗi Phản Ánh', `<span class="text-red font-semibold">${escapeHtml(data.issue_group || 'Chưa ghi nhận')}</span>`)}
                    ${value('Ghi Chú Khách Hàng', `<span class="italic text-slate-700">${escapeHtml(data.notes || 'Không có ghi chú')}</span>`)}
                    ${value('Thời Gian Hoàn Tất', `<span class="font-mono text-xs">${escapeHtml(data.completed_time || 'N/A')}</span>`)}
                    ${value('Thời Gian Đánh Giá', `<strong class="text-orange font-mono text-xs">${escapeHtml(data.eval_time || data.email_date || 'N/A')}</strong>`)}
                    ${value('Tiêu Đề Thư', `<span class="text-xs text-slate-600">${escapeHtml(data.subject || 'N/A')}</span>`)}
                </div>
            `;
        }

        if (iframe) {
            iframe.srcdoc = data.raw_html || '<p style="font-family: sans-serif; padding: 20px; color: #64748b;">Không có nội dung HTML gốc.</p>';
        }

    } catch (err) {
        console.error("Lỗi chi tiết modal:", err);
        showToast("Lỗi mở chi tiết email", "error");
        if (grid) grid.innerHTML = '<div class="text-center py-5 text-red font-semibold">Lỗi mở chi tiết email</div>';
    }
}

function closeDetailModal() {
    const modal = document.getElementById('detail-modal');
    if (modal) modal.classList.remove('show');
}

function switchModalTab(tab) {
    const tabParsedBtn = document.querySelector('.modal-tabs .tab-btn:nth-child(1)');
    const tabRawBtn = document.querySelector('.modal-tabs .tab-btn:nth-child(2)');
    const tabParsedContent = document.getElementById('modal-tab-parsed');
    const tabRawContent = document.getElementById('modal-tab-raw');

    if (tab === 'parsed') {
        if (tabParsedBtn) tabParsedBtn.classList.add('active');
        if (tabRawBtn) tabRawBtn.classList.remove('active');
        if (tabParsedContent) {
            tabParsedContent.classList.remove('hidden');
            tabParsedContent.classList.add('active');
        }
        if (tabRawContent) {
            tabRawContent.classList.add('hidden');
            tabRawContent.classList.remove('active');
        }
    } else {
        if (tabRawBtn) tabRawBtn.classList.add('active');
        if (tabParsedBtn) tabParsedBtn.classList.remove('active');
        if (tabRawContent) {
            tabRawContent.classList.remove('hidden');
            tabRawContent.classList.add('active');
        }
        if (tabParsedContent) {
            tabParsedContent.classList.add('hidden');
            tabParsedContent.classList.remove('active');
        }
    }
}

// -------------------------------------------------------------
// Manual Sync Trigger
// -------------------------------------------------------------
async function triggerManualSync() {
    const btn = document.getElementById('btn-sync');
    const icon = document.getElementById('sync-icon');
    const indicator = document.getElementById('status-indicator');

    btn.disabled = true;
    icon.classList.add('fa-spin');
    indicator.classList.add('loading');
    showToast("Đang kết nối mail.fpt.net và quét thư CEM...", "info");

    try {
        const res = await fetch('/api/sync', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });

        const data = await res.json();
        if (data.success) {
            showToast(data.message, "success");
            await Promise.all([
                loadStats(),
                loadTable(1),
                loadGiucStats(),
                loadGiucTable(1)
            ]);
        } else {
            showToast(data.error || "Đồng bộ thất bại", "error");
        }
    } catch (err) {
        showToast("Lỗi kết nối máy chủ", "error");
    } finally {
        btn.disabled = false;
        icon.classList.remove('fa-spin');
        indicator.classList.remove('loading');
    }
}

// -------------------------------------------------------------
// Export Reports (Respect Date Filters & Active Tag)
// -------------------------------------------------------------
function exportReport(type) {
    toggleExportMenu();
    if (currentTag === 'giuc') {
        const params = new URLSearchParams({
            priority: currentGiucPrio,
            search: currentGiucSearch,
            date_from: currentGiucDateFrom,
            date_to: currentGiucDateTo,
            block: currentGiucBlock,
            doi_truong: currentGiucDoiTruong
        });
        window.location.href = `/api/giuc-tien-do/export/${type}?${params.toString()}`;
        return;
    }

    const onlySurvey = document.getElementById('filter-only-survey')?.checked ?? true;
    const params = new URLSearchParams({
        only_survey: onlySurvey,
        csat: currentCsatFilter,
        search: currentSearch,
        date_from: currentDateFrom,
        date_to: currentDateTo,
        block: currentCemBlock,
        doi_truong: currentCemDoiTruong
    });

    const url = `/api/export/${type}?${params.toString()}`;
    window.location.href = url;
}

// -------------------------------------------------------------
// Settings Modal
// -------------------------------------------------------------
function openSettingsModal() {
    document.getElementById('settings-modal').classList.add('show');
}

function closeSettingsModal() {
    document.getElementById('settings-modal').classList.remove('show');
}

async function saveSettings(e) {
    e.preventDefault();
    const email = document.getElementById('cfg-email').value;
    const password = document.getElementById('cfg-password').value;
    const host = document.getElementById('cfg-host').value;
    const port = parseInt(document.getElementById('cfg-port').value);

    closeSettingsModal();
    showToast("Đang lưu cấu hình và kiểm tra kết nối...", "info");

    const res = await fetch('/api/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, host, port })
    });
    const data = await res.json();
    if (data.success) {
        showToast("Lưu và kết nối thành công!", "success");
        document.getElementById('status-email').textContent = email;
        await loadStats();
        await loadTable(1);
    } else {
        showToast(data.error || "Kết nối thất bại", "error");
    }
}

// -------------------------------------------------------------
// UI Utilities
// -------------------------------------------------------------
function toggleExportMenu() {
    const m = document.getElementById('export-menu');
    m.classList.toggle('show');
}

document.addEventListener('click', (e) => {
    const wrap = document.querySelector('.export-dropdown');
    if (wrap && !wrap.contains(e.target)) {
        const m = document.getElementById('export-menu');
        if (m) m.classList.remove('show');
    }
});

function scrollToSection(id) {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: 'smooth' });
}

function showToast(msg, type = 'info') {
    const t = document.getElementById('toast');
    t.className = `toast ${type} show`;
    t.innerHTML = `<i class="fa-solid fa-circle-info text-orange"></i> <span>${escapeHtml(msg)}</span>`;
    setTimeout(() => {
        t.classList.remove('show');
    }, 4500);
}

function animateNumber(id, endVal) {
    const el = document.getElementById(id);
    if (!el) return;
    const startVal = parseInt(el.textContent) || 0;
    const duration = 500;
    const steps = 15;
    const stepVal = (endVal - startVal) / steps;
    let current = startVal;
    let count = 0;

    const interval = setInterval(() => {
        count++;
        current += stepVal;
        if (count >= steps) {
            el.textContent = endVal.toLocaleString('vi-VN');
            clearInterval(interval);
        } else {
            el.textContent = Math.round(current).toLocaleString('vi-VN');
        }
    }, duration / steps);
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;')
              .replace(/</g, '&lt;')
              .replace(/>/g, '&gt;')
              .replace(/"/g, '&quot;')
              .replace(/'/g, '&#039;');
}

// =============================================================
// GIỤC TIẾN ĐỘ CONTROLLER & DATE FILTERING
// =============================================================

function setQuickGiucDate(preset) {
    document.querySelectorAll('#view-giuc .preset-btn').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-preset') === preset);
    });

    const now = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    const toYMD = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

    if (preset === 'all') {
        currentGiucDateFrom = '';
        currentGiucDateTo = '';
    } else if (preset === 'today') {
        currentGiucDateFrom = toYMD(now);
        currentGiucDateTo = toYMD(now);
    } else if (preset === 'yesterday') {
        const yest = new Date(now);
        yest.setDate(now.getDate() - 1);
        currentGiucDateFrom = toYMD(yest);
        currentGiucDateTo = toYMD(yest);
    } else if (preset === '7days') {
        const past7 = new Date(now);
        past7.setDate(now.getDate() - 6);
        currentGiucDateFrom = toYMD(past7);
        currentGiucDateTo = toYMD(now);
    } else if (preset === 'month') {
        const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
        currentGiucDateFrom = toYMD(startOfMonth);
        currentGiucDateTo = toYMD(now);
    }

    const inputFrom = document.getElementById('filter-giuc-date-from');
    const inputTo = document.getElementById('filter-giuc-date-to');
    if (inputFrom) inputFrom.value = currentGiucDateFrom;
    if (inputTo) inputTo.value = currentGiucDateTo;

    refreshGiuc();
}

function handleGiucDateChange() {
    const inputFrom = document.getElementById('filter-giuc-date-from');
    const inputTo = document.getElementById('filter-giuc-date-to');
    currentGiucDateFrom = inputFrom ? inputFrom.value : '';
    currentGiucDateTo = inputTo ? inputTo.value : '';

    document.querySelectorAll('#view-giuc .preset-btn').forEach(btn => btn.classList.remove('active'));
    refreshGiuc();
}

function resetGiucDateFilter() {
    setQuickGiucDate('all');
}

function refreshGiuc() {
    loadGiucStats();
    loadGiucTable(1);
}

function handleGiucNsFilter() {
    currentGiucBlock = document.getElementById('filter-giuc-block')?.value || '';
    currentGiucDoiTruong = document.getElementById('filter-giuc-doi-truong')?.value || '';
    loadGiucStats();
    loadGiucTable(1);
}

async function loadGiucStats() {
    try {
        const params = new URLSearchParams({
            priority: currentGiucPrio,
            search: currentGiucSearch,
            date_from: currentGiucDateFrom,
            date_to: currentGiucDateTo,
            block: currentGiucBlock,
            doi_truong: currentGiucDoiTruong
        });
        const res = await fetch(`/api/giuc-tien-do/stats?${params.toString()}`);
        const data = await res.json();
        if (!data.success) return;

        const kpi = data.kpi;
        animateNumber('kpi-giuc-total', kpi.total_records);
        animateNumber('kpi-giuc-khan', kpi.total_khan);
        animateNumber('kpi-giuc-cao', kpi.total_cao);
        animateNumber('kpi-giuc-normal', kpi.total_normal);
        animateNumber('kpi-giuc-assignees', kpi.total_assignees);

        const badgeGiuc = document.getElementById('badge-giuc-cnt');
        if (badgeGiuc) badgeGiuc.textContent = `${kpi.total_records} ca`;
    } catch (err) {
        console.error("Error loading Giuc stats:", err);
    }
}

function formatGiucReceived(r) {
    // Hiển thị cùng mốc thời gian (ngày nhận email) với bộ lọc ngày
    if (r.timestamp_val) {
        const d = new Date(r.timestamp_val * 1000);
        const p = n => String(n).padStart(2, '0');
        return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
    }
    return r.request_time || 'N/A';
}

async function loadGiucTable(page = 1) {
    currentGiucPage = page;
    const tbody = document.getElementById('table-giuc-body');
    if (!tbody) return;

    tbody.innerHTML = `
        <tr>
            <td colspan="8" class="text-center py-5">
                <div class="loading-state">
                    <i class="fa-solid fa-circle-notch fa-spin text-orange" style="font-size: 1.5rem;"></i>
                    <p style="margin-top: 8px; color: #64748b; font-weight: 600;">Đang nạp dữ liệu giục tiến độ...</p>
                </div>
            </td>
        </tr>
    `;

    try {
        const params = new URLSearchParams({
            page: currentGiucPage,
            limit: pageSize,
            priority: currentGiucPrio,
            search: currentGiucSearch,
            date_from: currentGiucDateFrom,
            date_to: currentGiucDateTo,
            block: currentGiucBlock,
            doi_truong: currentGiucDoiTruong
        });

        const res = await fetch(`/api/giuc-tien-do?${params.toString()}`);
        const data = await res.json();


        if (!data.success) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center py-5 text-red font-semibold">Lỗi nạp dữ liệu: ${escapeHtml(data.error)}</td></tr>`;
            return;
        }

        const rows = data.records;
        const total = data.total;

        const countBadge = document.getElementById('table-giuc-count');
        if (countBadge) countBadge.textContent = `${total} bản ghi`;

        if (rows.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="8" class="text-center py-5">
                        <div class="empty-state">
                            <i class="fa-solid fa-bell-slash" style="font-size: 2rem; color: #cbd5e1;"></i>
                            <p style="margin-top: 10px; font-weight: 600; color: #64748b;">Không tìm thấy yêu cầu giục tiến độ nào phù hợp</p>
                        </div>
                    </td>
                </tr>
            `;
            updateGiucPagination(0, 0, 0);
            return;
        }

        tbody.innerHTML = rows.map((r, idx) => {
            const isCao = (r.priority || '').toLowerCase().includes('cao') || (r.priority || '').toLowerCase().includes('khẩn');
            const prioClass = isCao ? 'badge-prio-cao' : 'badge-prio-binh-thuong';
            const prioIcon = isCao ? '<i class="fa-solid fa-fire text-red"></i>' : '<i class="fa-regular fa-clock"></i>';

            const blockBadge = r.ns_block ? `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-100 text-red-700 ml-1" title="Block ${escapeHtml(r.ns_block)}">${escapeHtml(r.ns_block)}</span>` : '';
            const dtLine = r.ns_doi_truong ? `<div class="text-[11px] text-slate-500 mt-0.5" title="Đội Trưởng: ${escapeHtml(r.ns_doi_truong)}"><i class="fa-solid fa-user-shield text-[10px] text-red-500 mr-1"></i>${escapeHtml(r.ns_doi_truong)}</div>` : '';

            return `
                <tr>
                    <!-- THÔNG TIN CƠ BẢN: Nhân Viên Xử Lý -->
                    <td class="text-center" style="font-weight: 700; color: #64748b;">${(currentGiucPage - 1) * pageSize + idx + 1}</td>
                    <td class="td-basic-last">
                        <div>
                            <span class="badge-assignee">
                                <i class="fa-solid fa-user-tie"></i>
                                <strong>${escapeHtml(r.assignee || 'Chưa gán')}</strong>
                            </span>
                            ${blockBadge}
                            ${dtLine}
                        </div>
                    </td>

                    <!-- THÔNG TIN YÊU CẦU -->
                    <td>
                        <span class="badge-contract">${escapeHtml(r.contract || r.contract_no || 'N/A')}</span>
                    </td>
                    <td>
                        <code class="font-mono text-xs" style="color: #475569; font-weight: 600;">${escapeHtml(r.sr_ticket || 'N/A')}</code>
                    </td>
                    <td style="text-align: center;">
                        <span class="badge-prio ${prioClass}">
                            ${prioIcon} ${escapeHtml(r.priority || 'Bình thường')}
                        </span>
                    </td>
                    <td>
                        <div style="max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500;" title="${escapeHtml(r.request_content || '')}">
                            ${escapeHtml(r.request_content || 'N/A')}
                        </div>
                    </td>
                    <td class="td-eval-last">
                        <span style="font-size: 0.8rem; color: #64748b; font-weight: 600;">
                            <i class="fa-regular fa-clock text-xs"></i> ${escapeHtml(formatGiucReceived(r))}
                        </span>
                    </td>

                    <!-- THAO TÁC -->
                    <td style="text-align: center;">
                        <button class="btn btn-sm btn-outline" onclick="openGiucDetailModal(${r.id})" title="Xem thư gốc Outlook">
                            <i class="fa-solid fa-eye text-orange"></i> Xem
                        </button>
                    </td>
                </tr>
            `;
        }).join('');

        updateGiucPagination(total, (page - 1) * pageSize + 1, Math.min(page * pageSize, total));

    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center py-5 text-red font-semibold">Lỗi kết nối máy chủ</td></tr>`;
    }
}

function updateGiucPagination(total, start, end) {
    const info = document.getElementById('giuc-pagination-info');
    const currentEl = document.getElementById('current-giuc-page');
    const btnPrev = document.getElementById('btn-giuc-prev');
    const btnNext = document.getElementById('btn-giuc-next');

    if (total === 0) {
        if (info) info.textContent = `Hiển thị 0 - 0 của 0`;
        if (currentEl) currentEl.textContent = '1';
        if (btnPrev) btnPrev.disabled = true;
        if (btnNext) btnNext.disabled = true;
        return;
    }

    if (info) info.textContent = `Hiển thị ${start} - ${end} của ${total.toLocaleString('vi-VN')}`;
    if (currentEl) currentEl.textContent = currentGiucPage;

    const maxPage = Math.ceil(total / pageSize);
    if (btnPrev) btnPrev.disabled = currentGiucPage <= 1;
    if (btnNext) btnNext.disabled = currentGiucPage >= maxPage;
}

function changeGiucPage(delta) {
    loadGiucTable(currentGiucPage + delta);
}

function handleGiucSearch(e) {
    clearTimeout(giucSearchDebounceTimeout);
    giucSearchDebounceTimeout = setTimeout(() => {
        currentGiucSearch = document.getElementById('filter-giuc-search').value.trim();
        loadGiucTable(1);
    }, 300);
}

function clearGiucSearch() {
    const input = document.getElementById('filter-giuc-search');
    if (input) input.value = '';
    currentGiucSearch = '';
    loadGiucTable(1);
}

function filterGiucPrio(prio) {
    currentGiucPrio = prio;
    document.querySelectorAll('#view-giuc .filter-pills .pill-btn').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-prio') === prio);
    });

    // Cập nhật viền nổi bật KPI card tương ứng
    const cardTotal = document.getElementById('kpi-card-giuc-total');
    const cardKhan = document.getElementById('kpi-card-giuc-khan');
    const cardCao = document.getElementById('kpi-card-giuc-cao');
    const cardNormal = document.getElementById('kpi-card-giuc-normal');
    [cardTotal, cardKhan, cardCao, cardNormal].forEach(c => c && c.classList.remove('kpi-card-active'));

    const pLower = (prio || '').toLowerCase();
    if (!prio && cardTotal) cardTotal.classList.add('kpi-card-active');
    else if (pLower.includes('khẩn') && cardKhan) cardKhan.classList.add('kpi-card-active');
    else if (pLower.includes('cao') && cardCao) cardCao.classList.add('kpi-card-active');
    else if (pLower.includes('bình') && cardNormal) cardNormal.classList.add('kpi-card-active');

    loadGiucStats();
    loadGiucTable(1);
}

async function openGiucDetailModal(id) {
    const modal = document.getElementById('detail-modal');
    const grid = document.getElementById('modal-detail-grid');
    const iframe = document.getElementById('modal-iframe');
    const title = document.getElementById('modal-contract-title');
    const badgeType = document.getElementById('modal-badge-type');

    if (badgeType) badgeType.textContent = 'YÊU CẦU GIỤC TIẾN ĐỘ';
    if (title) title.textContent = 'Đang tải chi tiết...';
    grid.innerHTML = '<div class="text-center py-5"><i class="fa-solid fa-circle-notch fa-spin text-orange"></i> Đang tải...</div>';
    iframe.srcdoc = '';

    modal.classList.add('show');
    switchModalTab('parsed');

    try {
        const res = await fetch(`/api/giuc-tien-do/${id}`);
        const data = await res.json();

        if (!data.success) {
            grid.innerHTML = `<div class="text-center py-5 text-red font-semibold">Lỗi: ${data.error}</div>`;
            return;
        }

        const r = data.record;
        title.innerHTML = `Số HĐ: <span class="badge-contract">${escapeHtml(r.contract || r.contract_no || 'N/A')}</span> | Mã SR: <code class="font-mono text-sm">${escapeHtml(r.sr_ticket || 'N/A')}</code>`;

        grid.innerHTML = `
            <div class="detail-section">
                <h4><i class="fa-solid fa-user-tie text-green"></i> THÔNG TIN CƠ BẢN</h4>
                <div class="detail-row">
                    <span class="detail-label">Nhân Viên Xử Lý:</span>
                    <span class="detail-value font-bold text-green" style="font-size: 1rem;">${escapeHtml(r.assignee || 'Chưa gán')}</span>
                </div>
                ${r.ns_block ? `
                <div class="detail-row">
                    <span class="detail-label">Block Phân Công:</span>
                    <span class="detail-value"><span class="px-2 py-0.5 rounded text-xs font-bold bg-red-100 text-red-700">${escapeHtml(r.ns_block)}</span></span>
                </div>` : ''}
                ${r.ns_doi_truong ? `
                <div class="detail-row">
                    <span class="detail-label">Đội Trưởng:</span>
                    <span class="detail-value font-semibold text-slate-700"><i class="fa-solid fa-user-shield text-red-500 mr-1"></i>${escapeHtml(r.ns_doi_truong)}</span>
                </div>` : ''}
                ${r.ns_inside ? `
                <div class="detail-row">
                    <span class="detail-label">Inside Account:</span>
                    <span class="detail-value font-mono text-xs text-slate-600">${escapeHtml(r.ns_inside)}</span>
                </div>` : ''}
                <div class="detail-row">
                    <span class="detail-label">Email Người Gửi:</span>
                    <span class="detail-value font-mono">${escapeHtml(r.from_sender || r.sender || 'N/A')}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Người Nhận (To):</span>
                    <span class="detail-value font-mono text-xs">${escapeHtml(r.recipients_to || 'N/A')}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Người Đồng Kính (Cc):</span>
                    <span class="detail-value font-mono text-xs">${escapeHtml(r.recipients_cc || 'N/A')}</span>
                </div>
            </div>

            <div class="detail-section">
                <h4><i class="fa-solid fa-file-invoice text-orange"></i> THÔNG TIN YÊU CẦU</h4>
                <div class="detail-row">
                    <span class="detail-label">Số Hợp Đồng:</span>
                    <span class="detail-value badge-contract" style="display:inline-block;">${escapeHtml(r.contract || r.contract_no || 'N/A')}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Mã SR/Ticket:</span>
                    <span class="detail-value font-mono font-bold">${escapeHtml(r.sr_ticket || 'N/A')}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Độ Ưu Tiên:</span>
                    <span class="detail-value">
                        <span class="badge-prio ${(r.priority || '').toLowerCase().includes('cao') || (r.priority || '').toLowerCase().includes('khẩn') ? 'badge-prio-cao' : 'badge-prio-binh-thuong'}">
                            ${escapeHtml(r.priority || 'Bình thường')}
                        </span>
                    </span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Thời Gian Gửi YC:</span>
                    <span class="detail-value font-semibold">${escapeHtml(r.request_time || 'N/A')}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Nội Dung Yêu Cầu:</span>
                    <span class="detail-value font-semibold" style="color: #0f172a;">${escapeHtml(r.request_content || 'N/A')}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Tiêu Đề Mail:</span>
                    <span class="detail-value">${escapeHtml(r.subject || 'N/A')}</span>
                </div>
            </div>
        `;

        if (r.raw_html) {
            iframe.srcdoc = r.raw_html;
        } else {
            iframe.srcdoc = '<p style="padding: 20px; font-family: sans-serif; color: #64748b;">Không có nội dung HTML gốc.</p>';
        }

    } catch (err) {
        grid.innerHTML = '<div class="text-center py-5 text-red font-semibold">Lỗi kết nối máy chủ</div>';
    }
}

// =============================================================
// CLL >3 — Checklist Bảo trì
// =============================================================
function cllDateYmd(date) {
    const pad = n => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
function setQuickCllDate(preset) {
    document.querySelectorAll('#view-cll .preset-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.preset === preset));
    const now = new Date();
    if (preset === 'all') [currentCllDateFrom, currentCllDateTo] = ['', ''];
    if (preset === 'today') [currentCllDateFrom, currentCllDateTo] = [cllDateYmd(now), cllDateYmd(now)];
    if (preset === '7days') { const d = new Date(now); d.setDate(d.getDate() - 6); [currentCllDateFrom, currentCllDateTo] = [cllDateYmd(d), cllDateYmd(now)]; }
    if (preset === 'month') [currentCllDateFrom, currentCllDateTo] = [cllDateYmd(new Date(now.getFullYear(), now.getMonth(), 1)), cllDateYmd(now)];
    document.getElementById('filter-cll-date-from').value = currentCllDateFrom;
    document.getElementById('filter-cll-date-to').value = currentCllDateTo;
    refreshCll();
}
function handleCllDateChange() {
    currentCllDateFrom = document.getElementById('filter-cll-date-from').value;
    currentCllDateTo = document.getElementById('filter-cll-date-to').value;
    document.querySelectorAll('#view-cll .preset-btn').forEach(btn => btn.classList.remove('active'));
    refreshCll();
}
function handleCllNsFilter() {
    currentCllBlock = document.getElementById('filter-cll-block')?.value || '';
    currentCllDoiTruong = document.getElementById('filter-cll-doi-truong')?.value || '';
    refreshCll();
}
function handleCllSearch() {
    clearTimeout(cllSearchDebounceTimeout);
    cllSearchDebounceTimeout = setTimeout(() => { currentCllSearch = document.getElementById('filter-cll-search').value.trim(); refreshCll(); }, 300);
}
function refreshCll() { loadCllStats(); loadCllTable(1); }
function formatCllReceived(r) {
    if (!r.timestamp_val) return r.email_date || 'N/A';
    return new Date(r.timestamp_val * 1000).toLocaleString('vi-VN');
}
async function loadCllStats() {
    try {
        const p = new URLSearchParams({
            search: currentCllSearch,
            date_from: currentCllDateFrom,
            date_to: currentCllDateTo,
            block: currentCllBlock,
            doi_truong: currentCllDoiTruong
        });
        const data = await (await fetch(`/api/cll/stats?${p}`)).json();
        if (!data.success) return;
        animateNumber('kpi-cll-total', data.kpi.total);
        animateNumber('kpi-cll-contracts', data.kpi.contracts);
        animateNumber('kpi-cll-max', data.kpi.max_occurrences);
        const badge = document.getElementById('badge-cll-cnt'); if (badge) badge.textContent = `${data.kpi.total} ca`;
    } catch (err) { console.error('Error loading CLL stats:', err); }
}
async function loadCllTable(page = 1) {
    currentCllPage = page;
    const body = document.getElementById('table-cll-body'); if (!body) return;
    body.innerHTML = '<tr><td colspan="7" class="text-center py-8 text-slate-500"><i class="fa-solid fa-circle-notch fa-spin"></i> Đang nạp dữ liệu...</td></tr>';
    try {
        const p = new URLSearchParams({
            page,
            limit: pageSize,
            search: currentCllSearch,
            date_from: currentCllDateFrom,
            date_to: currentCllDateTo,
            block: currentCllBlock,
            doi_truong: currentCllDoiTruong
        });
        const data = await (await fetch(`/api/cll?${p}`)).json();
        const rows = data.records || [];
        document.getElementById('table-cll-count').textContent = `${data.total || 0} bản ghi`;
        if (!rows.length) body.innerHTML = '<tr><td colspan="7" class="text-center py-8 text-slate-500">Không có mail CLL &gt;3 phù hợp</td></tr>';
        else body.innerHTML = rows.map((r, i) => {
            const nvDisplay = r.ns_nv_name
                ? `<span class="font-bold text-slate-800">${escapeHtml(r.ns_nv_name)}</span>`
                : (r.staff ? `<span class="font-bold text-slate-700">${escapeHtml(r.staff)}</span>` : '<span class="text-slate-400 italic">Chưa xác định</span>');
            const insideSub = (r.staff && r.ns_nv_name) ? `<div class="text-[11px] text-slate-500 font-mono">${escapeHtml(r.staff)}</div>` : '';
            const dtLine = r.ns_doi_truong
                ? `<div class="text-[11px] text-slate-600 mt-0.5" title="Đội Trưởng: ${escapeHtml(r.ns_doi_truong)}"><i class="fa-solid fa-user-shield text-[10px] text-violet-500 mr-1"></i>${escapeHtml(r.ns_doi_truong)}${r.ns_block ? ' · <span class="text-slate-400">' + escapeHtml(r.ns_block) + '</span>' : ''}</div>`
                : (r.ns_block ? `<div class="text-[11px] text-slate-400 mt-0.5"><i class="fa-solid fa-building text-[10px] mr-1"></i>${escapeHtml(r.ns_block)}</div>` : '');

            return `<tr>
                <td class="text-center font-bold text-slate-500">${(page - 1) * pageSize + i + 1}</td>
                <td><span class="badge-contract">${escapeHtml(r.contract)}</span></td>
                <td>${nvDisplay}${insideSub}${dtLine}</td>
                <td class="text-center"><span class="badge-prio badge-prio-cao">${r.occurrence_count} lần</span></td>
                <td>${escapeHtml(r.initial_status || 'Chưa có')}</td>
                <td>${escapeHtml(formatCllReceived(r))}</td>
                <td class="text-center"><button class="btn btn-sm btn-outline" onclick="openCllDetailModal(${r.id})"><i class="fa-solid fa-eye text-violet-600"></i> Xem</button></td>
            </tr>`;
        }).join('');
        updateCllPagination(data.total || 0);
    } catch (err) { body.innerHTML = '<tr><td colspan="7" class="text-center py-8 text-red-600">Lỗi kết nối máy chủ</td></tr>'; }
}
function updateCllPagination(total) {
    const start = total ? (currentCllPage - 1) * pageSize + 1 : 0, end = Math.min(currentCllPage * pageSize, total);
    document.getElementById('cll-pagination-info').textContent = `Hiển thị ${start} - ${end} của ${total}`;
    document.getElementById('current-cll-page').textContent = currentCllPage;
    document.getElementById('btn-cll-prev').disabled = currentCllPage <= 1;
    document.getElementById('btn-cll-next').disabled = currentCllPage >= Math.ceil(total / pageSize);
}
function changeCllPage(delta) { loadCllTable(currentCllPage + delta); }
async function openCllDetailModal(id) {
    const modal = document.getElementById('detail-modal'), grid = document.getElementById('modal-detail-grid'), iframe = document.getElementById('modal-iframe');
    document.getElementById('modal-badge-type').textContent = 'CLL >3';
    document.getElementById('modal-contract-title').textContent = 'Đang tải chi tiết...';
    grid.innerHTML = '<div class="text-center py-5"><i class="fa-solid fa-circle-notch fa-spin text-violet-600"></i> Đang đọc Supabase...</div>';
    iframe.srcdoc = ''; modal.classList.add('show'); switchModalTab('parsed');
    try {
        const data = await (await fetch(`/api/cll/${id}`)).json();
        if (!data.success) { grid.innerHTML = `<div class="text-center py-5 text-red-600">${escapeHtml(data.error || 'Không thể tải chi tiết')}</div>`; return; }
        const r = data.record, occurrences = r.occurrences || [];
        document.getElementById('modal-contract-title').innerHTML = `Số HĐ: <span class="badge-contract">${escapeHtml(r.contract)}</span> · ${r.occurrence_count} lần phát sinh`;
        const value = (label, val) => `<div class="detail-row"><span class="detail-label">${label}</span><span class="detail-value">${escapeHtml(String(val || 'N/A'))}</span></div>`;
        const occurrenceRows = occurrences.length ? occurrences.map((x, i) => `<tr><td>${i + 1}</td><td>${escapeHtml(String(x.staff || ''))}</td><td>${escapeHtml(String(x.created_at || ''))}</td><td>${escapeHtml(String(x.completed_at || ''))}</td><td>${escapeHtml(String(x.cc_note || ''))}</td><td>${escapeHtml(String(x.staff_note || ''))}</td></tr>`).join('') : '<tr><td colspan="6" class="text-center text-slate-500">Không có lần hoàn tất nào trong 30 ngày trước khi nhận mail.</td></tr>';
        const techVal = r.ns_nv_name ? `${r.ns_nv_name} (${r.staff || r.ns_inside})` : (r.staff || 'Chưa xác định');
        grid.innerHTML = `<div class="detail-section md:col-span-2">
            <h4><i class="fa-solid fa-id-card text-violet-600"></i> THÔNG TIN CƠ BẢN</h4>
            ${value('Số hợp đồng', r.contract)}
            ${value('Kỹ thuật viên', techVal)}
            ${value('Đội Trưởng', r.ns_doi_truong || 'Chưa xác định')}
            ${value('Block', r.ns_block || 'Chưa xác định')}
            ${value('Số lần phát sinh', `${r.occurrence_count} lần`)}
            ${value('Thời điểm nhận mail', formatCllReceived(r))}
            ${value('Tình trạng ban đầu', r.initial_status)}
        </div>
        <div class="detail-section md:col-span-2">
            <h4><i class="fa-solid fa-clock-rotate-left text-violet-600"></i> THÔNG TIN PHÁT SINH — 30 NGÀY GẦN NHẤT</h4>
            <div class="overflow-x-auto">
                <table class="data-table w-full text-xs">
                    <thead><tr><th>STT</th><th>Nhân viên</th><th>TG tạo</th><th>TG HT</th><th>Ghi chú CC</th><th>Ghi chú nhân viên</th></tr></thead>
                    <tbody>${occurrenceRows}</tbody>
                </table>
            </div>
        </div>`;
        iframe.srcdoc = r.raw_html || '<p>Không có email gốc.</p>';
    } catch (err) { grid.innerHTML = '<div class="text-center py-5 text-red-600">Lỗi kết nối máy chủ</div>'; }
}

// =============================================================
// NHÂN SỰ — Google Sheets Chi Nhánh Sài Gòn 01
// =============================================================

async function loadNhanSuMeta() {
    try {
        const res = await fetch('/api/nhansu/meta');
        const data = await res.json();
        if (!data.success) return;

        // Populate Block dropdowns (filter + modal across all views)
        const blockDropdowns = [
            { id: 'filter-ns-block', val: currentNsBlock },
            { id: 'ns-mail-block', val: '' },
            { id: 'filter-cem-block', val: currentCemBlock },
            { id: 'filter-giuc-block', val: currentGiucBlock },
            { id: 'filter-cll-block', val: currentCllBlock }
        ];
        blockDropdowns.forEach(({ id, val }) => {
            const sel = document.getElementById(id);
            if (!sel) return;
            const cur = sel.value || val || '';
            sel.innerHTML = `<option value="">Tất cả Block</option>`;
            data.blocks.forEach(b => {
                const o = document.createElement('option');
                o.value = b; o.textContent = b;
                if (b === cur) o.selected = true;
                sel.appendChild(o);
            });
        });

        // Populate Đội Trưởng dropdowns across all views
        const dtDropdowns = [
            { id: 'filter-ns-doi-truong', val: currentNsDoiTruong },
            { id: 'ns-mail-doi-truong', val: '' },
            { id: 'filter-cem-doi-truong', val: currentCemDoiTruong },
            { id: 'filter-giuc-doi-truong', val: currentGiucDoiTruong },
            { id: 'filter-cll-doi-truong', val: currentCllDoiTruong }
        ];
        dtDropdowns.forEach(({ id, val }) => {
            const sel = document.getElementById(id);
            if (!sel) return;
            const cur = sel.value || val || '';
            sel.innerHTML = `<option value="">Tất cả Đội Trưởng</option>`;
            data.doi_truongs.forEach(dt => {
                const o = document.createElement('option');
                o.value = dt; o.textContent = dt;
                if (dt === cur) o.selected = true;
                sel.appendChild(o);
            });
        });

        // KPI cards
        const kpiBlocks = document.getElementById('kpi-ns-blocks');
        const kpiDt     = document.getElementById('kpi-ns-doi-truong');
        if (kpiBlocks) kpiBlocks.textContent = data.blocks.length;
        if (kpiDt)     kpiDt.textContent     = data.doi_truongs.length;

        // Sidebar badge
        const badge = document.getElementById('badge-nhansu-cnt');
        if (badge) badge.textContent = `${data.total} NV`;
    } catch(e) { console.error('[NhanSu] Meta error:', e); }
}

async function loadNhanSuTable(page = 1) {
    currentNsPage = page;
    const tbody = document.getElementById('table-ns-body');
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="11" class="text-center py-8">
        <i class="fa-solid fa-circle-notch fa-spin text-teal-500 text-xl"></i>
        <p class="mt-2 text-xs text-slate-500">Đang tải...</p></td></tr>`;

    try {
        const params = new URLSearchParams({
            block:       currentNsBlock,
            doi_truong:  currentNsDoiTruong,
            search:      currentNsSearch,
            page:        page,
            limit:       NS_PAGE_SIZE
        });
        const res  = await fetch(`/api/nhansu?${params}`);
        const data = await res.json();
        if (!data.success) {
            tbody.innerHTML = `<tr><td colspan="11" class="text-center py-8 text-red-500">${data.error || 'Lỗi tải dữ liệu'}</td></tr>`;
            return;
        }

        // KPI total
        const kpiTotal = document.getElementById('kpi-ns-total');
        if (kpiTotal) kpiTotal.textContent = data.total;
        const cntBadge = document.getElementById('table-ns-count');
        if (cntBadge) cntBadge.textContent = `${data.total} NV`;
        const sideBadge = document.getElementById('badge-nhansu-cnt');
        if (sideBadge) sideBadge.textContent = `${data.total} NV`;

        if (!data.data || !data.data.length) {
            tbody.innerHTML = `<tr><td colspan="11" class="text-center py-10 text-slate-400">
                <i class="fa-solid fa-users-slash text-3xl mb-2 block"></i>
                Không tìm thấy nhân viên nào theo bộ lọc hiện tại.
            </td></tr>`;
            updateNsPagination(0);
            return;
        }

        tbody.innerHTML = data.data.map(r => `
        <tr class="hover:bg-teal-50/30 transition-colors">
            <td class="py-2.5 px-3 font-semibold text-slate-900 whitespace-nowrap">${escapeHtml(r.nv || '—')}</td>
            <td class="py-2.5 px-3 font-mono text-xs text-slate-600">${escapeHtml(r.ma_nv || '—')}</td>
            <td class="py-2.5 px-3 text-slate-500">${escapeHtml(r.inside_account || '—')}</td>
            <td class="py-2.5 px-3 text-slate-600">${escapeHtml(r.sdt || '—')}</td>
            <td class="py-2.5 px-3 text-blue-600 border-r-2 border-teal-200">
                ${r.email ? `<a href="mailto:${escapeHtml(r.email)}" class="hover:underline">${escapeHtml(r.email)}</a>` : '—'}
            </td>
            <td class="py-2.5 px-3">
                ${r.block ? `<span class="px-2 py-0.5 rounded-md text-xs font-bold bg-orange-100 text-orange-700">${escapeHtml(r.block)}</span>` : '—'}
            </td>
            <td class="py-2.5 px-3 text-slate-700 whitespace-nowrap">${escapeHtml(r.doi_truong || '—')}</td>
            <td class="py-2.5 px-3 text-slate-600 border-r-2 border-orange-200">${escapeHtml(r.chuc_danh || '—')}</td>
            <td class="py-2.5 px-3 text-slate-500">${escapeHtml(r.loai_hd || '—')}</td>
            <td class="py-2.5 px-3">${renderNsTtHd(r.tt_hd)}</td>
            <td class="py-2.5 px-3 text-slate-500 whitespace-nowrap">${escapeHtml(r.ngay_vao || '—')}</td>
        </tr>`).join('');

        updateNsPagination(data.total);
    } catch(e) {
        console.error('[NhanSu] Table error:', e);
        tbody.innerHTML = `<tr><td colspan="11" class="text-center py-8 text-red-500">Lỗi kết nối máy chủ.</td></tr>`;
    }
}

function renderNsTtHd(val) {
    if (!val) return '—';
    const v = val.toLowerCase();
    if (v.includes('đang') || v.includes('hoạt') || v.includes('active'))
        return `<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-700">${escapeHtml(val)}</span>`;
    if (v.includes('chờ') || v.includes('pending') || v.includes('tạm'))
        return `<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-700">${escapeHtml(val)}</span>`;
    if (v.includes('nghỉ') || v.includes('kết thúc') || v.includes('inactive'))
        return `<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-100 text-red-700">${escapeHtml(val)}</span>`;
    return `<span class="text-slate-600">${escapeHtml(val)}</span>`;
}

function updateNsPagination(total) {
    const start = total ? (currentNsPage - 1) * NS_PAGE_SIZE + 1 : 0;
    const end   = Math.min(currentNsPage * NS_PAGE_SIZE, total);
    const info  = document.getElementById('ns-pagination-info');
    const cur   = document.getElementById('current-ns-page');
    const prev  = document.getElementById('btn-ns-prev');
    const next  = document.getElementById('btn-ns-next');
    if (info) info.textContent = `Hiển thị ${start} - ${end} của ${total}`;
    if (cur)  cur.textContent  = currentNsPage;
    if (prev) prev.disabled    = currentNsPage <= 1;
    if (next) next.disabled    = currentNsPage >= Math.ceil(total / NS_PAGE_SIZE);
}

function changeNsPage(delta) {
    loadNhanSuTable(currentNsPage + delta);
}

function handleNsFilter() {
    currentNsBlock      = document.getElementById('filter-ns-block')?.value || '';
    currentNsDoiTruong  = document.getElementById('filter-ns-doi-truong')?.value || '';
    loadNhanSuTable(1);
}

function handleNsSearch(event) {
    clearTimeout(nsSearchDebounceTimeout);
    nsSearchDebounceTimeout = setTimeout(() => {
        currentNsSearch = document.getElementById('filter-ns-search')?.value?.trim() || '';
        loadNhanSuTable(1);
    }, 350);
}

function clearNsSearch() {
    const el = document.getElementById('filter-ns-search');
    if (el) el.value = '';
    currentNsSearch = '';
    loadNhanSuTable(1);
}

async function refreshNhanSu() {
    const icon = document.getElementById('ns-refresh-icon');
    if (icon) icon.classList.add('fa-spin');
    try {
        const res  = await fetch('/api/nhansu/refresh', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast(`✓ Đã làm mới — ${data.total} bản ghi`, 'success');
            await loadNhanSuMeta();
            loadNhanSuTable(1);
        } else {
            showToast('Lỗi làm mới Sheet: ' + (data.error || ''), 'error');
        }
    } catch(e) {
        showToast('Lỗi kết nối máy chủ', 'error');
    } finally {
        if (icon) icon.classList.remove('fa-spin');
    }
}

// ── Modal Gửi Mail ──
function openNsSendMailModal() {
    // Sync current filter to modal selects
    const modalBlock = document.getElementById('ns-mail-block');
    const modalDt    = document.getElementById('ns-mail-doi-truong');
    if (modalBlock) modalBlock.value = currentNsBlock;
    if (modalDt)    modalDt.value    = currentNsDoiTruong;
    const modal = document.getElementById('ns-mail-modal');
    if (modal) { modal.classList.remove('hidden'); modal.classList.add('flex'); }
}

function closeNsSendMailModal() {
    const modal = document.getElementById('ns-mail-modal');
    if (modal) { modal.classList.add('hidden'); modal.classList.remove('flex'); }
}

async function sendNsMail() {
    const subject    = document.getElementById('ns-mail-subject')?.value?.trim();
    const block      = document.getElementById('ns-mail-block')?.value || '';
    const doiTruong  = document.getElementById('ns-mail-doi-truong')?.value || '';
    const extraRaw   = document.getElementById('ns-mail-extra')?.value || '';
    const extraTo    = extraRaw.split('\n').map(e => e.trim()).filter(e => e && e.includes('@'));

    if (!subject) { showToast('Vui lòng nhập tiêu đề mail!', 'error'); return; }

    const btn = document.getElementById('btn-ns-send-mail');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang gửi...'; }

    try {
        const res  = await fetch('/api/nhansu/send-mail', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ subject, block, doi_truong: doiTruong, extra_to: extraTo })
        });
        const data = await res.json();
        if (data.success) {
            showToast(`✓ Đã gửi mail đến ${(data.sent_to || []).length} địa chỉ!`, 'success');
            closeNsSendMailModal();
        } else {
            showToast('Lỗi gửi mail: ' + (data.error || 'Không xác định'), 'error');
        }
    } catch(e) {
        showToast('Lỗi kết nối máy chủ', 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Gửi Ngay'; }
    }
}

// Close modals khi click backdrop
document.addEventListener('click', function(e) {
    const modal = document.getElementById('ns-mail-modal');
    if (modal && e.target === modal) closeNsSendMailModal();
    const detailModal = document.getElementById('detail-modal');
    if (detailModal && e.target === detailModal) closeDetailModal();
    const auImportModal = document.getElementById('au-import-modal');
    if (auImportModal && e.target === auImportModal) closeAuImportModal();
    const auRecordModal = document.getElementById('au-record-modal');
    if (auRecordModal && e.target === auRecordModal) closeAuRecordModal();
});


// =========================================================================
// TRA CỨU AU: LOGIC, TÌM KIẾM NHANH, IMPORT & CRUD
// =========================================================================
let currentAuPage = 1;
let currentAuLimit = 30;
let auSearchDebounceTimer = null;
let currentAuData = [];
let selectedAuFile = null;

// Cập nhật các card thống kê KPI AU theo đúng bộ lọc đang chọn
function updateAuKpiCards(s) {
    if (!s) return;
    const elTotal = document.getElementById('kpi-au-total');
    const elContracts = document.getElementById('kpi-au-contracts');
    const elTapDiem = document.getElementById('kpi-au-tap-diem');
    const elTstc = document.getElementById('kpi-au-tstc');
    const elBlocks = document.getElementById('kpi-au-blocks');
    const badgeCnt = document.getElementById('badge-au-cnt');

    if (elTotal) elTotal.textContent = Number(s.total || 0).toLocaleString();
    if (elContracts) elContracts.textContent = Number(s.contracts || 0).toLocaleString();
    if (elTapDiem) elTapDiem.textContent = Number(s.tap_diems || 0).toLocaleString();
    if (elTstc) elTstc.textContent = Number(s.tstcs || 0).toLocaleString();
    if (elBlocks) elBlocks.textContent = Number(s.blocks || 0).toLocaleString();
    if (badgeCnt) badgeCnt.textContent = Number(s.total || 0).toLocaleString();
}

// Tải số liệu thống kê AU (chạy theo bộ lọc)
async function loadAuStats() {
    try {
        const params = getAuQueryParams(1);
        const res = await fetch(`/api/au/stats?${params.toString()}`);
        const data = await res.json();
        if (data.success && data.stats) {
            updateAuKpiCards(data.stats);
        }
    } catch (e) {
        console.error('Lỗi tải thống kê AU:', e);
    }
}

// Tải danh sách Block & KTV vào bộ lọc
async function loadAuFilters() {
    try {
        const res = await fetch('/api/au/filters');
        const data = await res.json();
        if (data.success) {
            const blockSelect = document.getElementById('filter-au-block');
            if (blockSelect) {
                const curVal = blockSelect.value;
                blockSelect.innerHTML = '<option value="">Tất cả Block</option>';
                (data.blocks || []).forEach(b => {
                    const opt = document.createElement('option');
                    opt.value = b;
                    opt.textContent = b;
                    if (b === curVal) opt.selected = true;
                    blockSelect.appendChild(opt);
                });
            }
        }
    } catch (e) {
        console.error('Lỗi tải bộ lọc AU:', e);
    }
}

// Lấy tham số truy vấn tìm kiếm hiện tại
function getAuQueryParams(page = 1) {
    const smartSearch = (document.getElementById('filter-au-smart-search')?.value || '').trim();
    const soHopDong = (document.getElementById('filter-au-so-hop-dong')?.value || '').trim();
    const tapDiem = (document.getElementById('filter-au-tap-diem')?.value || '').trim();
    const tstc = (document.getElementById('filter-au-tstc')?.value || '').trim();
    const duong = (document.getElementById('filter-au-duong')?.value || '').trim();
    const ktv = (document.getElementById('filter-au-ktv')?.value || '').trim();
    const block = (document.getElementById('filter-au-block')?.value || '').trim();

    const params = new URLSearchParams();
    if (smartSearch) params.set('search', smartSearch);
    if (soHopDong) params.set('so_hop_dong', soHopDong);
    if (tapDiem) params.set('tap_diem', tapDiem);
    if (tstc) params.set('tstc', tstc);
    if (duong) params.set('duong', duong);
    if (ktv) params.set('ktv', ktv);
    if (block) params.set('block', block);
    params.set('page', page);
    params.set('limit', currentAuLimit);

    return params;
}

// Tải bảng dữ liệu tra cứu AU
async function loadAuTable(page = 1) {
    currentAuPage = page;
    const tbody = document.getElementById('table-au-body');
    if (!tbody) return;

    tbody.innerHTML = `
        <tr>
            <td colspan="8" class="text-center py-8 text-slate-400">
                <i class="fa-solid fa-spinner fa-spin text-xl text-blue-500 mb-2"></i>
                <div>Đang tra cứu dữ liệu AU...</div>
            </td>
        </tr>
    `;

    try {
        const params = getAuQueryParams(page);
        const res = await fetch(`/api/au?${params.toString()}`);
        const data = await res.json();

        if (!data.success) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="8" class="text-center py-6 text-red-500 font-semibold">
                        <i class="fa-solid fa-triangle-exclamation mr-1"></i> ${data.error || 'Lỗi tải dữ liệu'}
                    </td>
                </tr>
            `;
            return;
        }

        // Cập nhật thời gian truy vấn
        const elTime = document.getElementById('au-query-time');
        if (elTime) elTime.textContent = `${data.query_time_ms || 0} ms`;

        // Cập nhật số lượng
        const tableCnt = document.getElementById('table-au-count');
        if (tableCnt) tableCnt.textContent = `${Number(data.total || 0).toLocaleString()} bản ghi`;

        // Cập nhật ngay các card KPI theo đúng bộ lọc
        if (data.stats) {
            updateAuKpiCards(data.stats);
        }

        currentAuData = data.records || [];
        renderAuTable(data);

    } catch (e) {
        console.error('Lỗi khi tra cứu AU:', e);
        tbody.innerHTML = `
            <tr>
                <td colspan="8" class="text-center py-6 text-red-500 font-semibold">
                    Lỗi kết nối máy chủ khi tra cứu AU
                </td>
            </tr>
        `;
    }
}

// Render dữ liệu lên bảng
function renderAuTable(data) {
    const tbody = document.getElementById('table-au-body');
    const records = data.records || [];
    const total = data.total || 0;
    const page = data.page || 1;
    const limit = data.limit || currentAuLimit;
    const totalPages = data.total_pages || 1;

    // Phân trang info
    const info = document.getElementById('au-pagination-info');
    const fromIdx = total > 0 ? (page - 1) * limit + 1 : 0;
    const toIdx = Math.min(page * limit, total);
    if (info) info.textContent = `Hiển thị ${fromIdx} - ${toIdx} của ${total.toLocaleString()}`;

    const curPageEl = document.getElementById('current-au-page');
    const totalPagesEl = document.getElementById('total-au-pages');
    const btnPrev = document.getElementById('btn-au-prev');
    const btnNext = document.getElementById('btn-au-next');

    if (curPageEl) curPageEl.textContent = page;
    if (totalPagesEl) totalPagesEl.textContent = totalPages;
    if (btnPrev) btnPrev.disabled = (page <= 1);
    if (btnNext) btnNext.disabled = (page >= totalPages);

    if (records.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" class="text-center py-10 text-slate-400">
                    <i class="fa-solid fa-folder-open text-2xl mb-2 text-slate-300"></i>
                    <div class="text-xs font-semibold">Không tìm thấy bản ghi AU nào phù hợp</div>
                    <div class="text-[11px] text-slate-400 mt-1">Hãy thử nhập từ khóa khác hoặc bấm "Import Excel/CSV" để nạp dữ liệu</div>
                </td>
            </tr>
        `;
        return;
    }

    const smartKw = (document.getElementById('filter-au-smart-search')?.value || '').trim();

    tbody.innerHTML = records.map((r, idx) => {
        const id = r.id;
        const stt = (currentAuPage - 1) * currentAuLimit + idx + 1;
        const shd = escapeHtml(r.so_hop_dong || '');
        const td = escapeHtml(r.tap_diem || '');
        const tstc = escapeHtml(r.tstc || '');
        const duong = escapeHtml(r.duong || '');
        const ktv = escapeHtml(r.ktv_t10 || '');
        const block = escapeHtml(r.block || '');

        return `
            <tr class="hover:bg-blue-50/40 transition-colors">
                <td class="py-2.5 px-3 text-center font-bold text-slate-500">${stt}</td>
                <td class="py-2.5 px-3">
                    <div class="flex items-center gap-1.5">
                        <span class="font-bold text-blue-700 tracking-tight font-mono">${highlightKeyword(shd, smartKw)}</span>
                        ${shd ? `<button onclick="copyToClipboard('${shd}', 'Số HĐ')" class="text-slate-400 hover:text-blue-600 transition-colors" title="Sao chép"><i class="fa-regular fa-copy text-[11px]"></i></button>` : ''}
                    </div>
                </td>
                <td class="py-2.5 px-3">
                    <div class="flex items-center gap-1.5">
                        <span class="font-semibold text-slate-800">${highlightKeyword(td, smartKw)}</span>
                        ${td ? `<button onclick="copyToClipboard('${td}', 'Tập điểm')" class="text-slate-400 hover:text-blue-600 transition-colors" title="Sao chép"><i class="fa-regular fa-copy text-[11px]"></i></button>` : ''}
                    </div>
                </td>
                <td class="py-2.5 px-3">
                    <div class="flex items-center gap-1.5">
                        <span class="font-mono font-bold text-violet-700 bg-violet-50 px-1.5 py-0.5 rounded border border-violet-200">${highlightKeyword(tstc, smartKw)}</span>
                        ${tstc ? `<button onclick="copyToClipboard('${tstc}', 'TSTC')" class="text-slate-400 hover:text-violet-600 transition-colors" title="Sao chép"><i class="fa-regular fa-copy text-[11px]"></i></button>` : ''}
                    </div>
                </td>
                <td class="py-2.5 px-3 text-slate-700 font-medium">${highlightKeyword(duong, smartKw)}</td>
                <td class="py-2.5 px-3 text-slate-800 font-semibold">${highlightKeyword(ktv, smartKw)}</td>
                <td class="py-2.5 px-3">
                    ${block ? `<span class="px-2 py-0.5 rounded-full text-[11px] font-bold bg-teal-50 text-teal-700 border border-teal-200">${block}</span>` : '<span class="text-slate-300">-</span>'}
                </td>
                <td class="py-2.5 px-3 text-center whitespace-nowrap">
                    <div class="flex items-center justify-center gap-1">
                        <button onclick="openAuEditModal(${id})" class="p-1.5 rounded hover:bg-slate-100 text-slate-500 hover:text-blue-600 transition-colors" title="Chỉnh sửa bản ghi">
                            <i class="fa-solid fa-pen-to-square text-xs"></i>
                        </button>
                        <button onclick="deleteAuRecord(${id})" class="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600 transition-colors" title="Xóa bản ghi (Yêu cầu mật khẩu)">
                            <i class="fa-regular fa-trash-can text-xs"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

// Highlight từ khóa tìm kiếm
function highlightKeyword(text, keyword) {
    if (!text || !keyword) return text;
    try {
        const regex = new RegExp(`(${keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
        return text.replace(regex, '<mark class="bg-yellow-200 text-slate-900 rounded px-0.5 font-bold">$1</mark>');
    } catch (e) {
        return text;
    }
}

// Xử lý tìm kiếm thông minh nhanh (Debounced 150ms để gõ siêu mượt)
function handleAuSmartSearch(e) {
    const val = (e.target.value || '').trim();
    const btnClear = document.getElementById('btn-clear-au-smart');
    if (btnClear) {
        if (val) btnClear.classList.remove('hidden');
        else btnClear.classList.add('hidden');
    }

    clearTimeout(auSearchDebounceTimer);
    auSearchDebounceTimer = setTimeout(() => {
        loadAuTable(1);
    }, 150);
}

function clearAuSmartSearch() {
    const input = document.getElementById('filter-au-smart-search');
    if (input) input.value = '';
    const btnClear = document.getElementById('btn-clear-au-smart');
    if (btnClear) btnClear.classList.add('hidden');
    loadAuTable(1);
}

// Xử lý bộ lọc chi tiết
function handleAuDetailFilter() {
    clearTimeout(auSearchDebounceTimer);
    auSearchDebounceTimer = setTimeout(() => {
        loadAuTable(1);
    }, 200);
}

// Đặt lại bộ lọc
function resetAuFilters() {
    const smart = document.getElementById('filter-au-smart-search');
    const shd = document.getElementById('filter-au-so-hop-dong');
    const td = document.getElementById('filter-au-tap-diem');
    const tstc = document.getElementById('filter-au-tstc');
    const duong = document.getElementById('filter-au-duong');
    const ktv = document.getElementById('filter-au-ktv');
    const block = document.getElementById('filter-au-block');
    const btnClear = document.getElementById('btn-clear-au-smart');

    if (smart) smart.value = '';
    if (shd) shd.value = '';
    if (td) td.value = '';
    if (tstc) tstc.value = '';
    if (duong) duong.value = '';
    if (ktv) ktv.value = '';
    if (block) block.value = '';
    if (btnClear) btnClear.classList.add('hidden');

    loadAuTable(1);
}

// Đổi trang
function changeAuPage(delta) {
    const newPage = currentAuPage + delta;
    if (newPage >= 1) {
        loadAuTable(newPage);
    }
}

// Đổi số dòng / trang
function changeAuPageSize() {
    const sel = document.getElementById('au-page-size');
    if (sel) {
        currentAuLimit = parseInt(sel.value, 10) || 30;
        loadAuTable(1);
    }
}

// Export menu toggle
function toggleAuExportMenu() {
    const menu = document.getElementById('au-export-menu');
    if (menu) menu.classList.toggle('hidden');
}

// Xuất file báo cáo AU
function exportAuReport(format) {
    toggleAuExportMenu();
    const params = getAuQueryParams(1);
    const url = format === 'csv' ? `/api/au/export/csv?${params.toString()}` : `/api/au/export/excel?${params.toString()}`;
    window.location.href = url;
}

// Modal Import AU
function openAuImportModal() {
    selectedAuFile = null;
    const modal = document.getElementById('au-import-modal');
    const fileInput = document.getElementById('au-file-input');
    const label = document.getElementById('au-file-name-label');
    const status = document.getElementById('au-import-status');
    if (fileInput) fileInput.value = '';
    if (label) label.textContent = 'hoặc kéo thả file Excel (.xlsx, .xls) hoặc .csv vào đây';
    if (status) {
        status.className = 'hidden text-xs font-semibold p-2.5 rounded-lg';
        status.textContent = '';
    }
    if (modal) {
        modal.classList.remove('hidden');
        modal.classList.add('show');
        modal.style.display = 'flex';
    }
}

function closeAuImportModal() {
    const modal = document.getElementById('au-import-modal');
    if (modal) {
        modal.classList.remove('show');
        modal.classList.add('hidden');
        modal.style.display = 'none';
    }
}

function handleAuFileSelected(e) {
    const files = e.target.files;
    if (files && files.length > 0) {
        selectedAuFile = files[0];
        window.selectedAuFile = files[0];
        const label = document.getElementById('au-file-name-label');
        if (label) {
            label.innerHTML = `<span class="text-emerald-700 font-bold"><i class="fa-solid fa-circle-check text-emerald-500 mr-1"></i> Đã chọn: ${escapeHtml(selectedAuFile.name)}</span> (${(selectedAuFile.size / 1024).toFixed(1)} KB)`;
        }
        const fileAlert = document.getElementById('au-file-alert');
        if (fileAlert) fileAlert.classList.add('hidden');
    }
}

// Submit Import
async function handleAuImportSubmit(e) {
    if (e && e.preventDefault) e.preventDefault();
    const curFile = selectedAuFile || window.selectedAuFile;
    if (!curFile) {
        const fileAlert = document.getElementById('au-file-alert');
        if (fileAlert) fileAlert.classList.remove('hidden');
        showToast('Vui lòng chọn file Excel hoặc CSV trước!', 'error');
        // Tự động mở hộp thoại chọn file cho người dùng
        const input = document.getElementById('au-file-input');
        if (input) input.click();
        return;
    }

    const btnSubmit = document.getElementById('btn-submit-au-import');
    const status = document.getElementById('au-import-status');
    const mode = document.querySelector('input[name="au_import_mode"]:checked')?.value || 'replace';

    if (btnSubmit) {
        btnSubmit.disabled = true;
        btnSubmit.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang Import Dữ Liệu...';
    }

    if (status) {
        status.className = 'text-xs font-semibold p-2.5 rounded-lg bg-blue-50 text-blue-700 flex items-center gap-2';
        status.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang xử lý file dữ liệu...';
        status.classList.remove('hidden');
    }

    const formData = new FormData();
    formData.append('file', curFile);
    formData.append('mode', mode);

    try {
        const res = await fetch('/api/au/import', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();

        if (data.success) {
            showToast(data.message || `Import thành công ${data.count} bản ghi!`, 'success');
            if (status) {
                status.className = 'text-xs font-semibold p-2.5 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200';
                status.innerHTML = `<i class="fa-solid fa-circle-check"></i> ${data.message}`;
            }
            setTimeout(() => {
                closeAuImportModal();
                loadAuStats();
                loadAuFilters();
                loadAuTable(1);
            }, 800);
        } else {
            if (status) {
                status.className = 'text-xs font-semibold p-2.5 rounded-lg bg-red-50 text-red-700 border border-red-200';
                status.innerHTML = `<i class="fa-solid fa-circle-exclamation"></i> ${data.error || 'Lỗi khi import file'}`;
            }
            showToast(data.error || 'Import thất bại', 'error');
        }
    } catch (err) {
        console.error('Import AU error:', err);
        if (status) {
            status.className = 'text-xs font-semibold p-2.5 rounded-lg bg-red-50 text-red-700 border border-red-200';
            status.innerHTML = '<i class="fa-solid fa-circle-exclamation"></i> Lỗi kết nối khi tải file lên';
        }
        showToast('Lỗi kết nối khi import', 'error');
    } finally {
        if (btnSubmit) {
            btnSubmit.disabled = false;
            btnSubmit.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i> Bắt Đầu Import';
        }
    }
}

// Modal Thêm / Sửa AU Record
function openAuAddModal() {
    const modal = document.getElementById('au-record-modal');
    const title = document.getElementById('au-modal-title');
    const editId = document.getElementById('au-edit-id');
    const inShd = document.getElementById('au-input-so-hop-dong');
    const inTd = document.getElementById('au-input-tap-diem');
    const inTstc = document.getElementById('au-input-tstc');
    const inDuong = document.getElementById('au-input-duong');
    const inKtv = document.getElementById('au-input-ktv');
    const inBlock = document.getElementById('au-input-block');

    if (title) title.innerHTML = '<i class="fa-solid fa-plus text-blue-600"></i> Thêm Bản Ghi AU Mới';
    if (editId) editId.value = '';
    if (inShd) inShd.value = '';
    if (inTd) inTd.value = '';
    if (inTstc) inTstc.value = '';
    if (inDuong) inDuong.value = '';
    if (inKtv) inKtv.value = '';
    if (inBlock) inBlock.value = '';

    if (modal) {
        modal.classList.remove('hidden');
        modal.classList.add('show');
        modal.style.display = 'flex';
    }
}

function openAuEditModal(id) {
    const record = currentAuData.find(r => r.id === id);
    if (!record) return;

    const modal = document.getElementById('au-record-modal');
    const title = document.getElementById('au-modal-title');
    const editId = document.getElementById('au-edit-id');
    const inShd = document.getElementById('au-input-so-hop-dong');
    const inTd = document.getElementById('au-input-tap-diem');
    const inTstc = document.getElementById('au-input-tstc');
    const inDuong = document.getElementById('au-input-duong');
    const inKtv = document.getElementById('au-input-ktv');
    const inBlock = document.getElementById('au-input-block');

    if (title) title.innerHTML = `<i class="fa-solid fa-pen-to-square text-blue-600"></i> Chỉnh Sửa Bản Ghi AU`;
    if (editId) editId.value = id;
    if (inShd) inShd.value = record.so_hop_dong || '';
    if (inTd) inTd.value = record.tap_diem || '';
    if (inTstc) inTstc.value = record.tstc || '';
    if (inDuong) inDuong.value = record.duong || '';
    if (inKtv) inKtv.value = record.ktv_t10 || '';
    if (inBlock) inBlock.value = record.block || '';

    if (modal) {
        modal.classList.remove('hidden');
        modal.classList.add('show');
        modal.style.display = 'flex';
    }
}

function closeAuRecordModal() {
    const modal = document.getElementById('au-record-modal');
    if (modal) {
        modal.classList.remove('show');
        modal.classList.add('hidden');
        modal.style.display = 'none';
    }
}

async function handleAuRecordSubmit(e) {
    e.preventDefault();
    const editId = document.getElementById('au-edit-id')?.value;
    const payload = {
        so_hop_dong: document.getElementById('au-input-so-hop-dong')?.value || '',
        tap_diem: document.getElementById('au-input-tap-diem')?.value || '',
        tstc: document.getElementById('au-input-tstc')?.value || '',
        duong: document.getElementById('au-input-duong')?.value || '',
        ktv_t10: document.getElementById('au-input-ktv')?.value || '',
        block: document.getElementById('au-input-block')?.value || '',
    };

    try {
        let res;
        if (editId) {
            res = await fetch(`/api/au/record/${editId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } else {
            res = await fetch('/api/au/record', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        }
        const data = await res.json();
        if (data.success) {
            showToast(editId ? 'Cập nhật bản ghi thành công!' : 'Thêm bản ghi AU mới thành công!', 'success');
            closeAuRecordModal();
            loadAuStats();
            loadAuFilters();
            loadAuTable(currentAuPage);
        } else {
            showToast(data.error || 'Lỗi khi lưu bản ghi', 'error');
        }
    } catch (err) {
        console.error('Error saving AU record:', err);
        showToast('Lỗi kết nối khi lưu bản ghi', 'error');
    }
}

// Xóa bản ghi AU (Bắt buộc mật khẩu: doitruongsg1)
async function deleteAuRecord(id) {
    const pwd = prompt('BẢO MẬT: Nhập mật khẩu xác nhận để xóa bản ghi:');
    if (pwd === null) return;
    if (!pwd.trim()) {
        showToast('Vui lòng nhập mật khẩu xác nhận để xóa', 'error');
        return;
    }

    try {
        const res = await fetch(`/api/au/record/${id}?password=${encodeURIComponent(pwd.trim())}`, {
            method: 'DELETE'
        });
        const data = await res.json();
        if (data.success) {
            showToast('Đã xóa bản ghi AU thành công!', 'success');
            loadAuStats();
            loadAuTable(currentAuPage);
        } else {
            showToast(data.error || 'Mật khẩu xác nhận không chính xác!', 'error');
        }
    } catch (err) {
        console.error('Error deleting AU record:', err);
        showToast('Lỗi kết nối khi xóa bản ghi', 'error');
    }
}

// Xóa toàn bộ dữ liệu AU (Bắt buộc mật khẩu: doitruongsg1)
async function confirmClearAllAu() {
    const pwd = prompt('CẢNH BÁO NGUY HIỂM: Thao tác này sẽ XÓA SẠCH toàn bộ dữ liệu AU trong hệ thống!\nVui lòng nhập mật khẩu xác nhận:');
    if (pwd === null) return;
    if (!pwd.trim()) {
        showToast('Vui lòng nhập mật khẩu xác nhận để tiếp tục', 'error');
        return;
    }

    try {
        const res = await fetch('/api/au/clear', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: pwd.trim() })
        });
        const data = await res.json();
        if (data.success) {
            showToast('Đã xóa toàn bộ dữ liệu AU thành công!', 'success');
            loadAuStats();
            loadAuFilters();
            loadAuTable(1);
        } else {
            showToast(data.error || 'Mật khẩu xác nhận không chính xác!', 'error');
        }
    } catch (err) {
        console.error('Error clearing AU records:', err);
        showToast('Lỗi kết nối khi xóa dữ liệu', 'error');
    }
}

// Hàm sao chép clipboard tiện ích
function copyToClipboard(text, label = 'Nội dung') {
    if (!text) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
            showToast(`Đã sao chép ${label}: ${text}`, 'success');
        }).catch(() => {
            fallbackCopyText(text, label);
        });
    } else {
        fallbackCopyText(text, label);
    }
}

function fallbackCopyText(text, label) {
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.left = "-999999px";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
        document.execCommand('copy');
        showToast(`Đã sao chép ${label}: ${text}`, 'success');
    } catch (err) {
        showToast('Không thể sao chép tự động', 'error');
    }
    document.body.removeChild(textArea);
}


