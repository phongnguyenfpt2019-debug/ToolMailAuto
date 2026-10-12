# FPT Telecom - Dashboard Quản Trị CEM (CSAT 1, 2 CLDV)

Ứng dụng web viết bằng Python (Flask + SQLite + Chart.js) kết nối trực tiếp đến mail server **`mail.fpt.net`** qua giao thức IMAP SSL, tự động lọc và tổng hợp toàn bộ các email có tiêu đề bắt đầu bằng **`CEM - CSAT 1, 2 CLDV`**, sau đó hiển thị trực quan lên Dashboard quản trị CEM.

---

## 🌟 Tính Năng Nổi Bật

1. **Tag / Module Dashboard: CEM**:
   - Giao diện **Sáng (Light Theme)** trang nhã, sắc nét, tương phản cao, dễ nhìn.
   - Hiển thị trực tiếp các chỉ số đo lường trải nghiệm khách hàng (Voice of Customer).

2. **Bộ Lọc Thời Gian Đánh Giá (`eval_time`)**:
   - Chọn khoảng ngày tùy biến: **Từ ngày** - **Đến ngày** (dựa vào Thời gian đánh giá trong email).
   - Nút chọn nhanh: **Tất cả**, **Hôm nay**, **Hôm qua**, **7 ngày qua**, **Tháng này**.
   - Thẻ thống kê KPI, biểu đồ và danh sách dữ liệu tự động đồng bộ theo ngày được chọn.

3. **Bảng Danh Sách & Xem Chi Tiết**:
   - **Nhấp vào dòng bất kỳ** để mở rộng xem ngay thẻ chi tiết tại bảng.
   - Nút **"Xem Chi Tiết"** mở modal đầy đủ và tab xem lại toàn văn Email gốc (HTML).

4. **Biểu Đồ Trực Quan (Interactive Charts)**:
   - 🍩 **Biểu đồ tỷ lệ CSAT 1 vs CSAT 2** (Donut Chart)
   - 📈 **Xu hướng diễn biến CSAT theo ngày đánh giá** (Line/Area Chart)
   - 📊 **Top NVKT có nhiều phản ánh CSAT 1, 2 nhất** (Bar Chart)
   - 🏷️ **Phân loại Nhóm lỗi phản ánh phổ biến nhất** (Bar Chart)

5. **Xuất Báo Cáo Thông Minh**:
   - **Xuất Excel (.xlsx)** & **Xuất CSV (.csv)**: Xuất đúng theo bộ lọc ngày và điểm CSAT đang chọn.

6. **Đồng bộ dữ liệu tức thì (Live IMAP Sync)**:
   - Nút "Đồng bộ Mail" quét trực tiếp từ hòm thư `mail.fpt.net:993`.
   - Lưu trữ cục bộ tại SQLite (`data/cem_csat.db`), tốc độ truy xuất cực nhanh.

---

## 🚀 Hướng Dẫn Sử Dụng

### Cách 1: Khởi động 1-Click bằng file Batch (Khuyên dùng trên Windows)
Nhấp đúp chuột vào file:
```
run_dashboard.bat
```
Ứng dụng sẽ tự động khởi động server và mở trình duyệt web tại:
```
http://localhost:5050
```

### Cách 2: Khởi động bằng dòng lệnh Terminal
```powershell
cd "d:\Tool lấy data"
python app.py
```
Sau đó truy cập: `http://localhost:5050`

---

## ⚙️ Cấu Hình Mail Server
Thông tin đã được cài đặt sẵn:
- **Tài khoản**: `phuongnam.phongnh5@fpt.net`
- **Mật khẩu**: `Benngo@@2026`
- **IMAP Server**: `mail.fpt.net` (Cổng `993` SSL)
- Có thể thay đổi trực tiếp trên nút **"Cấu hình Mail"** tại giao diện Sidebar bất kỳ lúc nào.
