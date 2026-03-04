# run.py
import subprocess
import os
import mimetypes
from flask import Flask, request, abort, jsonify, g, send_file, redirect, url_for, render_template
import uuid
import time
import json
import threading
import webbrowser
import tempfile
import importlib.util
import sys
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime
import hashlib
import re

# ===== LOAD BIẾN MÔI TRƯỜNG =====
load_dotenv()

# ===== CẤU HÌNH GEMINI =====
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    print("⚠️  CẢNH BÁO: Chưa có GEMINI_API_KEY trong file .env")
    print("📝 Tạo file .env với nội dung: GEMINI_API_KEY=your-gemini-key-here")
    print("🔗 Lấy key tại: https://makersuite.google.com/app/apikey")
else:
    print("✅ Đã tìm thấy Gemini API Key")
    genai.configure(api_key=GEMINI_API_KEY)

# ===== XÁC ĐỊNH CỔNG CHẠY =====
PORT = int(os.environ.get('PORT', 7860))

# ===== THƯ MỤC GỐC =====
BASE_DIR = os.getcwd()
TMP_DIR = tempfile.gettempdir()

# ===== THƯ MỤC LƯU TRỮ =====
UPLOAD_FOLDER = os.path.join(TMP_DIR, 'uploads')
HEX_FOLDER = os.path.join(BASE_DIR, 'hex')
ASM_FOLDER = os.path.join(BASE_DIR, 'asm')
PIXEL_FOLDER = os.path.join(BASE_DIR, 'pixel')
SPELL_FOLDER = os.path.join(BASE_DIR, 'spell')
DONATE_FOLDER = os.path.join(BASE_DIR, 'donate')
LIENHE_FOLDER = os.path.join(BASE_DIR, 'lienhe')
ROP_FOLDER = os.path.join(BASE_DIR, 'rop')
TEMPLATES_FOLDER = os.path.join(BASE_DIR, 'templates')

# Tạo thư mục templates nếu chưa có
if not os.path.exists(TEMPLATES_FOLDER):
    os.makedirs(TEMPLATES_FOLDER)
    print(f"📁 Đã tạo thư mục: {TEMPLATES_FOLDER}")

ASMAPP_BASE = os.path.join(BASE_DIR, 'asmapp')
DECOMPILER_MODELS_DIR = os.path.join(ASMAPP_BASE, 'decompiler', 'models')

MODELS = ['580vnx', '880btg']

# Tạo thư mục
for folder in [UPLOAD_FOLDER, HEX_FOLDER, ASM_FOLDER, PIXEL_FOLDER,
               SPELL_FOLDER, DONATE_FOLDER, LIENHE_FOLDER, ROP_FOLDER,
               TEMPLATES_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)
        print(f"📁 Đã tạo thư mục: {folder}")

# ===== BLACKLIST =====
BLOCK_EXT = {".py", ".sh", ".php", ".asp", ".exe", ".dll", ".so"}
BLOCK_FILES = {"run.py", "app.py", "config.py", ".env"}
BLOCK_DIRS = {".git", "__pycache__", "venv", "env"}

app = Flask(__name__, template_folder=TEMPLATES_FOLDER)
app.secret_key = os.getenv('SECRET_KEY', 'casio-tool-secret-key-2024')

# ===== CẤU HÌNH GEMINI MODEL =====
generation_config = {
    "temperature": 0.7,
    "top_p": 0.9,
    "top_k": 40,
    "max_output_tokens": 1024,
}

safety_settings = [
    {
        "category": "HARM_CATEGORY_HARASSMENT",
        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
    },
    {
        "category": "HARM_CATEGORY_HATE_SPEECH",
        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
    },
    {
        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
    },
    {
        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
    },
]

