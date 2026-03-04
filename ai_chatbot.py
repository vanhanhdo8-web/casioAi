# ai_chatbot.py
import os
import google.generativeai as genai
import json
import uuid
import time
from flask import Blueprint, request, jsonify, session
from dotenv import load_dotenv
from functools import lru_cache

# Load biến môi trường
load_dotenv()

# Cấu hình Google Gemini - CHỈ MỘT LẦN DUY NHẤT
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY') or os.environ.get("GEMINI_API_KEY")
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

def get_chat_response(user_input, system_prompt=None):
    """Hàm xử lý chat với Gemini (dùng chung)"""
    retries = 2  # Số lần thử lại nếu bị nghẽn
    
    # Kiểm tra API key
    if not GEMINI_API_KEY:
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
        
        # Lấy lịch sử gần đây để tạo context
        recent_history = chat_histories[session_id][-6:-1]  # 5 tin nhắn gần nhất (trừ tin hiện tại)
        context = ""
        if recent_history:
            context = "Lịch sử hội thoại gần đây:\n"
            for msg in recent_history:
                role = "Người dùng" if msg['role'] == 'user' else "Trợ lý"
                context += f"{role}: {msg['content']}\n"
        
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