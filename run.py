import subprocess
import os
import mimetypes
from flask import Flask, request, abort, jsonify, g, send_file, redirect, url_for
from flask_cors import CORS
import uuid
import time
import json
import threading
import webbrowser
import tempfile
import importlib.util
import sys
from pathlib import Path

# Import ROP API
sys.path.append(str(Path(__file__).parent / "rop"))
try:
    from main import Model, translate_entry, normalize_address_input, decode_packed_hex_address
    ROP_AVAILABLE = True
    print("✅ Đã import ROP translation module")
except ImportError as e:
    print(f"⚠️  Không import được ROP translation module: {e}")
    ROP_AVAILABLE = False
    # Define dummy functions if import fails
    def Model(*args, **kwargs): raise NotImplementedError
    def translate_entry(*args, **kwargs): raise NotImplementedError
    def normalize_address_input(*args, **kwargs): raise NotImplementedError
    def decode_packed_hex_address(*args, **kwargs): raise NotImplementedError

# ===== XÁC ĐỊNH CỔNG CHẠY =====
PORT = int(os.environ.get('PORT', 7860))

# ===== THƯ MỤC GỐC =====
BASE_DIR = os.getcwd()
TMP_DIR = tempfile.gettempdir()
ROP_DIR = os.path.join(BASE_DIR, 'rop')
MODEL_DIR = os.path.join(ROP_DIR, 'model')

# ===== THƯ MỤC LƯU TRỮ =====
UPLOAD_FOLDER = os.path.join(TMP_DIR, 'uploads')
HEX_FOLDER = os.path.join(BASE_DIR, 'hex')
ASM_FOLDER = os.path.join(BASE_DIR, 'asm')
PIXEL_FOLDER = os.path.join(BASE_DIR, 'pixel')
SPELL_FOLDER = os.path.join(BASE_DIR, 'spell')
DONATE_FOLDER = os.path.join(BASE_DIR, 'donate')
LIENHE_FOLDER = os.path.join(BASE_DIR, 'lienhe')
ROP_FOLDER = os.path.join(BASE_DIR, 'rop')

# Dictionary để cache models ROP
rop_loaded_models = {}

ASMAPP_BASE = os.path.join(BASE_DIR, 'asmapp')
DECOMPILER_MODELS_DIR = os.path.join(ASMAPP_BASE, 'decompiler', 'models')

MODELS = ['580vnx', '880btg']

# Tạo thư mục
for folder in [UPLOAD_FOLDER, HEX_FOLDER, ASM_FOLDER, PIXEL_FOLDER,
               SPELL_FOLDER, DONATE_FOLDER, LIENHE_FOLDER, ROP_FOLDER, MODEL_DIR]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# Kiểm tra ROP models
if ROP_AVAILABLE:
    rop_models = list(Path(MODEL_DIR).glob("*.txt"))
    if rop_models:
        print(f"✅ Tìm thấy {len(rop_models)} ROP models:")
        for model in rop_models:
            print(f"   - {model.name}")
    else:
        print(f"⚠️  Không tìm thấy ROP models trong {MODEL_DIR}")

# Kiểm tra compiler
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

# Decompiler
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

# ===== BLACKLIST =====
BLOCK_EXT = {".py", ".sh", ".php", ".asp", ".exe", ".dll", ".so"}
BLOCK_FILES = {"run.py", "app.py", "config.py", ".env"}
BLOCK_DIRS = {".git", "__pycache__", "venv", "env"}

app = Flask(__name__, static_folder=None)
CORS(app)  # Enable CORS for all routes

# ===== ROP API FUNCTIONS =====
def get_rop_model(model_name):
    """Load ROP model từ file"""
    if not ROP_AVAILABLE:
        raise ValueError("ROP module không available")
    
    if model_name not in rop_loaded_models:
        # Thêm .txt vào tên file nếu chưa có
        if not model_name.endswith('.txt'):
            model_file = f"{model_name}.txt"
        else:
            model_file = model_name
            
        model_path = os.path.join(MODEL_DIR, model_file)
        if not os.path.exists(model_path):
            # Thử tìm file .txt khác
            txt_files = list(Path(MODEL_DIR).glob(f"{model_name}*.txt"))
            if txt_files:
                model_path = str(txt_files[0])
            else:
                raise ValueError(f"Model {model_name} không tồn tại trong {MODEL_DIR}")
        
        rop_loaded_models[model_name] = Model(model_path)
        print(f"✅ Loaded ROP model: {model_name}")
    
    return rop_loaded_models[model_name]