# Khởi tạo model
model = None
if GEMINI_API_KEY and GEMINI_API_KEY != 'your-gemini-key-here':
    try:
        model = genai.GenerativeModel(
            model_name="gemini-pro",
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        print("✅ Đã khởi tạo Gemini model thành công")
    except Exception as e:
        print(f"⚠️ Lỗi khởi tạo Gemini model: {e}")

# ===== CẤU TRÚC WEBSITE CHO AI =====
WEBSITE_STRUCTURE = {
    'home': {
        'name': 'Trang chủ',
        'path': '/',
        'description': 'Trang chủ của Casio Tool Server',
        'features': ['Xem công cụ', 'Điều hướng', 'Tìm kiếm']
    },
    'hex': {
        'name': 'HEX Tool',
        'path': '/hex',
        'description': 'Công cụ xử lý file HEX cho CASIO',
        'features': ['Upload file hex', 'Xem nội dung hex', 'Chỉnh sửa hex', 'Download file'],
        'commands': ['upload', 'edit', 'save', 'download']
    },
    'asm': {
        'name': 'ASM Compiler',
        'path': '/asm',
        'description': 'Trình biên dịch Assembly cho CASIO',
        'features': ['Biên dịch assembly', 'Chọn model 580vnx/880btg', 'Xem kết quả hex', 'Debug'],
        'models': ['580vnx', '880btg'],
        'commands': ['compile', 'select model', 'view output']
    },
    'pixel': {
        'name': 'Pixel Tool',
        'path': '/pixel',
        'description': 'Công cụ vẽ ảnh pixel',
        'features': ['Tạo ảnh mới', 'Vẽ pixel', 'Chỉnh màu', 'Xuất ảnh'],
        'commands': ['new', 'draw', 'color', 'export']
    },
    'spell': {
        'name': 'Spell Checker',
        'path': '/spell',
        'description': 'Kiểm tra chính tả',
        'features': ['Kiểm tra chính tả', 'Gợi ý sửa lỗi', 'API'],
        'commands': ['check', 'suggest', 'api']
    },
    'rop': {
        'name': 'ROP Tool',
        'path': '/rop',
        'description': 'Công cụ ROP (Return Oriented Programming)',
        'features': ['Xem tài liệu', 'Tải examples', 'Hướng dẫn'],
        'commands': ['docs', 'examples', 'guide']
    },
    'donate': {
        'name': 'Donate',
        'path': '/donate',
        'description': 'Ủng hộ dự án',
        'features': ['Ủng hộ qua Vietcombank', 'Ủng hộ qua Momo', 'Ủng hộ qua Paypal']
    },
    'lienhe': {
        'name': 'Liên hệ',
        'path': '/lienhe',
        'description': 'Thông tin liên hệ',
        'features': ['Gửi email', 'Facebook', 'Discord']
    }
}

# ===== KIẾN THỨC VỀ CASIO =====
CASIO_KNOWLEDGE = {
    'asm_basics': {
        'title': 'Kiến thức cơ bản về ASM CASIO',
        'content': '''
        Assembly cho CASIO là ngôn ngữ lập trình cấp thấp dành cho dòng máy tính fx-580VN X và fx-880BTG.
        
        Các lệnh cơ bản:
        - MOV: Di chuyển dữ liệu
        - ADD: Cộng
        - SUB: Trừ
        - MUL: Nhân
        - DIV: Chia
        - JMP: Nhảy
        - CALL: Gọi hàm
        - RET: Trở về
        '''
    },
    'hex_format': {
        'title': 'Định dạng file HEX',
        'content': '''
        File HEX (Intel HEX) là định dạng file chứa mã máy dưới dạng text.
        
        Cấu trúc dòng HEX:
        :LLAAAATTDD...CC
        
        - : - Ký tự bắt đầu
        - LL - Độ dài dữ liệu (bytes)
        - AAAA - Địa chỉ
        - TT - Loại record
        - DD - Dữ liệu
        - CC - Checksum
        '''
    }
}

# ===== LƯU TRỮ CHAT HISTORY =====
chat_histories = {}

# ===== CACHE CHO AI RESPONSES =====
RESPONSE_CACHE = {}
CACHE_DURATION = 86400  # 24 giờ

# ===== RATE LIMITING =====
RATE_LIMIT = {}
RATE_LIMIT_DURATION = 60  # 1 phút
RATE_LIMIT_MAX = 30  # 30 requests/phút

# ===== HÀM KIỂM TRA RATE LIMIT =====
def check_rate_limit(ip):
    current_time = time.time()
    
    # Clean old entries
    for client_ip in list(RATE_LIMIT.keys()):
        if current_time - RATE_LIMIT[client_ip]['timestamp'] > RATE_LIMIT_DURATION:
            del RATE_LIMIT[client_ip]
    
    # Check rate limit
    if ip in RATE_LIMIT:
        if RATE_LIMIT[ip]['count'] >= RATE_LIMIT_MAX:
            return False
        RATE_LIMIT[ip]['count'] += 1
    else:
        RATE_LIMIT[ip] = {
            'count': 1,
            'timestamp': current_time
        }
    return True

# ===== HÀM TẠO CACHE KEY =====
def get_cache_key(messages, tool_context):
    content = json.dumps({
        'messages': messages[-3:],
        'tool': tool_context
    }, sort_keys=True)
    return hashlib.md5(content.encode()).hexdigest()

# ===== HÀM LẤY CACHED RESPONSE =====
def get_cached_response(cache_key):
    if cache_key in RESPONSE_CACHE:
        cached = RESPONSE_CACHE[cache_key]
        if time.time() - cached['timestamp'] < CACHE_DURATION:
            return cached['response']
        else:
            del RESPONSE_CACHE[cache_key]
    return None

# ===== HÀM PHÂN TÍCH INTENT =====
def analyze_intent(message):
    message_lower = message.lower()
    
    intents = {
        'help': ['giúp', 'hướng dẫn', 'cách', 'làm sao', 'how to'],
        'compile': ['dịch', 'compile', 'biên dịch', 'chạy code'],
        'debug': ['lỗi', 'bug', 'sai', 'debug', 'fix'],
        'explain': ['giải thích', 'nghĩa là', 'là gì', 'khái niệm'],
        'example': ['ví dụ', 'mẫu', 'example', 'sample'],
        'compare': ['so sánh', 'khác nhau', 'compare', 'vs']
    }
    
    detected = []
    for intent, keywords in intents.items():
        if any(keyword in message_lower for keyword in keywords):
            detected.append(intent)
    
    return detected if detected else ['general']

# ===== HÀM TẠO SYSTEM PROMPT =====
def get_system_prompt(tool_context='home'):
    base_prompt = f"""Bạn là trợ lý AI thông minh của Casio Tool Server - công cụ lập trình cho máy tính CASIO fx-580VN X và fx-880BTG.

THÔNG TIN:
- Tên: Casio AI Assistant (Gemini)
- Chuyên môn: Lập trình CASIO, Assembly, HEX, ROP
- Phong cách: Thân thiện, chuyên nghiệp
- Ngôn ngữ: Trả lời bằng TIẾNG VIỆT

NHIỆM VỤ:
1. Hướng dẫn sử dụng các công cụ trên website
2. Giải thích code assembly, hex, các khái niệm lập trình
3. Cung cấp ví dụ cụ thể, dễ hiểu
4. Debug và tối ưu code cho CASIO

CÔNG CỤ HIỆN CÓ:
"""
    
    for tool_id, tool_info in WEBSITE_STRUCTURE.items():
        base_prompt += f"\n- {tool_info['name']}: {tool_info['description']}"
    
    if tool_context in WEBSITE_STRUCTURE:
        tool = WEBSITE_STRUCTURE[tool_context]
        base_prompt += f"\n\nNGƯỜI DÙNG ĐANG Ở: {tool['name']}"
        base_prompt += f"\nMô tả: {tool['description']}"
        base_prompt += f"\nTính năng: {', '.join(tool['features'])}"
    
    return base_prompt

# ===== HÀM GỢI Ý ACTIONS =====
def suggest_actions(reply, current_tool, intents):
    suggestions = []
    
    # Gợi ý theo tool hiện tại
    if current_tool in WEBSITE_STRUCTURE:
        tool = WEBSITE_STRUCTURE[current_tool]
        if 'commands' in tool:
            suggestions.extend(tool['commands'][:2])
    
    # Gợi ý theo nội dung reply
    reply_lower = reply.lower()
    if 'hex' in reply_lower:
        suggestions.append('Upload file HEX')
        suggestions.append('Chỉnh sửa HEX')
    if 'asm' in reply_lower or 'assembly' in reply_lower:
        suggestions.append('Viết code ASM mẫu')
        suggestions.append('Chọn model 580vnx')
    if 'pixel' in reply_lower:
        suggestions.append('Vẽ ảnh mới')
        suggestions.append('Hướng dẫn vẽ pixel')
    
    # Thêm gợi ý mặc định
    if len(suggestions) < 3:
        defaults = ['Các công cụ có sẵn', 'Hướng dẫn ASM', 'Liên hệ hỗ trợ']
        suggestions.extend(defaults[:3 - len(suggestions)])
    
    return list(dict.fromkeys(suggestions))[:5]

# ===== API KIỂM TRA SỨC KHỎE =====
@app.route('/api/ai-health', methods=['GET'])
def ai_health():
    return jsonify({
        'status': 'healthy',
        'api_configured': bool(GEMINI_API_KEY and GEMINI_API_KEY != 'your-gemini-key-here' and model is not None),
        'cache_size': len(RESPONSE_CACHE),
        'active_sessions': len(chat_histories),
        'model': 'Gemini Pro'
    })

# ===== API CHAT =====
@app.route('/api/ai-chat', methods=['POST'])
def ai_chat():
    """Xử lý chat với Gemini AI"""
    # Kiểm tra rate limit
    client_ip = request.remote_addr
    if not check_rate_limit(client_ip):
        return jsonify({'error': 'Bạn đã gửi quá nhiều yêu cầu. Vui lòng thử lại sau.'}), 429
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Không có dữ liệu'}), 400
        
        message = data.get('message', '').strip()
        if not message:
            return jsonify({'error': 'Tin nhắn trống'}), 400
        
        session_id = data.get('session_id', str(uuid.uuid4()))
        current_tool = data.get('current_tool', 'home')
        
        # Kiểm tra API key và model
        if not GEMINI_API_KEY or GEMINI_API_KEY == 'your-gemini-key-here':
            return jsonify({'error': 'Gemini API key chưa được cấu hình. Vui lòng thêm vào file .env'}), 501
        
        if model is None:
            return jsonify({'error': 'Gemini model chưa được khởi tạo. Kiểm tra API key.'}), 501
        
        # Phân tích intent
        intents = analyze_intent(message)
        
        # Tạo session mới nếu cần
        if session_id not in chat_histories:
            chat_histories[session_id] = []
        
        # Thêm tin nhắn user vào history
        chat_histories[session_id].append({
            'role': 'user',
            'content': message,
            'time': time.time()
        })
        
        # Tạo system prompt
        system_prompt = get_system_prompt(current_tool)
        
        # Tạo context từ lịch sử
        context = ""
        recent_history = chat_histories[session_id][-6:]
        for msg in recent_history[:-1]:  # Bỏ qua tin nhắn cuối (tin nhắn hiện tại)
            context += f"{msg['role']}: {msg['content']}\n"
        
        # Tạo prompt hoàn chỉnh
        full_prompt = f"""{system_prompt}

LỊCH SỬ CHAT:
{context}

USER: {message}
ASSISTANT:"""
        
        # Kiểm tra cache
        cache_key = get_cache_key([full_prompt], current_tool)
        cached_response = get_cached_response(cache_key)
        
        if cached_response:
            suggestions = suggest_actions(cached_response, current_tool, intents)
            return jsonify({
                'reply': cached_response,
                'suggestions': suggestions,
                'session_id': session_id,
                'cached': True
            })
        
        # Gọi Gemini API
        response = model.generate_content(full_prompt)
        
        bot_reply = response.text
        
        # Lưu vào cache
        RESPONSE_CACHE[cache_key] = {
            'response': bot_reply,
            'timestamp': time.time()
        }
        
        # Lưu phản hồi bot
        chat_histories[session_id].append({
            'role': 'assistant',
            'content': bot_reply,
            'time': time.time()
        })
        
        # Giới hạn history
        if len(chat_histories[session_id]) > 50:
            chat_histories[session_id] = chat_histories[session_id][-50:]
        
        # Gợi ý actions
        suggestions = suggest_actions(bot_reply, current_tool, intents)
        
        return jsonify({
            'reply': bot_reply,
            'suggestions': suggestions,
            'session_id': session_id,
            'cached': False
        })
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Lỗi Gemini API: {error_msg}")
        
        if "API key" in error_msg.lower():
            return jsonify({'error': 'Lỗi xác thực Gemini API. Kiểm tra API key'}), 401
        elif "quota" in error_msg.lower() or "limit" in error_msg.lower():
            return jsonify({'error': 'Đã vượt quá giới hạn API Gemini. Thử lại sau'}), 429
        else:
            return jsonify({'error': f'Lỗi hệ thống: {error_msg}'}), 500

# ===== API CHAT STREAM =====
@app.route('/api/ai-chat-stream', methods=['POST'])
def ai_chat_stream():
    """Xử lý chat với Gemini AI (streaming)"""
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        session_id = data.get('session_id', str(uuid.uuid4()))
        current_tool = data.get('current_tool', 'home')
        
        if not message:
            return jsonify({'error': 'Tin nhắn trống'}), 400
        
        if model is None:
            return jsonify({'error': 'Gemini model chưa được khởi tạo'}), 501
        
        system_prompt = get_system_prompt(current_tool)
        full_prompt = f"{system_prompt}\n\nUSER: {message}\nASSISTANT:"
        
        def generate():
            try:
                response = model.generate_content(full_prompt, stream=True)
                
                full_response = ""
                for chunk in response:
                    if chunk.text:
                        full_response += chunk.text
                        yield f"data: {json.dumps({'content': chunk.text, 'done': False})}\n\n"
                
                # Lưu vào history
                if session_id not in chat_histories:
                    chat_histories[session_id] = []
                
                chat_histories[session_id].append({
                    'role': 'user',
                    'content': message,
                    'time': time.time()
                })
                chat_histories[session_id].append({
                    'role': 'assistant',
                    'content': full_response,
                    'time': time.time()
                })
                
                yield f"data: {json.dumps({'done': True})}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"
        
        return app.response_class(
            generate(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
            }
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ===== API LỊCH SỬ CHAT =====
@app.route('/api/chat-history/<session_id>', methods=['GET'])
def get_chat_history(session_id):
    history = chat_histories.get(session_id, [])
    return jsonify(history[-20:])

# ===== API XÓA LỊCH SỬ =====
@app.route('/api/clear-history/<session_id>', methods=['POST'])
def clear_chat_history(session_id):
    if session_id in chat_histories:
        chat_histories[session_id] = []
    return jsonify({'status': 'success'})

# ===== API XÓA CACHE =====
@app.route('/api/clear-cache', methods=['POST'])
def clear_cache():
    RESPONSE_CACHE.clear()
    return jsonify({'status': 'success', 'message': 'Đã xóa cache'})

# ===== TRANG CHATBOT =====
@app.route('/ai-chatbot')
def ai_chatbot_page():
    return render_template('ai_chatbot.html')

# ===== CÁC ROUTE KHÁC =====
@app.route("/upload", methods=["POST"])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "Không tìm thấy file"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Tên file trống"}), 400

    filename = file.filename
    if '..' in filename or filename.startswith('.'):
        return jsonify({"error": "Tên file không hợp lệ"}), 400

    ext = os.path.splitext(filename)[1].lower()
    if ext in BLOCK_EXT or filename in BLOCK_FILES:
        return jsonify({"error": f"Loại file bị chặn"}), 403

    safe_filename = f"{uuid.uuid4().hex}_{filename}"
    file_path = os.path.join(UPLOAD_FOLDER, safe_filename)
    file.save(file_path)
    return jsonify({
        "status": "success",
        "filename": filename,
        "saved_as": safe_filename,
        "size": os.path.getsize(file_path)
    })

@app.route("/compiler", methods=["POST"])
def compiler_old():
    data = request.get_json(silent=True)
    if not data or "code" not in data or "type" not in data:
        return jsonify({"returncode": -1, "stderr": "invalid input"}), 400

    code = data["code"]
    type_ca = data["type"]
    if type_ca not in MODELS:
        return jsonify({"returncode": -1, "stderr": "invalid model"}), 400

    compiler_path = os.path.join(ASMAPP_BASE, type_ca, "compiler_.py")
    if not os.path.exists(compiler_path):
        return jsonify({"returncode": -4, "stderr": "Compiler not found"}), 404

    try:
        p = subprocess.run(
            [sys.executable, compiler_path, "-f", "hex"],
            input=code, text=True, capture_output=True, timeout=18
        )
        return jsonify({"returncode": p.returncode, "stderr": p.stderr, "stdout": p.stdout})
    except subprocess.TimeoutExpired:
        return jsonify({"returncode": -2, "stderr": "timeout"}), 408
    except Exception as e:
        return jsonify({"returncode": -3, "stderr": str(e)}), 500

@app.route("/spell", methods=["POST"])
def spell_api():
    data = request.get_json(silent=True)
    if not data or "code" not in data:
        return jsonify({"out": "invalid input", "returncode": -1}), 400
    code = data["code"]
    spell_path = "util/spell.py"
    if not os.path.exists(spell_path):
        return jsonify({"out": "spell tool not found", "returncode": -4}), 404
    try:
        p = subprocess.run(
            [sys.executable, spell_path],
            input=code, text=True, capture_output=True, timeout=10
        )
        return jsonify({"out": p.stdout or p.stderr, "returncode": p.returncode})
    except subprocess.TimeoutExpired:
        return jsonify({"out": "timeout", "returncode": -2}), 408
    except Exception as e:
        return jsonify({"out": str(e), "returncode": -3}), 500

# ===== STATIC PAGES =====
def serve_static(path, folder=None):
    base = folder or BASE_DIR
    full = os.path.normpath(os.path.join(base, path))
    if not full.startswith(base):
        abort(403)
    for d in BLOCK_DIRS:
        if os.path.commonpath([full, os.path.join(BASE_DIR, d)]) == os.path.join(BASE_DIR, d):
            abort(403)
    if os.path.basename(full) in BLOCK_FILES or any(full.endswith(ext) for ext in BLOCK_EXT):
        abort(403)
    if os.path.isdir(full):
        index = os.path.join(full, "index.html")
        if os.path.exists(index):
            full = index
        else:
            abort(403)
    if not os.path.exists(full):
        abort(404)
    mime, _ = mimetypes.guess_type(full)
    return send_file(full, mimetype=mime or "application/octet-stream")

@app.route("/asm", methods=["GET", "POST"])
def asm_page():
    return serve_static("index.html", ASM_FOLDER)

@app.route("/hex", methods=["GET", "POST"])
def hex_page():
    return serve_static("index.html", HEX_FOLDER)

@app.route("/pixel", methods=["GET", "POST"])
def pixel_page():
    return serve_static("index.html", PIXEL_FOLDER)

@app.route("/spell", methods=["GET", "POST"])
def spell_page():
    if request.method == "POST" and request.is_json:
        return spell_api()
    return serve_static("index.html", SPELL_FOLDER)

@app.route("/donate", methods=["GET", "POST"])
def donate_page():
    return serve_static("index.html", DONATE_FOLDER)

@app.route("/lienhe", methods=["GET", "POST"])
def lienhe_page():
    return serve_static("index.html", LIENHE_FOLDER)

@app.route("/rop")
@app.route("/rop/")
@app.route("/rop/<path:subpath>")
def rop_serve(subpath=""):
    if ".." in subpath or subpath.startswith("."):
        abort(403)
    
    if subpath == "" or subpath == "/":
        full_path = os.path.join(ROP_FOLDER, "index.html")
        if not os.path.exists(full_path):
            full_path = ROP_FOLDER
    else:
        full_path = os.path.join(ROP_FOLDER, subpath)
    
    if not os.path.exists(full_path):
        abort(404)
    
    for d in BLOCK_DIRS:
        if os.path.commonpath([full_path, os.path.join(ROP_FOLDER, d)]) == os.path.join(ROP_FOLDER, d):
            abort(403)
    
    if os.path.basename(full_path) in BLOCK_FILES or any(full_path.endswith(ext) for ext in BLOCK_EXT):
        abort(403)
    
    if os.path.isdir(full_path):
        index_path = os.path.join(full_path, "index.html")
        if os.path.exists(index_path):
            return send_file(index_path)
        abort(403)
    
    mime, _ = mimetypes.guess_type(full_path)
    return send_file(full_path, mimetype=mime or "application/octet-stream")

@app.route("/gop", methods=["GET", "POST"])
def gop_redirect():
    return redirect(url_for('donate_page'), 301)

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
    if ".." in path or "~" in path:
        abort(403)
    if path == "":
        path = "index.html"
    return serve_static(path, BASE_DIR)

# ===== ERROR HANDLERS =====
@app.errorhandler(403)
def forbidden(e):
    return jsonify({"error": "Truy cập bị từ chối"}), 403

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Không tìm thấy"}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Lỗi máy chủ"}), 500

