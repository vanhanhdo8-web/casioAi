# run.py
import subprocess
import os
import mimetypes
from flask import Flask, request, abort, jsonify, send_file, redirect, url_for, render_template
import uuid
import time
import json
import threading
import webbrowser
import tempfile
import sys
from dotenv import load_dotenv
import google.generativeai as genai
import hashlib
import re
from werkzeug.utils import secure_filename
import logging
import base64
from PIL import Image
import io
from datetime import datetime
from typing import List, Dict, Any, Optional

# ===== CẤU HÌNH LOGGING =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== LOAD BIẾN MÔI TRƯỜNG =====
if os.path.exists('.env'):
    load_dotenv()
    print("📝 Đã load biến môi trường từ file .env (local mode)")
else:
    print("☁️ Chạy trên môi trường cloud (Render)")
    print("⚠️ Tạo file .env với nội dung: GEMINI_API_KEY=your_key_here")

# ===== CẤU HÌNH GEMINI =====
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    print("⚠️ CẢNH BÁO: Chưa có GEMINI_API_KEY trong biến môi trường")
else:
    print("✅ Đã tìm thấy Gemini API Key")
    genai.configure(api_key=GEMINI_API_KEY)

# ===== XÁC ĐỊNH CỔNG CHẠY =====
PORT = int(os.environ.get('PORT', 7860))

# ===== THƯ MỤC GỐC =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TMP_DIR = tempfile.gettempdir()

# ===== THƯ MỤC LƯU TRỮ =====
UPLOAD_FOLDER = os.path.join(TMP_DIR, 'casio_uploads')
TEMPLATES_FOLDER = os.path.join(BASE_DIR, 'templates')

# Tạo thư mục cần thiết
for folder in [UPLOAD_FOLDER, TEMPLATES_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)
        print(f"📁 Đã tạo thư mục: {folder}")

# ===== KIỂM TRA FILE TEMPLATE =====
TEMPLATE_FILE = os.path.join(TEMPLATES_FOLDER, 'ai_chatbot.html')
if not os.path.exists(TEMPLATE_FILE):
    print(f"❌ KHÔNG TÌM THẤY FILE TEMPLATE: {TEMPLATE_FILE}")
    print("📝 Tạo file templates/ai_chatbot.html với nội dung HTML đã cung cấp")
else:
    print(f"✅ Đã tìm thấy template: {TEMPLATE_FILE}")

# ===== BLACKLIST =====
BLOCK_EXT = {".py", ".sh", ".php", ".asp", ".exe", ".dll", ".so"}
BLOCK_FILES = {"run.py", "app.py", "config.py", ".env"}
BLOCK_DIRS = {".git", "__pycache__", "venv", "env"}

MODELS = ['580vnx', '880btg']

app = Flask(__name__, template_folder=TEMPLATES_FOLDER)
app.secret_key = os.environ.get('SECRET_KEY', 'casio-tool-secret-key-2024')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max
app.config['JSON_AS_ASCII'] = False  # Hỗ trợ tiếng Việt

# ===== CẤU HÌNH GEMINI MODEL =====
generation_config = {
    "temperature": 0.7,
    "top_p": 0.9,
    "top_k": 40,
    "max_output_tokens": 2048,
}

# Khởi tạo model
model = None
if GEMINI_API_KEY and GEMINI_API_KEY != 'your-gemini-key-here':
    try:
        print("🔄 Đang kết nối Gemini API...")
        genai.configure(api_key=GEMINI_API_KEY)
        
        # Thử các model name khác nhau
        model_names = [
            'models/gemini-1.5-pro',
            'models/gemini-1.0-pro',
            'gemini-1.5-pro',
            'gemini-1.0-pro',
            'gemini-pro'
        ]
        
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

# ===== LƯU TRỮ CHAT HISTORY =====
chat_histories = {}
RESPONSE_CACHE = {}
CACHE_DURATION = 3600  # 1 giờ

# ===== RATE LIMITING =====
RATE_LIMIT = {}
RATE_LIMIT_DURATION = 60
RATE_LIMIT_MAX = 30

def check_rate_limit(ip):
    current_time = time.time()
    
    # Xóa các IP hết hạn
    for client_ip in list(RATE_LIMIT.keys()):
        if current_time - RATE_LIMIT[client_ip]['timestamp'] > RATE_LIMIT_DURATION:
            del RATE_LIMIT[client_ip]
    
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

