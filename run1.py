# run.py
import os
import sys
import uuid
import time
import json
import hashlib
import re
import logging
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect, url_for, send_file, abort
import google.generativeai as genai
from werkzeug.utils import secure_filename

# ===== CẤU HÌNH LOGGING =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== CẤU HÌNH GEMINI - LẤY TỪ ENVIRONMENT VARIABLES =====
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    print("⚠️ CẢNH BÁO: Chưa có GEMINI_API_KEY trong environment variables trên Render")
    print("📝 Vào Render Dashboard → Environment → Thêm GEMINI_API_KEY")
else:
    print("✅ Đã tìm thấy Gemini API Key từ environment variables")
    genai.configure(api_key=GEMINI_API_KEY)

# ===== XÁC ĐỊNH CỔNG CHẠY =====
PORT = int(os.environ.get('PORT', 7860))

# ===== THƯ MỤC GỐC =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ===== THƯ MỤC LƯU TRỮ =====
UPLOAD_FOLDER = '/tmp/casio_uploads'  # Dùng /tmp trên Render
TEMPLATES_FOLDER = os.path.join(BASE_DIR, 'templates')

# Tạo thư mục cần thiết
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMPLATES_FOLDER, exist_ok=True)

print(f"📁 Upload folder: {UPLOAD_FOLDER}")
print(f"📁 Templates folder: {TEMPLATES_FOLDER}")

app = Flask(__name__, template_folder=TEMPLATES_FOLDER)
app.secret_key = os.environ.get('SECRET_KEY', 'casio-secret-key-' + str(uuid.uuid4()))
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# ===== KHỞI TẠO GEMINI MODEL =====
model = None
if GEMINI_API_KEY:
    try:
        print("🔄 Đang kết nối Gemini API...")
        genai.configure(api_key=GEMINI_API_KEY)
        
        # Thử các model name
        model_names = ['gemini-1.5-pro', 'gemini-1.0-pro', 'gemini-pro']
        
        for model_name in model_names:
            try:
                model = genai.GenerativeModel(model_name)
                # Test nhẹ
                test = model.generate_content("test", generation_config={"max_output_tokens": 5})
                print(f"✅ Đã kết nối thành công với model: {model_name}")
                break
            except Exception as e:
                print(f"⚠️ Thử model {model_name} thất bại: {e}")
                continue
        else:
            print("❌ Không thể kết nối với bất kỳ model nào")
            model = None
            
    except Exception as e:
        print(f"⚠️ Lỗi khởi tạo Gemini: {e}")
        model = None
else:
    print("ℹ️ Chạy ở chế độ offline (không có Gemini API)")

# ===== KIỂM TRA TEMPLATE =====
TEMPLATE_FILE = os.path.join(TEMPLATES_FOLDER, 'ai_chatbot.html')
if not os.path.exists(TEMPLATE_FILE):
    print(f"❌ KHÔNG TÌM THẤY FILE TEMPLATE: {TEMPLATE_FILE}")
    # Tạo template mặc định
    with open(TEMPLATE_FILE, 'w', encoding='utf-8') as f:
        f.write("""<!DOCTYPE html>
<html>
<head>
    <title>Casio AI Assistant</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial; padding: 20px; background: #f0f2f5; }
        .container { max-width: 800px; margin: 0 auto; background: white; border-radius: 10px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .header { text-align: center; margin-bottom: 20px; }
        .chat-box { height: 400px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; margin-bottom: 20px; }
        .message { margin: 10px 0; padding: 10px; border-radius: 5px; }
        .user { background: #007bff; color: white; text-align: right; }
        .bot { background: #e9ecef; }
        .input-area { display: flex; gap: 10px; }
        textarea { flex: 1; padding: 10px; border: 1px solid #ddd; border-radius: 5px; }
        button { padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; }
        button:hover { background: #0056b3; }
        .status { text-align: center; margin-bottom: 10px; color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Casio AI Assistant</h1>
            <div class="status" id="status">Đang kết nối...</div>
        </div>
        <div class="chat-box" id="chatBox"></div>
        <div class="input-area">
            <textarea id="message" placeholder="Nhập tin nhắn..." rows="3"></textarea>
            <button onclick="sendMessage()">Gửi</button>
        </div>
    </div>
    <script>
        const sessionId = 'session_' + Date.now();
        
        async function sendMessage() {
            const message = document.getElementById('message').value;
            if (!message) return;
            
            addMessage('user', message);
            document.getElementById('message').value = '';
            
            try {
                const response = await fetch('/api/ai-chat-with-file', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        message: message,
                        session_id: sessionId
                    })
                });
                
                const data = await response.json();
                if (data.error) {
                    addMessage('bot', '❌ ' + data.error);
                } else {
                    addMessage('bot', data.reply);
                }
            } catch (error) {
                addMessage('bot', '❌ Lỗi kết nối');
            }
        }
        
        function addMessage(role, content) {
            const chatBox = document.getElementById('chatBox');
            const div = document.createElement('div');
            div.className = 'message ' + role;
            div.textContent = content;
            chatBox.appendChild(div);
            chatBox.scrollTop = chatBox.scrollHeight;
        }
        
        // Kiểm tra status
        fetch('/api/ai-health')
            .then(r => r.json())
            .then(data => {
                document.getElementById('status').textContent = 
                    data.api_configured ? '✅ Sẵn sàng' : '⚠️ Chế độ offline';
            });
    </script>
</body>
</html>""")
    print("✅ Đã tạo template mặc định")

