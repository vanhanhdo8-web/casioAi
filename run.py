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

# ===== LOAD BIẾN MÔI TRƯỜNG =====
load_dotenv()

# ===== CẤU HÌNH GEMINI =====
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY') or os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("⚠️  CẢNH BÁO: Chưa có GEMINI_API_KEY trong file .env")
    print("📝 Tạo file .env với nội dung: GEMINI_API_KEY=your-gemini-key-here")
    print("🔗 Lấy key tại: https://aistudio.google.com/apikey")
else:
    print("✅ Đã tìm thấy Google Gemini API Key")
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
    print(f"📁 Đã tạo thư mục templates: {TEMPLATES_FOLDER}")

ASMAPP_BASE = os.path.join(BASE_DIR, 'asmapp')
DECOMPILER_MODELS_DIR = os.path.join(ASMAPP_BASE, 'decompiler', 'models')

MODELS = ['580vnx', '880btg']

# Tạo thư mục
for folder in [UPLOAD_FOLDER, HEX_FOLDER, ASM_FOLDER, PIXEL_FOLDER,
               SPELL_FOLDER, DONATE_FOLDER, LIENHE_FOLDER, ROP_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)
        print(f"📁 Đã tạo thư mục: {folder}")

# ===== BLACKLIST =====
BLOCK_EXT = {".py", ".sh", ".php", ".asp", ".exe", ".dll", ".so"}
BLOCK_FILES = {"run.py", "app.py", "config.py", ".env"}
BLOCK_DIRS = {".git", "__pycache__", "venv", "env"}

app = Flask(__name__, 
            template_folder=TEMPLATES_FOLDER,  # Chỉ định thư mục templates
            static_folder=None)
app.secret_key = os.getenv('SECRET_KEY', 'casio-tool-secret-key-2024')

# ===== HÀM CHAT RESPONSE CHO GEMINI =====
def get_chat_response(user_input, system_prompt=None):
    """Hàm xử lý chat với Gemini"""
    retries = 2  # Số lần thử lại nếu bị nghẽn
    
    # Kiểm tra API key
    if not GEMINI_API_KEY or GEMINI_API_KEY == 'your-gemini-key-here':
        return "⚠️ Chưa cấu hình Google Gemini API key. Vui lòng thêm GEMINI_API_KEY vào biến môi trường.\n\n🔗 Lấy key miễn phí tại: https://aistudio.google.com/apikey"
    
    for i in range(retries + 1):
        try:
            # Cấu hình model
            model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                generation_config={
                    'temperature': 0.7,
                    'max_output_tokens': 800,
                    'top_p': 0.9,
                    'top_k': 40
                }
            )
            
            # Kết hợp system prompt nếu có
            if system_prompt:
                prompt = f"{system_prompt}\n\nNgười dùng: {user_input}\n\nTrợ lý:"
            else:
                prompt = user_input
            
            # Gửi request
            response = model.generate_content(prompt)
            
            if response and response.text:
                return response.text
            return "AI không thể đưa ra câu trả lời lúc này."

        except Exception as e:
            error_str = str(e)
            # Xử lý lỗi quá tải
            if "429" in error_str or "quota" in error_str.lower() or "rate" in error_str.lower():
                if i < retries:
                    time.sleep(2)
                    continue
                return "⚠️ Hệ thống đang quá tải (hết lượt dùng miễn phí). Vui lòng đợi 1 phút rồi thử lại.\n\nGemini có giới hạn 60 requests/phút cho bản miễn phí."
            elif "API key" in error_str or "authentication" in error_str.lower():
                return "❌ Lỗi xác thực API key. Vui lòng kiểm tra lại GEMINI_API_KEY"
            else:
                return f"❌ Lỗi kết nối: {error_str[:200]}"

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

# ===== LƯU TRỮ CHAT HISTORY =====
chat_histories = {}