@app.route("/api/rop/translate", methods=["POST"])
def rop_translate_api():
    """API endpoint để dịch địa chỉ ROP"""
    try:
        if not ROP_AVAILABLE:
            return jsonify({"error": "ROP module không khả dụng"}), 500
            
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Invalid JSON data"}), 400
            
        source_model = data.get('source_model')
        target_model = data.get('target_model')
        addresses = data.get('addresses', [])
        
        if not source_model or not target_model:
            return jsonify({'error': 'Thiếu thông tin model'}), 400
            
        if not addresses:
            return jsonify({'error': 'Danh sách địa chỉ trống'}), 400
            
        # Load models
        try:
            source = get_rop_model(source_model)
            target = get_rop_model(target_model)
        except ValueError as e:
            return jsonify({'error': str(e)}), 404
            
        results = []
        for addr in addresses:
            try:
                # Chuẩn hóa địa chỉ đầu vào
                import re
                if re.match(r'^([0-9A-Fa-f]{2}\s*){4}$', addr) or re.match(r'^[0-9A-Fa-f]{8}$', addr):
                    formatted_addr = decode_packed_hex_address(addr)
                else:
                    formatted_addr = normalize_address_input(addr)
                
                # Tìm entry trong model nguồn
                source_entry = source.get_by_address(formatted_addr)
                if not source_entry:
                    results.append({
                        'source': addr,
                        'error': f'Không tìm thấy địa chỉ {formatted_addr}'
                    })
                    continue
                
                # Dịch sang model đích
                translation = translate_entry(source, target, source_entry)
                if not translation:
                    results.append({
                        'source': addr,
                        'error': 'Không tìm thấy bản dịch'
                    })
                    continue
                
                results.append({
                    'source': addr,
                    'target': translation.target_entry.address_text,
                    'confidence': translation.confidence
                })
                
            except Exception as e:
                results.append({
                    'source': addr,
                    'error': str(e)
                })
        
        return jsonify(results)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/api/rop/models", methods=["GET"])
def rop_models_list():
    """API endpoint để lấy danh sách models ROP có sẵn"""
    try:
        models = []
        for model_file in Path(MODEL_DIR).glob("*.txt"):
            models.append({
                'name': model_file.stem,  # Tên không có .txt
                'file': model_file.name,
                'size': model_file.stat().st_size
            })
        return jsonify(models)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/api/rop/translate/batch", methods=["POST"])
def rop_translate_batch():
    """API endpoint để dịch batch nhiều địa chỉ từ file"""
    try:
        if not ROP_AVAILABLE:
            return jsonify({"error": "ROP module không khả dụng"}), 500
            
        if 'file' not in request.files:
            return jsonify({'error': 'Không tìm thấy file'}), 400
            
        file = request.files['file']
        source_model = request.form.get('source_model')
        target_model = request.form.get('target_model')
        
        if not source_model or not target_model:
            return jsonify({'error': 'Thiếu thông tin model'}), 400
            
        # Đọc địa chỉ từ file
        content = file.read().decode('utf-8')
        addresses = [line.strip() for line in content.split('\n') if line.strip()]
        
        # Gọi API translate với danh sách địa chỉ
        data = {
            'source_model': source_model,
            'target_model': target_model,
            'addresses': addresses
        }
        
        # Tạo request context và gọi hàm translate
        with app.test_request_context('/api/rop/translate', method='POST', json=data):
            response = rop_translate_api()
            return response
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

# ===== ROP ROUTES (Static files) =====
@app.route("/rop")
@app.route("/rop/")
@app.route("/rop/<path:subpath>")
def rop_serve(subpath=""):
    """Phục vụ các file trong thư mục rop"""
    # Kiểm tra path traversal
    if ".." in subpath or subpath.startswith("."):
        abort(403)
    
    # Xác định đường dẫn đầy đủ
    if subpath == "" or subpath == "/":
        full_path = os.path.join(ROP_FOLDER, "index.html")
        if not os.path.exists(full_path):
            full_path = ROP_FOLDER
    else:
        full_path = os.path.join(ROP_FOLDER, subpath)
    
    # Kiểm tra tồn tại
    if not os.path.exists(full_path):
        abort(404)
    
    # Kiểm tra blacklist
    for d in BLOCK_DIRS:
        if os.path.commonpath([full_path, os.path.join(ROP_FOLDER, d)]) == os.path.join(ROP_FOLDER, d):
            abort(403)
    
    if os.path.basename(full_path) in BLOCK_FILES or any(full_path.endswith(ext) for ext in BLOCK_EXT):
        abort(403)
    
    # Nếu là thư mục, tìm index.html
    if os.path.isdir(full_path):
        index_path = os.path.join(full_path, "index.html")
        if os.path.exists(index_path):
            return send_file(index_path)
        abort(403)
    
    # Gửi file
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

# ===== MỞ TRÌNH DUYỆT (local) =====
def open_browser():
    time.sleep(1.5)
    webbrowser.open(f'http://localhost:{PORT}')

if __name__ == "__main__":
    print(f"\n🚀 Casio Tool Server đang chạy tại http://0.0.0.0:{PORT}")
    print(f"📁 Upload tạm: {UPLOAD_FOLDER}")
    print(f"📁 ROP Directory: {ROP_FOLDER}")
    print(f"📁 ROP Models: {MODEL_DIR}")
    
    # Hiển thị ROP API endpoints
    if ROP_AVAILABLE:
        print("\n📡 ROP API Endpoints:")
        print("   POST /api/rop/translate - Dịch địa chỉ ROP")
        print("   GET  /api/rop/models   - Danh sách models")
        print("   POST /api/rop/translate/batch - Dịch batch từ file")
    
    if not os.environ.get('SPACE_ID'):
        threading.Thread(target=open_browser, daemon=True).start()
        print("\n⏳ Đang mở trình duyệt...")
    
    app.run("0.0.0.0", PORT, debug=True)
