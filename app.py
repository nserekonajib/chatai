from flask import Flask, render_template, request, jsonify, session, Response, stream_with_context
import requests
import json
from functools import wraps
import PyPDF2
import os
from werkzeug.utils import secure_filename
import uuid
from datetime import datetime, timezone
import re
from supabase import create_client, Client
from dotenv import load_dotenv
import markdown
import time
from concurrent.futures import ThreadPoolExecutor


# Initialize thread pool for background tasks
executor = ThreadPoolExecutor(max_workers=4)

load_dotenv()

app = Flask(__name__)
app.secret_key = "hguwewjdjdjassyuwjhvagywehvcauucyjqhwqxvjzkgxcygqwehqwxbxsagcyeukcgkhcbxhqwghgy"

# Configuration
SUPABASE_URL = "https://wbpeabugoqfwziayrabr.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6IndicGVhYnVnb3Fmd3ppYXlyYWJyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDcxMjg4MjUsImV4cCI6MjA2MjcwNDgyNX0.VBUvqPffjcmiMIxhHhoGHh0aaYwrfaO2iJrI-AHXiDs"
OPENROUTER_API_KEY = "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"
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Initialize Supabase
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Auth decorator
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return wrapper

# Utility Functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_pdf_text(filepath):
    try:
        with open(filepath, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            text = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text.append(page_text)
            return "\n".join(text)
    except Exception as e:
        print(f"PDF Extraction Error: {str(e)}")
        return None

def format_markdown(content):
    # Convert markdown to HTML with proper code highlighting
    extensions = ['fenced_code', 'codehilite', 'tables']
    html = markdown.markdown(content, extensions=extensions)
    
    # Add copy buttons to code blocks
    def add_copy_button(match):
        code_id = f"code-{uuid.uuid4().hex[:8]}"
        return f"""
        <div class="code-block-wrapper">
            <div class="code-block-header">
                <button onclick="copyToClipboard('{code_id}')" class="copy-button">
                    <i class="fas fa-copy"></i> Copy
                </button>
            </div>
            <pre id="{code_id}"><code>{match.group(1)}</code></pre>
        </div>
        """
    
    return re.sub(r'<pre><code>(.*?)</code></pre>', add_copy_button, html, flags=re.DOTALL)

def save_message_async(user_id, content, role, chat_id=None):
    """Save message in background thread to improve response time"""
    def _save(chat_id=chat_id):
        try:
            chat_id = chat_id or str(uuid.uuid4())
            supabase.table('chat_history').insert({
                'user_id': user_id,
                'message': content,
                'role': role,
                'chat_id': chat_id,
                'created_at': datetime.now(timezone.utc).isoformat()
            }).execute()
            return chat_id
        except Exception as e:
            print(f"Error saving message: {str(e)}")
            return chat_id

    # Submit to thread pool and return immediately
    future = executor.submit(_save)
    return future.result()  # This will block until done, but runs in separate thread

def get_chat_history(user_id, chat_id=None, limit=50):
    """Optimized chat history retrieval with pagination"""
    try:
        query = supabase.table('chat_history').select('*').eq('user_id', user_id)
        if chat_id:
            query = query.eq('chat_id', chat_id)
        return query.order('created_at', desc=False).limit(limit).execute().data
    except Exception as e:
        print(f"Error fetching chat history: {str(e)}")
        return []

def get_user_chats(user_id, limit=20):
    """Fetch the most recent message from each chat for the user."""
    try:
        rows = supabase.table('chat_history') \
            .select('*') \
            .eq('user_id', user_id) \
            .order('created_at', desc=True) \
            .limit(100).execute().data

        # Group by chat_id, get latest message per chat
        chats = {}
        for row in rows:
            cid = row['chat_id']
            if cid not in chats:
                chats[cid] = row
        # Sort by created_at desc, limit
        chat_list = sorted(chats.values(), key=lambda x: x['created_at'], reverse=True)[:limit]
        return [{
            'id': chat['chat_id'],
            'title': chat['message'][:50] + '...' if len(chat['message']) > 50 else chat['message'],
            'created_at': chat['created_at']
        } for chat in chat_list]
    except Exception as e:
        print(f"Error fetching user chats: {str(e)}")
        return []
    
@app.route('/love', methods=['POST', 'GET'])
def love():
      if 'user' in session:
        chats = get_user_chats(session['user']['id'])
        return render_template('chat.html', user=session['user'], chats=chats)
      return render_template('auth.html')
 
    

# Routes
@app.route('/')
def home():
    
    if 'user' in session:
        chats = get_user_chats(session['user']['id'])
        return render_template('chat.html', user=session['user'], chats=chats)
    return render_template('index.html')

@app.route('/auth', methods=['POST', 'GET'])
def auth():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    action = data.get('action', 'login')
    
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    
    try:
        if action == 'login':
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        else:
            res = supabase.auth.sign_up({"email": email, "password": password})
        
        if res.user:
            session['user'] = {
                'id': res.user.id,
                'email': res.user.email,
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            return jsonify({
                'success': True,
                'user': session['user'],
                'chats': get_user_chats(res.user.id)
            })
        return jsonify({'error': 'Authentication failed'}), 401
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/logout', methods=['POST', 'GET'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400
    
    try:
        filename = secure_filename(file.filename)
        file_id = str(uuid.uuid4())
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{file_id}_{filename}")
        
        # Save file temporarily
        file.save(filepath)
        
        # Extract text in background thread
        def process_pdf():
            try:
                text = extract_pdf_text(filepath)
                if text:
                    # Store in Supabase storage
                    supabase.storage.from_("pdfs").upload(
                        f"{file_id}/{filename}", 
                        open(filepath, 'rb').read(),
                        {"content-type": "application/pdf"}
                    )
                    
                    # Save metadata in database
                    supabase.table('pdf_documents').insert({
                        'user_id': session['user']['id'],
                        'file_id': file_id,
                        'filename': filename,
                        'text_content': text[:10000],  # Store first 10k chars
                        'uploaded_at': datetime.now(timezone.utc).isoformat()
                    }).execute()
                    
                    # Cache in session
                    session.setdefault('pdf_context', {})[file_id] = {
                        'filename': filename,
                        'text': text,
                        'uploaded_at': datetime.now(timezone.utc).isoformat()
                    }
                    session.setdefault('pdf_files', {})[file_id] = {
                        'file_id': file_id,
                        'filename': filename,
                        'text': text,
                        'uploaded_at': datetime.now(timezone.utc).isoformat()
                    }
                    session.modified = True

                    # After storing pdf_files[file_id]...
                    # Optionally associate with latest chat if exists
                    if 'current_chat_id' in session:
                        pdf_context = session.setdefault('pdf_context', {})
                        chat_pdfs = pdf_context.setdefault(session['current_chat_id'], [])
                        if file_id not in chat_pdfs:
                            chat_pdfs.append(file_id)
                        session.modified = True
            finally:
                # Always remove temp file
                try:
                    os.remove(filepath)
                except:
                    pass
        
        executor.submit(process_pdf)
        
        return jsonify({
            'success': True,
            'file_id': file_id,
            'filename': filename
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/chats')
@login_required
def get_chats():
    try:
        chats = get_user_chats(session['user']['id'])
        return jsonify({'success': True, 'chats': chats})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/chat/history')
@login_required
def chat_history():
    chat_id = request.args.get('chat_id')
    if not chat_id:
        return jsonify({'error': 'chat_id parameter required'}), 400
    
    try:
        messages = get_chat_history(session['user']['id'], chat_id)
        return jsonify({
            'success': True,
            'messages': [{
                'id': msg.get('id'),
                'role': msg.get('role'),
                'content': msg.get('message'),
                'created_at': msg.get('created_at')
            } for msg in messages]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/chat', methods=['POST', 'GET'])
@login_required
def chat():
    if request.method == 'POST':
        data = request.get_json()
        message = data.get('message', '').strip()
        chat_id = data.get('chat_id') or str(uuid.uuid4())
    else:
        message = request.args.get('message', '').strip()
        chat_id = request.args.get('chat_id') or str(uuid.uuid4())

    if not message:
        return jsonify({'error': 'Message cannot be empty'}), 400

    save_message_async(session['user']['id'], message, 'user', chat_id)

    # Prepare context from associated PDFs
    context_parts = []
    pdf_files = session.get('pdf_files', {})
    pdf_context = session.get('pdf_context', {})
    file_ids = pdf_context.get(chat_id, [])
    for file_id in file_ids:
        doc = pdf_files.get(file_id)
        if doc:
            context_parts.append(f"=== {doc['filename']} ===\n{doc['text'][:5000]}\n")
    context = "\n".join(context_parts) if context_parts else None

    def generate_response():
        messages = []
        if context:
            messages.append({"role": "system", "content": f"Document context:\n{context}"})
        messages.append({"role": "user", "content": message})

        try:
            with requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": request.host_url,
                    "X-Title": "AI Chat Assistant"
                },
                json={
                    "model": "deepseek/deepseek-r1-0528-qwen3-8b:free",
                    "messages": messages,
                    "stream": True
                },
                stream=True
            ) as response:
                response.raise_for_status()
                full_response = []
                for line in response.iter_lines():
                    if line:
                        decoded = line.decode('utf-8').lstrip('data: ').strip()
                        if decoded == '[DONE]':
                            break
                        try:
                            data = json.loads(decoded)
                            if data.get('choices'):
                                chunk = data['choices'][0]['delta'].get('content', '')
                                if chunk:
                                    full_response.append(chunk)
                                    yield f"data: {json.dumps({'content': chunk, 'chat_id': chat_id})}\n\n"
                        except json.JSONDecodeError:
                            continue
                # Save complete response (async)
                if full_response:
                    complete_response = ''.join(full_response)
                    save_message_async(
                        session['user']['id'],
                        complete_response,
                        'assistant',
                        chat_id
                    )
                    yield f"data: {json.dumps({'done': True, 'chat_id': chat_id})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(generate_response()), mimetype='text/event-stream')

@app.route('/new-chat', methods=['POST'])
@login_required
def new_chat():
    chat_id = str(uuid.uuid4())
    # Insert a placeholder message so the chat appears in history
    supabase.table('chat_history').insert({
        'user_id': session['user']['id'],
        'message': 'New chat started',
        'role': 'system',
        'chat_id': chat_id,
        'created_at': datetime.now(timezone.utc).isoformat()
    }).execute()
    return jsonify({'success': True, 'chat_id': chat_id})

@app.route('/attach-pdf', methods=['POST'])
@login_required
def attach_pdf():
    data = request.get_json()
    chat_id = data.get('chat_id')
    file_id = data.get('file_id')
    if not chat_id or not file_id:
        return jsonify({'error': 'chat_id and file_id required'}), 400

    pdf_context = session.setdefault('pdf_context', {})
    chat_pdfs = pdf_context.setdefault(chat_id, [])
    if file_id not in chat_pdfs:
        chat_pdfs.append(file_id)
    session.modified = True
    return jsonify({'success': True})

@app.route('/delete-chat', methods=['POST'])
@login_required
def delete_chat():
    data = request.get_json()
    chat_id = data.get('chat_id')
    if not chat_id:
        return jsonify({'error': 'chat_id required'}), 400
    try:
        supabase.table('chat_history').delete().eq('user_id', session['user']['id']).eq('chat_id', chat_id).execute()
        # Remove from session context if present
        pdf_context = session.get('pdf_context', {})
        if chat_id in pdf_context:
            del pdf_context[chat_id]
            session.modified = True
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# if __name__ == '__main__':
#     os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
#     app.run(debug=True, threaded=True)
#     waitress-serve --port=8000
