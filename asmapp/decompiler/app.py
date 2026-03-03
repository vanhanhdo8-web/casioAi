from flask import Flask, request, jsonify, send_from_directory
import os
import tempfile
import importlib.util

from libdecompiler import get_disas, get_commands, decompile

app = Flask(__name__)

MODELS_DIR = os.path.join(os.path.dirname(__file__), 'models')

def load_model_config(model_name):
    config_path = os.path.join(MODELS_DIR, model_name, 'config.py')
    if not os.path.exists(config_path):
        raise FileNotFoundError(f'Không tìm thấy config.py cho model {model_name}')
    
    spec = importlib.util.spec_from_file_location('config', config_path)
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    return config

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/decompile', methods=['POST'])
def decompile_api():
    data = request.get_json()
    model_name = data.get('model_name')
    hex_content = data.get('hex_content')

    if not model_name or not hex_content:
        return jsonify({'error': 'Thiếu model_name hoặc hex_content'}), 400

    model_path = os.path.join(MODELS_DIR, model_name)
    if not os.path.isdir(model_path):
        return jsonify({'error': f'Model {model_name} không tồn tại'}), 400

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(hex_content)
        input_path = f.name

    output_path = tempfile.mktemp(suffix='.asm')

    try:
        cfg = load_model_config(model_name)

        disas = get_disas(os.path.join(model_path, 'disas.txt'))
        gadgets = get_commands(os.path.join(model_path, 'gadgets.txt'))
        labels = get_commands(os.path.join(model_path, 'labels.txt'))

        result_lines = decompile(
            input_path, output_path,
            disas, gadgets, labels,
            cfg.start_ram, cfg.end_ram
        )

        asm_output = ''.join(result_lines)
        return jsonify({'asm': asm_output})

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(input_path):
            os.unlink(input_path)
        if os.path.exists(output_path):
            os.unlink(output_path)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)