# ===== HÀM PHÂN TÍCH FILE HEX =====
def analyze_hex_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except:
        with open(file_path, 'r', encoding='latin-1') as f:
            content = f.read()
    
    lines = content.strip().split('\n')
    analysis = {
        'total_lines': len(lines),
        'valid_records': 0,
        'data_bytes': 0,
        'start_address': None,
        'end_address': None,
        'record_types': {},
        'errors': [],
        'file_size': os.path.getsize(file_path)
    }
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
            
        if line.startswith(':'):
            try:
                if len(line) < 11:
                    analysis['errors'].append(f'Dòng {i+1}: Quá ngắn')
                    continue
                    
                byte_count = int(line[1:3], 16)
                address = int(line[3:7], 16)
                record_type = int(line[7:9], 16)
                
                analysis['valid_records'] += 1
                analysis['data_bytes'] += byte_count
                analysis['record_types'][str(record_type)] = analysis['record_types'].get(str(record_type), 0) + 1
                
                if analysis['start_address'] is None or address < int(analysis['start_address'], 16):
                    analysis['start_address'] = f'0x{address:04X}'
                if analysis['end_address'] is None:
                    analysis['end_address'] = f'0x{address + byte_count:04X}'
                    
            except Exception as e:
                analysis['errors'].append(f'Dòng {i+1}: Lỗi format')
        else:
            analysis['errors'].append(f'Dòng {i+1}: Không hợp lệ')
    
    return analysis

# ===== HÀM BIÊN DỊCH ASM =====
def compile_asm_file(file_path, model='580vnx'):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
    except:
        with open(file_path, 'r', encoding='latin-1') as f:
            code = f.read()
    
    lines = code.strip().split('\n')
    code_lines = [l for l in lines if l.strip() and not l.strip().startswith(';')]
    labels = re.findall(r'^([a-zA-Z_][a-zA-Z0-9_]*):', code, re.MULTILINE)
    instructions = re.findall(r'^(?:[a-zA-Z_][a-zA-Z0-9_]*:)?\s*([A-Z]+)', code, re.MULTILINE)
    
    return {
        'model': model,
        'success': True,
        'stats': {
            'total_lines': len(lines),
            'code_lines': len(code_lines),
            'labels': len(labels),
            'instructions': len(instructions),
            'size': len(code)
        },
        'message': f'Đã phân tích file ASM cho model {model}',
        'details': {
            'labels': labels[:10],
            'instructions': list(set(instructions))[:10]
        }
    }