# ===== HÀM TẠO SYSTEM PROMPT CHO AI =====
def get_system_prompt(tool_context='home'):
    """Tạo system prompt dựa trên context"""
    base_prompt = """Bạn là trợ lý ảo thông minh của Casio Tool Server - công cụ lập trình cho máy tính CASIO.
    
    NHIỆM VỤ:
    - Hướng dẫn người dùng sử dụng các công cụ lập trình CASIO
    - Giải thích code assembly, hex, các khái niệm lập trình
    - Trả lời bằng TIẾNG VIỆT, thân thiện, dễ hiểu
    - Đưa ra ví dụ cụ thể khi hướng dẫn
    - Nếu không biết, nói "Xin lỗi, tôi chưa có thông tin về vấn đề này"
    
    CÁC CÔNG CỤ HIỆN CÓ:
    1. HEX Tool: Xử lý file hex, chỉnh sửa, upload/download
    2. ASM Compiler: Biên dịch assembly (models: 580vnx, 880btg)
    3. Pixel Tool: Vẽ ảnh pixel
    4. Spell Checker: Kiểm tra chính tả
    5. ROP Tool: Công cụ ROP
    """
    
    if tool_context and tool_context in WEBSITE_STRUCTURE:
        tool = WEBSITE_STRUCTURE[tool_context]
        base_prompt += f"\n\nNGƯỜI DÙNG ĐANG Ở: {tool['name']}"
        base_prompt += f"\nMÔ TẢ: {tool['description']}"
        base_prompt += f"\nTÍNH NĂNG: {', '.join(tool['features'])}"
    
    return base_prompt

# ===== ROUTE CHAT ĐƠN GIẢN (CHO TRANG CHATBOT.HTML) =====
@app.route('/chat', methods=['POST'])
def chat_simple():
    """API chat đơn giản không cần session"""
    try:
        data = request.get_json()
        user_input = data.get("message", "").strip()
        
        if not user_input:
            return jsonify({"response": "Vui lòng nhập tin nhắn."})
        
        response = get_chat_response(user_input, get_system_prompt('home'))
        return jsonify({"response": response})
    except Exception as e:
        return jsonify({"response": f"Lỗi: {str(e)}"}), 500

# ===== API AI CHATBOT ĐẦY ĐỦ (CÓ SESSION) =====
@app.route('/api/ai-chat', methods=['POST'])
def ai_chat():
    """Xử lý chat với AI sử dụng Google Gemini (có session)"""
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        session_id = data.get('session_id', str(uuid.uuid4()))
        current_tool = data.get('current_tool', 'home')
        
        if not message:
            return jsonify({'error': 'Tin nhắn trống'}), 400
        
        # Kiểm tra API key
        if not GEMINI_API_KEY or GEMINI_API_KEY == 'your-gemini-key-here':
            return jsonify({'error': 'Chưa cấu hình Google Gemini API key. Vui lòng thêm vào file .env'}), 501
        
        # Tạo session mới nếu cần
        if session_id not in chat_histories:
            chat_histories[session_id] = []
        
        # Thêm tin nhắn user vào history
        chat_histories[session_id].append({
            'role': 'user',
            'content': message,
            'time': time.time()
        })
        
        # Lấy lịch sử gần đây để tạo context
        recent_history = chat_histories[session_id][-6:-1]  # 5 tin nhắn gần nhất (trừ tin hiện tại)
        context = ""
        if recent_history:
            context = "Lịch sử hội thoại gần đây:\n"
            for msg in recent_history:
                role = "Người dùng" if msg['role'] == 'user' else "Trợ lý"
                context += f"{role}: {msg['content']}\n"
        
        # Lấy system prompt
        system_prompt = get_system_prompt(current_tool)
        
        # Kết hợp context với tin nhắn hiện tại
        full_prompt = f"{context}\nNgười dùng: {message}" if context else message
        
        # Gọi hàm xử lý chat
        bot_reply = get_chat_response(full_prompt, system_prompt)
        
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
        suggestions = suggest_actions(bot_reply, current_tool)
        
        return jsonify({
            'reply': bot_reply,
            'suggestions': suggestions,
            'session_id': session_id
        })
        
    except Exception as e:
        error_str = str(e)
        if "API key" in error_str or "authentication" in error_str.lower():
            return jsonify({'error': 'Lỗi xác thực Google Gemini API. Kiểm tra API key trong file .env'}), 401
        elif "quota" in error_str or "limit" in error_str.lower() or "rate" in error_str.lower():
            return jsonify({'error': 'Đã vượt quá giới hạn API Gemini. Thử lại sau.'}), 429
        else:
            return jsonify({'error': f'Lỗi Gemini API: {error_str}'}), 500

