# ai_chatbot.py
import os
import google.generativeai as genai  # Đổi từ openai sang google.generativeai
import json
import uuid
import time
from flask import Blueprint, request, jsonify, session
from dotenv import load_dotenv
from functools import lru_cache

# Load biến môi trường
load_dotenv()

# Cấu hình Google Gemini
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    print("✅ AI Chatbot: Đã tìm thấy Google Gemini API Key")
else:
    print("⚠️ AI Chatbot: Chưa có Google Gemini API Key trong file .env")
    print("🔗 Lấy key miễn phí tại: https://aistudio.google.com/apikey")

# Tạo blueprint
ai_chatbot_bp = Blueprint('ai_chatbot', __name__, url_prefix='/ai-chatbot')

# Cấu trúc website cho AI
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

# Lưu trữ lịch sử chat
chat_histories = {}

# Cache system prompts
@lru_cache(maxsize=32)
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
        base_prompt += f"\nTÍNH NĂNG: {', '.join(tool['features'][:5])}"
        
        if 'models' in tool and tool['models']:
            base_prompt += f"\nMODEL HỖ TRỢ: {', '.join(tool['models'])}"
    
    return base_prompt

@ai_chatbot_bp.route('/chat', methods=['POST'])
def chat():
    """Xử lý chat với AI sử dụng Google Gemini"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Không có dữ liệu'}), 400
            
        message = data.get('message', '').strip()
        session_id = data.get('session_id', str(uuid.uuid4()))
        current_tool = data.get('current_tool', 'home')
        
        if not message:
            return jsonify({'error': 'Tin nhắn trống'}), 400
        
        # Kiểm tra API key
        if not GEMINI_API_KEY:
            return jsonify({
                'error': 'Chưa cấu hình Google Gemini API key',
                'reply': 'Xin lỗi, hiện tại chưa có API key. Vui lòng thêm GEMINI_API_KEY vào file .env\n\n🔗 Lấy key miễn phí tại: https://aistudio.google.com/apikey'
            }), 503
        
        # Tạo session mới nếu cần
        if session_id not in chat_histories:
            chat_histories[session_id] = []
        
        # Thêm tin nhắn user vào history
        chat_histories[session_id].append({
            'role': 'user',
            'content': message,
            'time': time.time()
        })
        
        # Lấy system prompt
        system_prompt = get_system_prompt(current_tool)
        
        # Chuẩn bị history cho Gemini
        history = []
        recent_history = chat_histories[session_id][-11:-1]  # Lấy history trừ tin nhắn cuối
        
        for msg in recent_history:
            if msg['role'] in ['user', 'assistant']:
                role = "user" if msg['role'] == 'user' else "model"
                history.append({
                    "role": role,
                    "parts": [msg['content']]
                })
        
        try:
            # Tạo model với system instruction
            model = genai.GenerativeModel(
                model_name='gemini-1.5-flash',  # Dùng flash cho nhanh và tiết kiệm
                generation_config={
                    'temperature': 0.7,
                    'max_output_tokens': 800,
                    'top_p': 0.9,
                    'top_k': 40
                },
                system_instruction=system_prompt
            )
            
            # Bắt đầu chat với history
            chat = model.start_chat(history=history)
            
            # Gửi tin nhắn
            response = chat.send_message(message)
            bot_reply = response.text
            
        except Exception as e:
            error_str = str(e)
            if "API key" in error_str or "authentication" in error_str.lower():
                bot_reply = "❌ Lỗi xác thực API key. Vui lòng kiểm tra lại GEMINI_API_KEY trong file .env"
            elif "quota" in error_str or "limit" in error_str.lower() or "rate" in error_str.lower():
                bot_reply = "⚠️ Đã vượt quá giới hạn sử dụng Gemini API. Vui lòng thử lại sau ít phút.\n\nGemini có giới hạn 60 requests/phút cho bản miễn phí."
            else:
                bot_reply = f"❌ Có lỗi xảy ra: {error_str[:200]}"
        
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
            'session_id': session_id,
            'model': 'gemini-1.5-flash'
        })
        
    except Exception as e:
        return jsonify({'error': f'Lỗi hệ thống: {str(e)}'}), 500

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
    
    # Gợi ý mặc định
    default_suggestions = [
        'Các công cụ hiện có',
        'Hướng dẫn ASM',
        'Cách upload file',
        'Liên hệ hỗ trợ',
        'Lấy API key Gemini'
    ]
    
    # Thêm gợi ý mặc định nếu chưa đủ
    for suggestion in default_suggestions:
        if len(suggestions) >= 5:
            break
        if suggestion not in suggestions:
            suggestions.append(suggestion)
    
    return suggestions[:5]

@ai_chatbot_bp.route('/history/<session_id>', methods=['GET'])
def get_history(session_id):
    """Lấy lịch sử chat"""
    history = chat_histories.get(session_id, [])
    # Chỉ lấy 20 tin nhắn gần nhất
    return jsonify(history[-20:])

@ai_chatbot_bp.route('/clear-history/<session_id>', methods=['POST'])
def clear_history(session_id):
    """Xóa lịch sử chat"""
    if session_id in chat_histories:
        chat_histories[session_id] = []
    return jsonify({'status': 'success', 'message': 'Đã xóa lịch sử chat'})

@ai_chatbot_bp.route('/status', methods=['GET'])
def status():
    """Kiểm tra trạng thái AI"""
    return jsonify({
        'status': 'active',
        'api_configured': bool(GEMINI_API_KEY),
        'model': 'gemini-1.5-flash',
        'total_sessions': len(chat_histories),
        'gemini_info': {
            'free_tier': '60 requests/phút',
            'docs': 'https://ai.google.dev/gemini-api/docs'
        }
    })

@ai_chatbot_bp.route('/models', methods=['GET'])
def list_models():
    """Liệt kê các model Gemini có thể dùng"""
    try:
        if GEMINI_API_KEY:
            models = genai.list_models()
            available_models = [
                {'name': m.name, 'display_name': m.display_name}
                for m in models if 'generateContent' in m.supported_generation_methods
            ]
            return jsonify({'models': available_models[:10]})
        else:
            return jsonify({'error': 'Chưa cấu hình API key'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Hàm xóa history cũ (có thể chạy định kỳ)
def cleanup_old_histories(max_age_hours=24):
    """Xóa các history cũ hơn max_age_hours"""
    current_time = time.time()
    for session_id in list(chat_histories.keys()):
        if chat_histories[session_id]:
            last_msg_time = chat_histories[session_id][-1]['time']
            if current_time - last_msg_time > max_age_hours * 3600:
                del chat_histories[session_id]
                print(f"🧹 Đã xóa history cũ: {session_id}")
