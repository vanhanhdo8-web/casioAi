#!/usr/bin/env python3
import os
import sys
import webbrowser
import threading
import time

try:
    from app import app
except ImportError as e:
    print("Lỗi: Không thể import 'app' từ app.py. Hãy chắc chắn file app.py tồn tại.")
    print("Chi tiết:", e)
    sys.exit(1)

def open_browser():
    time.sleep(1.5)
    webbrowser.open('http://localhost:5000')

def check_models():
    models_dir = 'models'
    if not os.path.isdir(models_dir):
        print(f"Lỗi: Không tìm thấy thư mục '{models_dir}'.")
        print("Hãy tạo thư mục 'models' và bên trong đặt các thư mục con cho từng model (ví dụ: 580vnx, 880btg).")
        return False

    models = [d for d in os.listdir(models_dir) if os.path.isdir(os.path.join(models_dir, d))]
    if not models:
        print(f"Cảnh báo: Thư mục '{models_dir}' không chứa model nào.")
        return True

    required_files = ['config.py', 'disas.txt', 'gadgets.txt', 'labels.txt']
    for model in models:
        model_path = os.path.join(models_dir, model)
        missing = []
        for f in required_files:
            if not os.path.isfile(os.path.join(model_path, f)):
                missing.append(f)
        if missing:
            print(f"Cảnh báo: Model '{model}' thiếu các file: {', '.join(missing)}")
    return True

if __name__ == '__main__':
    if not check_models():
        sys.exit(1)

    print("🚀 Đang khởi động Decompiler Web Server...")
    print("📂 Đường dẫn: http://localhost:5000")
    print("⏳ Đang mở trình duyệt...")

    threading.Thread(target=open_browser, daemon=True).start()
    app.run(debug=True, host='0.0.0.0', port=5000)