def suggest_actions(reply, current_tool):
    """Gợi ý actions dựa trên nội dung reply"""
    suggestions = []
    reply_lower = reply.lower()
    
    # Gợi ý theo tool hiện tại
    if current_tool in WEBSITE_STRUCTURE:
        tool = WEBSITE_STRUCTURE[current_tool]
        suggestions.extend(tool['features'][:2])
    
    # Gợi ý dựa trên nội dung
    if 'hex' in reply_lower:
        suggestions.append('Hướng dẫn HEX Tool')
    if 'asm' in reply_lower or 'assembly' in reply_lower:
        suggestions.append('Hướng dẫn ASM Compiler')
    if 'pixel' in reply_lower:
        suggestions.append('Hướng dẫn Pixel Tool')
    if 'spell' in reply_lower:
        suggestions.append('Hướng dẫn Spell Checker')
    if 'rop' in reply_lower:
        suggestions.append('Hướng dẫn ROP Tool')
    
    # Thêm gợi ý mặc định
    default_suggestions = ['Các công cụ', 'Hướng dẫn ASM', 'Upload file', 'Liên hệ']
    for suggestion in default_suggestions:
        if len(suggestions) >= 5:
            break
        if suggestion not in suggestions:
            suggestions.append(suggestion)
    
    return list(set(suggestions))[:5]

@app.route('/api/chat-history/<session_id>', methods=['GET'])
def get_chat_history(session_id):
    """Lấy lịch sử chat"""
    history = chat_histories.get(session_id, [])
    return jsonify(history[-20:])

@app.route('/api/clear-history/<session_id>', methods=['POST'])
def clear_chat_history(session_id):
    """Xóa lịch sử chat"""
    if session_id in chat_histories:
        chat_histories[session_id] = []
    return jsonify({'status': 'success'})

# ===== TRANG CHATBOT CHÍNH (DÙNG FILE TỪ TEMPLATES) =====
@app.route('/chatbot')
def chatbot_page():
    """Trang chatbot chính - sử dụng file chatbot.html từ thư mục templates"""
    try:
        return render_template('chatbot.html')
    except Exception as e:
        return f"Lỗi: Không tìm thấy file chatbot.html trong thư mục templates. Chi tiết: {str(e)}", 404

# ===== TRANG CHATBOT AI ĐẦY ĐỦ (CŨ) =====
@app.route('/ai-chatbot')
def ai_chatbot_page():
    """Trang chatbot AI đầy đủ (giữ nguyên code HTML từ file cũ) - CÓ THỂ XÓA NẾU KHÔNG DÙNG"""
    html_content = """<!DOCTYPE html>
<html>
<head><title>AI Chatbot</title></head>
<body>
    <h1>AI Chatbot</h1>
    <p>Đã chuyển sang trang chatbot mới: <a href="/chatbot">/chatbot</a></p>
</body>
</html>
    """
    return html_content

# ===== KIỂM TRA COMPILER =====
for model in MODELS:
    model_dir = os.path.join(ASMAPP_BASE, model)
    if not os.path.isdir(model_dir):
        print(f"⚠️  Cảnh báo: Thư mục model '{model_dir}' không tồn tại.")
    else:
        compiler_file = os.path.join(model_dir, 'compiler_.py')
        if not os.path.exists(compiler_file):
            print(f"⚠️  Thiếu compiler cho {model} tại {compiler_file}")
        else:
            print(f"✅ Tìm thấy compiler cho {model}")