# ===== HÀM XỬ LÝ ẢNH PIXEL =====
def convert_to_pixel_art(file_path):
    try:
        img = Image.open(file_path)
        
        original_size = img.size
        original_format = img.format
        original_mode = img.mode
        
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        pixel_size = 32
        img_small = img.resize((pixel_size, pixel_size), Image.Resampling.NEAREST)
        
        colors = set()
        pixel_data = []
        for y in range(pixel_size):
            row = []
            for x in range(pixel_size):
                r, g, b = img_small.getpixel((x, y))
                hex_color = f'#{r:02x}{g:02x}{b:02x}'
                colors.add(hex_color)
                row.append(hex_color)
            pixel_data.append(row)
        
        img_preview = img_small.resize((256, 256), Image.Resampling.NEAREST)
        buffered = io.BytesIO()
        img_preview.save(buffered, format="PNG")
        preview_base64 = base64.b64encode(buffered.getvalue()).decode()
        
        return {
            'success': True,
            'dimensions': f'{pixel_size}x{pixel_size}',
            'original_size': f'{original_size[0]}x{original_size[1]}',
            'original_format': original_format,
            'original_mode': original_mode,
            'color_count': len(colors),
            'preview': f'data:image/png;base64,{preview_base64}',
            'pixel_data': pixel_data[:5],
            'message': f'Đã chuyển thành pixel art {pixel_size}x{pixel_size} với {len(colors)} màu'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# ===== HÀM KIỂM TRA CHÍNH TẢ =====
def check_spelling(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except:
        with open(file_path, 'r', encoding='latin-1') as f:
            content = f.read()
    
    words = re.findall(r'\b[a-zA-ZÀ-ỹ]+\b', content)
    unique_words = set(words)
    
    suggestions = []
    for word in list(unique_words)[:30]:
        if len(word) > 20:
            suggestions.append(f'Từ quá dài: "{word}"')
        elif any(c.isdigit() for c in word):
            suggestions.append(f'Từ có số: "{word}"')
        elif re.search(r'(.)\1{3,}', word):
            suggestions.append(f'Từ lặp ký tự: "{word}"')
    
    return {
        'success': True,
        'stats': {
            'total_words': len(words),
            'unique_words': len(unique_words),
            'characters': len(content),
            'lines': len(content.split('\n'))
        },
        'suggestions': suggestions[:15],
        'message': f'Đã kiểm tra {len(words)} từ, {len(unique_words)} từ duy nhất'
    }

# ===== HÀM XỬ LÝ FILE TEXT =====
def analyze_text_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except:
        with open(file_path, 'r', encoding='latin-1') as f:
            content = f.read()
    
    lines = content.split('\n')
    words = re.findall(r'\b\w+\b', content)
    
    return {
        'success': True,
        'stats': {
            'lines': len(lines),
            'non_empty_lines': len([l for l in lines if l.strip()]),
            'words': len(words),
            'characters': len(content),
            'size': os.path.getsize(file_path)
        },
        'preview': content[:500] + '...' if len(content) > 500 else content,
        'message': f'File text: {len(lines)} dòng, {len(words)} từ'
    }

# ===== HÀM XỬ LÝ FILE JSON =====
def analyze_json_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        data = json.loads(content)
        
        if isinstance(data, dict):
            structure = {
                'type': 'object',
                'keys': len(data.keys()),
                'sample_keys': list(data.keys())[:10]
            }
        elif isinstance(data, list):
            structure = {
                'type': 'array',
                'length': len(data),
                'sample': data[:5] if len(data) > 5 else data
            }
        else:
            structure = {
                'type': type(data).__name__,
                'value': str(data)[:100]
            }
        
        return {
            'success': True,
            'structure': structure,
            'size': os.path.getsize(file_path),
            'message': f'File JSON: {structure["type"]}'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# ===== HÀM XỬ LÝ FILE CSV =====
def analyze_csv_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if not lines:
            return {'success': False, 'error': 'File rỗng'}
        
        header = lines[0].strip().split(',')
        data_lines = lines[1:11]
        
        return {
            'success': True,
            'stats': {
                'total_lines': len(lines),
                'data_lines': len(lines) - 1,
                'columns': len(header)
            },
            'header': header[:10],
            'sample': [line.strip().split(',')[:10] for line in data_lines],
            'message': f'File CSV: {len(header)} cột, {len(lines)-1} dòng dữ liệu'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# ===== HÀM XỬ LÝ FILE PYTHON =====
def analyze_python_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        lines = code.split('\n')
        classes = re.findall(r'^class\s+(\w+)', code, re.MULTILINE)
        functions = re.findall(r'^def\s+(\w+)', code, re.MULTILINE)
        imports = re.findall(r'^(?:from\s+(\S+)\s+)?import\s+(\S+)', code, re.MULTILINE)
        
        return {
            'success': True,
            'stats': {
                'lines': len(lines),
                'code_lines': len([l for l in lines if l.strip() and not l.strip().startswith('#')]),
                'classes': len(classes),
                'functions': len(functions),
                'imports': len(imports)
            },
            'details': {
                'classes': classes[:10],
                'functions': functions[:10],
                'imports': [f"{i[0]}.{i[1]}" if i[0] else i[1] for i in imports[:10]]
            },
            'message': f'File Python: {len(classes)} class, {len(functions)} function'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# ===== HÀM XỬ LÝ FILE TỔNG HỢP =====
def process_file(file_path, file_ext, tool_name, message):
    message_lower = message.lower() if message else ""
    
    # Xác định tool dựa trên nhiều yếu tố
    if tool_name == 'hex' or 'hex' in message_lower or file_ext == '.hex':
        result = analyze_hex_file(file_path)
        return {
            'tool': 'hex_analyzer',
            'result': result,
            'summary': f"📊 HEX: {result['valid_records']} records, {result['data_bytes']} bytes"
        }
    
    elif tool_name == 'asm' or 'asm' in message_lower or 'assembly' in message_lower or file_ext == '.asm':
        results = {}
        for model in MODELS:
            results[model] = compile_asm_file(file_path, model)
        return {
            'tool': 'asm_compiler',
            'result': results,
            'summary': f"⚙️ ASM: Đã phân tích cho {len(MODELS)} models"
        }
    
    elif tool_name == 'pixel' or 'pixel' in message_lower or 'ảnh' in message_lower or file_ext in ['.jpg', '.jpeg', '.png', '.gif']:
        result = convert_to_pixel_art(file_path)
        summary = f"🎨 Pixel: {result.get('dimensions', 'N/A')}, {result.get('color_count', 0)} màu" if result.get('success') else "❌ Lỗi xử lý ảnh"
        return {
            'tool': 'pixel_converter',
            'result': result,
            'summary': summary
        }
    
    elif tool_name == 'spell' or 'spell' in message_lower or 'chính tả' in message_lower:
        result = check_spelling(file_path)
        return {
            'tool': 'spell_checker',
            'result': result,
            'summary': f"📝 Spell: {result.get('stats', {}).get('total_words', 0)} từ"
        }
    
    # Xử lý theo loại file
    if file_ext == '.txt':
        result = analyze_text_file(file_path)
        return {
            'tool': 'text_analyzer',
            'result': result,
            'summary': f"📄 Text: {result['stats']['lines']} dòng, {result['stats']['words']} từ"
        }
    
    elif file_ext == '.json':
        result = analyze_json_file(file_path)
        return {
            'tool': 'json_analyzer',
            'result': result,
            'summary': f"📋 JSON: {result.get('structure', {}).get('type', 'N/A')}"
        }
    
    elif file_ext == '.csv':
        result = analyze_csv_file(file_path)
        return {
            'tool': 'csv_analyzer',
            'result': result,
            'summary': f"📊 CSV: {result.get('stats', {}).get('columns', 0)} cột"
        }
    
    elif file_ext == '.py':
        result = analyze_python_file(file_path)
        return {
            'tool': 'python_analyzer',
            'result': result,
            'summary': f"🐍 Python: {result.get('stats', {}).get('functions', 0)} functions"
        }
    
    return None

# ===== API CHAT CHÍNH =====
@app.route('/api/ai-chat-with-file', methods=['POST'])
def ai_chat_with_file():
    client_ip = request.remote_addr
    if not check_rate_limit(client_ip):
        return jsonify({'error': 'Quá nhiều yêu cầu, vui lòng thử lại sau'}), 429
    
    try:
        file = request.files.get('file')
        message = request.form.get('message', '').strip()
        session_id = request.form.get('session_id', str(uuid.uuid4()))
        current_tool = request.form.get('current_tool', 'home')
        
        if not file and not message:
            return jsonify({'error': 'Vui lòng nhập tin nhắn hoặc chọn file'}), 400
        
        file_path = None
        file_info = None
        tool_result = None
        
        if file and file.filename:
            filename = secure_filename(file.filename)
            file_ext = os.path.splitext(filename)[1].lower()
            
            allowed_ext = {'.txt', '.hex', '.asm', '.py', '.json', '.csv', '.jpg', '.jpeg', '.png', '.gif'}
            if file_ext not in allowed_ext:
                return jsonify({'error': f'Không hỗ trợ file {file_ext}. Chỉ hỗ trợ: {", ".join(allowed_ext)}'}), 400
            
            # Tạo tên file an toàn
            safe_filename = f"{uuid.uuid4().hex}_{filename}"
            file_path = os.path.join(UPLOAD_FOLDER, safe_filename)
            file.save(file_path)
            
            file_info = {
                'name': filename,
                'size': os.path.getsize(file_path),
                'type': file_ext[1:],  # Bỏ dấu chấm
                'saved_as': safe_filename
            }
            
            # Xử lý file với tool
            tool_result = process_file(file_path, file_ext, current_tool, message)
            
            # Tạo preview cho ảnh
            if file_ext in ['.jpg', '.jpeg', '.png', '.gif']:
                try:
                    img = Image.open(file_path)
                    img.thumbnail((200, 200))
                    buffered = io.BytesIO()
                    img.save(buffered, format="PNG")
                    file_info['preview'] = f"data:image/png;base64,{base64.b64encode(buffered.getvalue()).decode()}"
                except Exception as e:
                    print(f"Không thể tạo preview: {e}")
        
        # Nếu không có API key hoặc model, trả về kết quả xử lý file
        if not GEMINI_API_KEY or GEMINI_API_KEY == 'your-gemini-key-here' or model is None:
            if tool_result:
                reply = f"""**ĐÃ XỬ LÝ FILE THÀNH CÔNG:**

{tool_result['summary']}

```json
{json.dumps(tool_result['result'], ensure_ascii=False, indent=2)[:1000]}
```"""
            else:
                reply = "✅ Đã nhận tin nhắn của bạn. (Đang chạy ở chế độ offline)"
            
            # Xóa file tạm
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            
            return jsonify({
                'reply': reply,
                'session_id': session_id,
                'cached': False,
                'file_info': file_info,
                'tool_result': tool_result,
                'suggestions': ['Hướng dẫn ASM', 'Phân tích HEX', 'Chuyển ảnh pixel', 'Kiểm tra chính tả']
            })
        
        # Xử lý với Gemini AI
        try:
            if session_id not in chat_histories:
                chat_histories[session_id] = []
            
            user_msg = message
            if file_info:
                user_msg += f"\n[Đã gửi: {file_info['name']} ({file_info['size']} bytes)]"
            
            chat_histories[session_id].append({
                'role': 'user',
                'content': user_msg,
                'time': time.time()
            })
            
            system_prompt = """Bạn là trợ lý AI của Casio Tool - công cụ lập trình cho CASIO fx-580VN X và fx-880BTG.

Bạn chuyên về:
- Phân tích file HEX, ASM
- Hướng dẫn lập trình Assembly
- Chuyển đổi ảnh sang pixel art
- Kiểm tra chính tả
- Phân tích file Python, JSON, CSV

Hãy trả lời bằng TIẾNG VIỆT, thân thiện và dễ hiểu. Nếu có lỗi, hãy đề xuất cách sửa."""

            context = ""
            recent = chat_histories[session_id][-5:]
            for msg in recent[:-1]:
                context += f"{msg['role']}: {msg['content']}\n"
            
            if tool_result:
                result_str = json.dumps(tool_result['result'], ensure_ascii=False, indent=2)
                if len(result_str) > 1500:
                    result_str = result_str[:1500] + "...\n(Kết quả bị cắt do quá dài)"
                
                full_prompt = f"""{system_prompt}

LỊCH SỬ CHAT:
{context}

USER: {message}

THÔNG TIN FILE: {json.dumps(file_info, ensure_ascii=False)}

KẾT QUẢ XỬ LÝ BẰNG CÔNG CỤ {tool_result['tool']}:
```json
{result_str}
```"""
            else:
                full_prompt = f"""{system_prompt}

LỊCH SỬ CHAT:
{context}

USER: {message}"""
            
            # Kiểm tra cache
            cache_key = hashlib.md5(full_prompt.encode()).hexdigest()
            if cache_key in RESPONSE_CACHE:
                if time.time() - RESPONSE_CACHE[cache_key]['time'] < CACHE_DURATION:
                    reply = RESPONSE_CACHE[cache_key]['reply']
                    
                    # Xóa file tạm
                    if file_path and os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except:
                            pass
                    
                    return jsonify({
                        'reply': reply,
                        'session_id': session_id,
                        'cached': True,
                        'file_info': file_info,
                        'tool_result': tool_result,
                        'suggestions': ['Phân tích HEX', 'Biên dịch ASM', 'Chuyển ảnh pixel', 'Kiểm tra chính tả']
                    })
            
            # Gọi Gemini API
            try:
                response = model.generate_content(
                    full_prompt,
                    generation_config={
                        "temperature": 0.7,
                        "max_output_tokens": 1024,
                    }
                )
                reply = response.text
                
                # Lưu cache
                RESPONSE_CACHE[cache_key] = {
                    'reply': reply,
                    'time': time.time()
                }
                
            except Exception as e:
                reply = f"Xin lỗi, có lỗi khi gọi AI: {str(e)}. Tôi vẫn có thể xử lý file cho bạn!"
            
            # Lưu lịch sử
            chat_histories[session_id].append({
                'role': 'assistant',
                'content': reply,
                'time': time.time()
            })
            
            # Giới hạn lịch sử
            if len(chat_histories[session_id]) > 50:
                chat_histories[session_id] = chat_histories[session_id][-50:]
            
            # Xóa file tạm
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            
            # Tạo suggestions dựa trên tool
            suggestions = []
            if tool_result:
                if 'hex' in tool_result['tool']:
                    suggestions = ['Phân tích HEX khác', 'Hướng dẫn sửa HEX', 'Chuyển sang ASM', 'Cấu trúc file HEX']
                elif 'asm' in tool_result['tool']:
                    suggestions = ['Biên dịch cho model khác', 'Tối ưu code', 'Debug ASM', 'Hướng dẫn ASM']
                elif 'pixel' in tool_result['tool']:
                    suggestions = ['Chuyển ảnh khác', 'Điều chỉnh màu sắc', 'Xuất pixel art', 'Tạo sprite']
                elif 'spell' in tool_result['tool']:
                    suggestions = ['Kiểm tra file khác', 'Sửa lỗi chính tả', 'Gợi ý từ', 'Kiểm tra văn bản']
                else:
                    suggestions = ['Phân tích HEX', 'Biên dịch ASM', 'Chuyển ảnh pixel', 'Kiểm tra chính tả']
            else:
                suggestions = ['Hướng dẫn ASM', 'Phân tích HEX', 'Chuyển ảnh pixel', 'Kiểm tra chính tả']
            
            return jsonify({
                'reply': reply,
                'suggestions': suggestions[:5],
                'session_id': session_id,
                'cached': False,
                'file_info': file_info,
                'tool_result': tool_result
            })
            
        except Exception as e:
            logger.error(f"Lỗi xử lý AI: {str(e)}")
            # Fallback: trả về kết quả xử lý file
            if tool_result:
                reply = f"""**ĐÃ XỬ LÝ FILE THÀNH CÔNG:**

{tool_result['summary']}

```json
{json.dumps(tool_result['result'], ensure_ascii=False, indent=2)[:1000]}
```"""
            else:
                reply = f"✅ Đã nhận tin nhắn. (Lỗi AI: {str(e)})"
            
            return jsonify({
                'reply': reply,
                'session_id': session_id,
                'cached': False,
                'file_info': file_info,
                'tool_result': tool_result,
                'suggestions': ['Hướng dẫn ASM', 'Phân tích HEX', 'Chuyển ảnh pixel', 'Kiểm tra chính tả']
            })
        
    except Exception as e:
        logger.error(f"Lỗi hệ thống: {str(e)}")
        return jsonify({'error': f'Lỗi hệ thống: {str(e)}'}), 500

# ===== API KIỂM TRA SỨC KHỎE =====
@app.route('/api/ai-health', methods=['GET'])
def ai_health():
    return jsonify({
        'status': 'ok',
        'api_configured': model is not None,
        'cache_size': len(RESPONSE_CACHE),
        'active_sessions': len(chat_histories),
        'supported_files': ['.txt', '.hex', '.asm', '.py', '.json', '.csv', '.jpg', '.jpeg', '.png', '.gif'],
        'template_exists': os.path.exists(TEMPLATE_FILE)
    })

# ===== API LỊCH SỬ =====
@app.route('/api/chat-history/<session_id>', methods=['GET'])
def get_chat_history(session_id):
    history = chat_histories.get(session_id, [])
    return jsonify(history[-50:])

# ===== API XÓA LỊCH SỬ =====
@app.route('/api/clear-history/<session_id>', methods=['POST'])
def clear_chat_history(session_id):
    if session_id in chat_histories:
        chat_histories[session_id] = []
    return jsonify({'status': 'ok'})

# ===== API XÓA CACHE =====
@app.route('/api/clear-cache', methods=['POST'])
def clear_cache():
    RESPONSE_CACHE.clear()
    return jsonify({'status': 'ok', 'message': 'Đã xóa cache'})

# ===== DEBUG =====
@app.route('/debug')
def debug():
    return jsonify({
        'gemini_api': bool(GEMINI_API_KEY),
        'model': str(model) if model else None,
        'upload_folder': UPLOAD_FOLDER,
        'templates': TEMPLATES_FOLDER,
        'template_file': TEMPLATE_FILE,
        'template_exists': os.path.exists(TEMPLATE_FILE),
        'python_version': sys.version,
        'cwd': BASE_DIR
    })

# ===== FAVICON =====
@app.route('/favicon.ico')
def favicon():
    return '', 204

# ===== TRANG CHATBOT =====
@app.route('/ai-chatbot')
def ai_chatbot_page():
    if not os.path.exists(TEMPLATE_FILE):
        return f"""
        <html>
        <head><title>Lỗi</title></head>
        <body style="font-family: sans-serif; padding: 20px;">
            <h1>❌ Không tìm thấy file template</h1>
            <p>Đường dẫn: <code>{TEMPLATE_FILE}</code></p>
            <p>Vui lòng tạo file <code>templates/ai_chatbot.html</code> với nội dung HTML đã cung cấp.</p>
            <hr>
            <h3>Thông tin debug:</h3>
            <pre>BASE_DIR: {BASE_DIR}
TEMPLATES_FOLDER: {TEMPLATES_FOLDER}
TEMPLATE_FILE: {TEMPLATE_FILE}
Tồn tại: {os.path.exists(TEMPLATE_FILE)}</pre>
        </body>
        </html>
        """, 404
    return render_template('ai_chatbot.html')

# ===== TRANG CHỦ =====
@app.route('/')
def home():
    return redirect('/ai-chatbot')

# ===== UPLOAD FILE =====
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'Không tìm thấy file'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Tên file trống'}), 400
    
    filename = secure_filename(file.filename)
    safe_filename = f"{uuid.uuid4().hex}_{filename}"
    file_path = os.path.join(UPLOAD_FOLDER, safe_filename)
    file.save(file_path)
    
    return jsonify({
        'status': 'success',
        'filename': filename,
        'saved_as': safe_filename,
        'size': os.path.getsize(file_path)
    })

# ===== ERROR HANDLERS =====
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Không tìm thấy'}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Lỗi máy chủ'}), 500

# ===== MỞ TRÌNH DUYỆT =====
def open_browser():
    time.sleep(1.5)
    try:
        webbrowser.open(f'http://localhost:{PORT}/ai-chatbot')
    except:
        pass

# ===== MAIN =====
if __name__ == '__main__':
    print("\n" + "="*70)
    print("🚀 CASIO TOOL SERVER - AI CHATBOT")
    print("="*70)
    print(f"📌 Địa chỉ: http://localhost:{PORT}")
    print(f"🤖 Chatbot: http://localhost:{PORT}/ai-chatbot")
    print(f"🔑 Gemini API: {'✅ Có' if model else '❌ Chưa cấu hình'}")
    print(f"📁 Thư mục gốc: {BASE_DIR}")
    print(f"📁 Templates: {TEMPLATES_FOLDER}")
    print(f"📁 Upload: {UPLOAD_FOLDER}")
    print(f"📄 Template file: {'✅ Tồn tại' if os.path.exists(TEMPLATE_FILE) else '❌ Không tìm thấy'}")
    print("="*70)
    print("\n📂 HỖ TRỢ CÁC LOẠI FILE:")
    print("  ✅ .hex - Phân tích HEX")
    print("  ✅ .asm - Biên dịch Assembly")
    print("  ✅ .jpg/.png/.gif - Chuyển pixel art")
    print("  ✅ .txt - Kiểm tra chính tả")
    print("  ✅ .py - Phân tích Python")
    print("  ✅ .json - Phân tích JSON")
    print("  ✅ .csv - Phân tích CSV")
    print("="*70)
    
    if not model:
        print("\n⚠️ CHƯA CÓ API KEY GEMINI")
        print("📝 Thêm vào file .env: GEMINI_API_KEY=your_key_here")
        print("🔗 Lấy key tại: https://makersuite.google.com/app/apikey")
        print("💡 Chatbot vẫn hoạt động với chức năng xử lý file!\n")
    
    # Mở trình duyệt
    try:
        threading.Thread(target=open_browser, daemon=True).start()
    except:
        pass
    
    # Chạy app
    app.run(host='0.0.0.0', port=PORT, debug=True, threaded=True)