# ===== MỞ TRÌNH DUYỆT =====
def open_browser():
    time.sleep(1.5)
    webbrowser.open(f'http://localhost:{PORT}/ai-chatbot')

# ===== MAIN =====
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 CASIO TOOL SERVER - GEMINI AI CHATBOT")
    print("="*60)
    print(f"📌 Phiên bản: 2.0 (with Gemini AI)")
    print(f"🌐 Địa chỉ: http://localhost:{PORT}")
    print(f"🤖 AI Chatbot: http://localhost:{PORT}/ai-chatbot")
    print(f"📁 Thư mục templates: {TEMPLATES_FOLDER}")
    print(f"🔑 Gemini API: {'✅ Có' if GEMINI_API_KEY and GEMINI_API_KEY != 'your-gemini-key-here' else '❌ Chưa cấu hình'}")
    if model:
        print(f"🤖 Model: Gemini Pro - Sẵn sàng")
    print("="*60)
    
    if not GEMINI_API_KEY or GEMINI_API_KEY == 'your-gemini-key-here':
        print("\n⚠️  CẢNH BÁO: Chưa có Gemini API key!")
        print("📝 Tạo file .env với nội dung:")
        print("   GEMINI_API_KEY=your-actual-gemini-key-here")
        print("🔗 Lấy key tại: https://makersuite.google.com/app/apikey")
        print("💡 Chatbot sẽ hoạt động sau khi cấu hình API key\n")
    
    if not os.environ.get('SPACE_ID'):
        threading.Thread(target=open_browser, daemon=True).start()
        print("⏳ Đang mở trình duyệt...")
    
    app.run("0.0.0.0", PORT, debug=True)