# ===== DECOMPILER =====
sys.path.insert(0, os.path.join(ASMAPP_BASE, 'decompiler'))
try:
    from libdecompiler import get_disas, get_commands, decompile
    print("✅ Đã import libdecompiler.")
except ImportError as e:
    print(f"⚠️  Không import được libdecompiler: {e}")
    def get_disas(*args, **kwargs): raise NotImplementedError
    def get_commands(*args, **kwargs): raise NotImplementedError
    def decompile(*args, **kwargs): raise NotImplementedError

def check_decompiler_models():
    if not os.path.isdir(DECOMPILER_MODELS_DIR):
        print(f"⚠️  Không tìm thấy {DECOMPILER_MODELS_DIR}")
        return
    models = [d for d in os.listdir(DECOMPILER_MODELS_DIR) 
              if os.path.isdir(os.path.join(DECOMPILER_MODELS_DIR, d))]
    required_files = ['config.py', 'disas', 'gadgets', 'labels']
    for model in models:
        model_path = os.path.join(DECOMPILER_MODELS_DIR, model)
        missing = [f for f in required_files if not os.path.isfile(os.path.join(model_path, f))]
        if missing:
            print(f"⚠️  Decompiler model '{model}' thiếu: {', '.join(missing)}")
        else:
            print(f"✅ Decompiler model '{model}' sẵn sàng.")
check_decompiler_models()

# ===== LOGGING =====
@app.before_request
def log_input():
    g.req_id = str(uuid.uuid4())
    g.start_time = time.time()
    body = ""
    if request.method in ["POST", "PUT"]:
        try:
            body = request.get_data(as_text=True)
        except:
            body = "<binary>"
    print(json.dumps({
        "type": "REQUEST",
        "req_id": g.req_id,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "method": request.method,
        "path": request.path,
        "body": body[:200] + ("..." if len(body) > 200 else "")
    }, ensure_ascii=False), flush=True)

# ===== API UPLOAD =====
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

# ===== COMPILER =====
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

def compiler_new(code, model):
    try:
        compiler_path = os.path.join(ASMAPP_BASE, model, "compiler_.py")
        if not os.path.exists(compiler_path):
            return {"returncode": -4, "stderr": f"Compiler {model} not found"}, 404
        p = subprocess.run(
            [sys.executable, compiler_path, "-f", "hex"],
            input=code, text=True, capture_output=True, timeout=15
        )
        return {"returncode": p.returncode, "stderr": p.stderr, "stdout": p.stdout}, 200
    except subprocess.TimeoutExpired:
        return {"returncode": -2, "stderr": "timeout"}, 408
    except Exception as e:
        return {"returncode": -5, "stderr": str(e)}, 500

# ===== SPELL =====
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

# ===== DECOMPILER =====
def load_model_config(model_name):
    config_path = os.path.join(DECOMPILER_MODELS_DIR, model_name, 'config.py')
    if not os.path.exists(config_path):
        raise FileNotFoundError(f'Missing config for {model_name}')
    spec = importlib.util.spec_from_file_location('config', config_path)
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    return config

@app.route("/decompile", methods=["POST"])
def decompile_api():
    data = request.get_json(silent=True)
    if not data or "code" not in data:
        return jsonify({"returncode": -1, "stderr": "invalid input"}), 400

    code = data["code"]
    model = data.get("model", "580vnx")
    model_path = os.path.join(DECOMPILER_MODELS_DIR, model)
    if not os.path.isdir(model_path):
        return jsonify({"returncode": -1, "stderr": f"model {model} not found"}), 400

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, dir=TMP_DIR) as f:
        f.write(code)
        input_path = f.name
    output_path = tempfile.mktemp(suffix='.asm', dir=TMP_DIR)

    try:
        cfg = load_model_config(model)
        disas = get_disas(os.path.join(model_path, 'disas'))
        gadgets = get_commands(os.path.join(model_path, 'gadgets'))
        labels = get_commands(os.path.join(model_path, 'labels'))

        result_lines = decompile(
            input_path, output_path,
            disas, gadgets, labels,
            cfg.start_ram, cfg.end_ram
        )
        asm_output = ''.join(result_lines)
        return jsonify({"returncode": 0, "stderr": "", "stdout": asm_output})
    except Exception as e:
        return jsonify({"returncode": -3, "stderr": str(e)}), 500
    finally:
        if os.path.exists(input_path): os.unlink(input_path)
        if os.path.exists(output_path): os.unlink(output_path)

