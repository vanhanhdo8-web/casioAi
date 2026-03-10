# rop_api.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from pathlib import Path
from main import Model, translate_entry, normalize_address_input, decode_packed_hex_address
import re

app = Flask(__name__)
CORS(app)

MODELS_DIR = Path(__file__).parent / "models"
loaded_models = {}

def get_model(model_name):
    if model_name not in loaded_models:
        model_path = MODELS_DIR / model_name
        if not model_path.exists():
            raise ValueError(f"Model {model_name} không tồn tại")
        loaded_models[model_name] = Model(model_path)
    return loaded_models[model_name]

@app.route('/rop/translate', methods=['POST'])
def translate():
    try:
        data = request.json
        source_model = data.get('source_model')
        target_model = data.get('target_model')
        addresses = data.get('addresses', [])

        if not source_model or not target_model:
            return jsonify({'error': 'Thiếu thông tin model'}), 400

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
                
                # Lấy dòng chi tiết từ model đích
                target_line = None
                if translation.target_entry.index < len(target.entries):
                    entry = target.entries[translation.target_entry.index]
                    target_line = f"{entry.address_text} {entry.opcode} ..."
                
                results.append({
                    'source': addr,
                    'target': translation.target_entry.address_text,
                    'confidence': translation.confidence,
                    'details': target_line
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
    app.run(debug=True, port=5000)