# ===== CÁC HÀM XỬ LÝ FILE =====
def analyze_text_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        lines = content.split('\n')
        words = re.findall(r'\b\w+\b', content)
        return {
            'success': True,
            'stats': {
                'lines': len(lines),
                'words': len(words),
                'characters': len(content)
            },
            'preview': content[:500]
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

def analyze_hex_file(file_path):
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        lines = content.strip().split('\n')
        valid = 0
        for line in lines:
            if line.startswith(':'):
                valid += 1
        return {
            'success': True,
            'total_lines': len(lines),
            'valid_records': valid,
            'preview': content[:500]
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

def analyze_asm_file(file_path):
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        lines = content.split('\n')
        code_lines = [l for l in lines if l.strip() and not l.strip().startswith(';')]
        return {
            'success': True,
            'total_lines': len(lines),
            'code_lines': len(code_lines),
            'preview': content[:500]
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

def process_file(file_path, file_ext):
    if file_ext == '.txt':
        return analyze_text_file(file_path)
    elif file_ext == '.hex':
        return analyze_hex_file(file_path)
    elif file_ext == '.asm':
        return analyze_asm_file(file_path)
    return None

# ===== API CHAT CHÍNH =====
@app.route('/api/ai-chat-with-file', methods=['POST'])
def ai_chat():
    try:
        # Xử lý JSON request
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Không có dữ liệu'}), 400
        
        message = data.get('message', '').strip()
        session_id = data.get('session_id', str(uuid.uuid4()))
        
        if not message:
            return jsonify({'error': 'Tin nhắn trống'}), 400
        
        # Nếu không có API key hoặc model, trả lời đơn giản
        if not model:
            return jsonify({
                'reply': f'✅ Đã nhận: "{message}"\n\n(Đang chạy ở chế độ offline - chưa có Gemini API)',
                'session_id': session_id,
                'suggestions': ['Hướng dẫn ASM', 'Phân tích HEX', 'Kiểm tra chính tả']
            })
        
        # Gọi Gemini API
        try:
            response = model.generate_content(
                f"Bạn là trợ lý AI cho CASIO. Trả lời bằng tiếng Việt.\n\nUser: {message}",
                generation_config={"temperature": 0.7, "max_output_tokens": 1024}
            )
            reply = response.text
        except Exception as e:
            reply = f"❌ Lỗi AI: {str(e)}"
        
        return jsonify({
            'reply': reply,
            'session_id': session_id,
            'suggestions': ['Hướng dẫn ASM', 'Phân tích HEX', 'Kiểm tra chính tả']
        })
        
    except Exception as e:
        logger.error(f"Lỗi: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ===== API HEALTH =====
@app.route('/api/ai-health', methods=['GET'])
def ai_health():
    return jsonify({
        'status': 'ok',
        'api_configured': model is not None,
        'environment': 'render',
        'upload_folder': UPLOAD_FOLDER
    })

# ===== DEBUG =====
@app.route('/debug')
def debug():
    return jsonify({
        'gemini_api': bool(GEMINI_API_KEY),
        'model': str(model) if model else None,
        'python_version': sys.version,
        'env_vars': list(os.environ.keys())
    })

# ===== TRANG CHATBOT =====
@app.route('/ai-chatbot')
def ai_chatbot_page():
    return render_template('ai_chatbot.html')

# ===== TRANG CHỦ =====
@app.route('/')
def home():
    return redirect('/ai-chatbot')

# ===== ERROR HANDLERS =====
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Không tìm thấy'}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Lỗi máy chủ'}), 500

# ===== MAIN =====
if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 CASIO TOOL SERVER - RENDER OPTIMIZED")
    print("="*60)
    print(f"📌 Port: {PORT}")
    print(f"🤖 Gemini API: {'✅ Có' if model else '❌ Chưa'}")
    print(f"📁 Templates: {TEMPLATES_FOLDER}")
    print("="*60)
    
    app.run(host='0.0.0.0', port=PORT)
