# rop_api.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from pathlib import Path
import sys
import re

# Thêm thư mục hiện tại vào path để import main.py
sys.path.append(str(Path(__file__).parent))

from main import Model, translate_entry, normalize_address_input, decode_packed_hex_address

app = Flask(__name__)
CORS(app)

# Đường dẫn đến thư mục model (không có 's' ở cuối) - giống với index.html
MODEL_DIR = Path(__file__).parent / "model"  # /rop/model/
loaded_models = {}

def get_model(model_name):
    """Load model từ file"""
    if model_name not in loaded_models:
        # Thêm .txt vào tên file
        model_path = MODEL_DIR / f"{model_name}.txt"
        if not model_path.exists():
            raise ValueError(f"Model {model_name} không tồn tại")
        loaded_models[model_name] = Model(model_path)
    return loaded_models[model_name]

@app.route('/api/rop/translate', methods=['POST'])
def translate():
    """API endpoint để dịch địa chỉ ROP"""
    try:
        data = request.json
        source_model = data.get('source_model')
        target_model = data.get('target_model')
        addresses = data.get('addresses', [])

        if not source_model or not target_model:
            return jsonify({'error': 'Thiếu thông tin model'}), 400

        # Load models
        source = get_model(source_model)
        target = get_model(target_model)
        
        results = []
        for addr in addresses:
            try:
                # Chuẩn hóa địa chỉ đầu vào
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

if __name__ == '__main__':
    print("ROP Translation API Server")
    print("==========================")
    print("Model directory:", MODEL_DIR)
    print("Available models:", [f.name for f in MODEL_DIR.glob("*.txt") if f.is_file()])
    print("\nStarting server at http://localhost:5000")
    app.run(debug=True, port=5000)