# ===== ROP ROUTES =====
@app.route("/rop")
@app.route("/rop/")
@app.route("/rop/<path:subpath>")
def rop_serve(subpath=""):
    """Phục vụ các file trong thư mục rop"""
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
    if request.method == "POST" and request.is_json:
        data = request.get_json(silent=True)
        if data and "code" in data:
            model = data.get("model", "580vnx")
            res_data, status_code = compiler_new(data["code"], model)
            return jsonify(res_data), status_code
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

@app.route("/gop", methods=["GET", "POST"])
def gop_redirect():
    return redirect(url_for('donate_page'), 301)

@app.route("/asm/LICENSE")
def show_lisma():
    try:
        with open("./asm/LICENSE", "rb") as f:
            data = f.read()
    except FileNotFoundError:
        return "", 404
    return app.response_class(data, mimetype="text/plain; charset=utf-8")

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

# ===== LOG OUTPUT =====
@app.after_request
def log_output(response):
    duration = round((time.time() - g.get("start_time", time.time())) * 1000, 2)
    try:
        body = response.get_data(as_text=True)[:200]
    except:
        body = "<binary>"
    print(json.dumps({
        "type": "RESPONSE",
        "req_id": g.get("req_id"),
        "status": response.status_code,
        "duration_ms": duration,
        "body": body + ("..." if len(body) >= 200 else "")
    }, ensure_ascii=False), flush=True)
    return response

# ===== MỞ TRÌNH DUYỆT =====
def open_browser():
    time.sleep(1.5)
    webbrowser.open(f'http://localhost:{PORT}/chatbot')

# ===== MAIN =====
if __name__ == "__main__":
    print("\n" + "="*50)
    print("🚀 CASIO TOOL SERVER - AI CHATBOT INTEGRATED")
    print("="*50)
    print(f"📌 Phiên bản: 3.0 (with Google Gemini)")
    print(f"🌐 Địa chỉ: http://localhost:{PORT}")
    print(f"🤖 Chatbot chính: http://localhost:{PORT}/chatbot")
    print(f"📁 Thư mục templates: {TEMPLATES_FOLDER}")
    print(f"📁 File chatbot: {os.path.join(TEMPLATES_FOLDER, 'chatbot.html')}")
    print(f"🔑 Google Gemini API: {'✅ Có' if GEMINI_API_KEY and GEMINI_API_KEY != 'your-gemini-key-here' else '❌ Chưa cấu hình'}")
    print("="*50)
    
    if not GEMINI_API_KEY or GEMINI_API_KEY == 'your-gemini-key-here':
        print("\n⚠️  CẢNH BÁO: Chưa có Google Gemini API key!")
        print("📝 Tạo file .env với nội dung:")
        print("   GEMINI_API_KEY=your-actual-gemini-key-here")
        print("🔗 Lấy key miễn phí tại: https://aistudio.google.com/apikey")
        print("💡 Chatbot sẽ hoạt động ở chế độ hạn chế\n")
    else:
        print("\n✅ Google Gemini đã sẵn sàng!")
        print("💰 Gemini có bản miễn phí 60 requests/phút\n")
    
    if not os.environ.get('SPACE_ID'):
        threading.Thread(target=open_browser, daemon=True).start()
        print("⏳ Đang mở trình duyệt...")
    
    app.run("0.0.0.0", PORT, debug=True)
