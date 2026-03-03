Casio Tool

https://img.shields.io/badge/Flask-2.3.3-blue.svg
https://img.shields.io/badge/Python-3.8%2B-green.svg
https://img.shields.io/badge/License-GNU%20GPLv3-red.svg

Casio Tool là bộ công cụ toàn diện dành cho các dòng máy tính Casio FX‑580VN X và FX‑880BTG, hỗ trợ biên dịch ASM/ROP, xử lý pixel, chuyển đổi token hex, spell 1‑line và nhiều tiện ích khác.
Dự án được xây dựng trên nền tảng Flask, với giao diện responsive, cơ chế điều hướng POST đồng bộ và bảo mật cao.

---

✨ Tính năng nổi bật

· ROP Compiler
  Biên dịch mã Assembly / ROP sang mã hex, hỗ trợ riêng biệt cho hai dòng máy 580VN X và 880BTG.
· Pixel Tool
  · Chuyển đổi ảnh → ma trận pixel 1‑bit (192×63) và xuất mã hex.
  · Vẽ pixel trực tiếp trên lưới, xuất hex tương ứng.
· Hex / Token Translator
  · Phân tách chuỗi hex theo cấu trúc đặc thù của Casio.
  · Dịch token giữa hex, ký tự và hàm máy tính kèm bảng mã tra cứu.
· Spell 1‑Line
  Biên dịch các dòng lệnh spell thành hex, tự động resize ô kết quả, hỗ trợ Ctrl+Enter.
· Upload & Góp ý
  Cho phép tải file lên server (chặn file nguy hiểm), gửi phản hồi và ủng hộ qua mã QR.
· Giao diện thống nhất
  · Sidebar với điều hướng POST, active page được highlight tự động.
  · Footer đồng bộ với các liên kết nhanh.
  · Thiết kế responsive, tối ưu cho cả desktop và mobile.

---

📁 Cấu trúc thư mục

```
CasioTool/
├── app.py                          # Flask backend chính (tích hợp tất cả)
├── index.html                      # Trang chủ
├── hex/                            # Tiện ích Hex / Token
│   └── index.html
├── asm/                            # ROP Compiler
│   └── index.html
├── pixel/                          # Pixel Tool
│   └── index.html
├── spell/                          # Spell 1‑Line
│   └── index.html
├── donate/                         # Trang ủng hộ
│   └── index.html
├── lienhe/                         # Trang liên hệ
│   └── index.html
├── asmapp/                         # Thư mục chứa compiler gốc
│   ├── 580vnx/                    # Compiler cho 580VN X
│   │   ├── compiler_.py
│   │   └── rom.bin               # Bắt buộc
│   └── 880btg/                    # Compiler cho 880 BTG
│       ├── compiler_.py
│       └── rom.bin
├── util/                           # Các tiện ích backend
│   └── spell.py                  # Xử lý spell
├── uploads/                        # Thư mục lưu file upload (tự động tạo)
├── requirements.txt               # Danh sách thư viện Python
└── README.md                      # Bạn đang đọc đây
```

Lưu ý: Các thư mục 580vnx và 880btg phải chứa đầy đủ compiler_.py và rom.bin. Các file phụ trợ khác (disas.txt, gadgets, labels, …) là không bắt buộc.

---

⚙️ Yêu cầu hệ thống

· Python 3.8 trở lên
· pip (Python package manager)
· Các thư viện trong requirements.txt

---

🚀 Cài đặt và chạy

1. Clone repository
   ```bash
   git clone https://github.com/your-username/casio-tool.git
   cd casio-tool
   ```
2. Tạo môi trường ảo (khuyến nghị)
   ```bash
   python -m venv venv
   source venv/bin/activate      # Linux / macOS
   venv\Scripts\activate         # Windows
   ```
3. Cài đặt dependencies
   ```bash
   pip install -r requirements.txt
   ```
4. Chuẩn bị compiler
   · Đặt compiler_.py và rom.bin vào thư mục asmapp/580vnx/ và asmapp/880btg/ tương ứng.
5. Khởi động server
   ```bash
   python app.py 5000
   ```
   Server sẽ chạy tại http://localhost:5000.
6. Truy cập ứng dụng
   Mở trình duyệt và vào http://localhost:5000.

---

📡 API Endpoints

Phương thức Đường dẫn Mô tả
GET / Trang chủ
POST / Xác nhận điều hướng POST
GET /hex Giao diện tiện ích Casio
POST /hex Xác nhận POST, trả JSON
GET /asm Giao diện ROP Compiler
POST /asm Biên dịch mã (nếu có code), hoặc xác nhận
POST /compiler Tương tự /asm
GET /pixel Giao diện Pixel Tool
POST /pixel Xác nhận POST
GET /spell Giao diện Spell 1‑Line
POST /spell Biên dịch spell
GET /donate Trang ủng hộ
POST /donate Nhận dữ liệu ủng hộ (JSON)
GET /lienhe Trang liên hệ
POST /lienhe Xác nhận liên hệ
POST /upload Tải file lên (multipart/form‑data)
GET /health Kiểm tra trạng thái server (nếu dùng)

---

🧠 Hướng dẫn sử dụng compiler

1. Chọn dòng máy trong dropdown (580VNX / 880BTG).
2. Nhập mã Assembly/ROP vào ô văn bản.
3. Nhấn nút "BIÊN DỊCH" hoặc Ctrl+Enter.
4. Kết quả hex sẽ hiển thị trong ô kết quả và tự động copy vào clipboard.

Ví dụ mã ASM đơn giản (580VNX):

```
    org 0x8000
    mov a, #0x55
    add a, #0x01
    nop
    ret
```

---

🔒 Bảo mật

· Blacklist: Chặn tải lên các file có đuôi .py, .sh, .php, .exe, … và các file nhạy cảm (app.py, config.py, …).
· Path traversal: Ngăn truy cập ra ngoài thư mục dự án.
· Logging: Ghi lại chi tiết request/response (giới hạn 1000 ký tự) phục vụ debug.

---

🤝 Đóng góp

Mọi đóng góp đều được hoan nghênh!

1. Fork dự án.
2. Tạo nhánh mới (git checkout -b feature/AmazingFeature).
3. Commit thay đổi (git commit -m 'Add some AmazingFeature').
4. Push lên nhánh (git push origin feature/AmazingFeature).
5. Mở Pull Request.

---

📄 Giấy phép

Dự án được phân phối dưới giấy phép GNU General Public License v3.0.
Xem file LICENSE để biết thêm chi tiết.

---

💖 Tín nhiệm & Cảm ơn

· Compiler gốc: Hieuxyz, Casio2k9
· Spell Tool: phong2k11123
· Ý tưởng và hỗ trợ: Cộng đồng Casio Việt Nam

---

Made with ❤️ for the Casio modding community.