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
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "default_api_key")
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
                try:
                    page_text = page.extract_text()
                    if page_text:
                        # Clean and encode the text properly
                        cleaned_text = page_text.encode('ascii', 'ignore').decode('ascii')
                        text.append(cleaned_text)
                except Exception as e:
                    print(f"Error extracting page: {str(e)}")
                    continue
            return "\n".join(text) if text else None
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
    """Get chat history with proper ordering"""
    try:
        query = supabase.table('chat_history') \
            .select('*') \
            .eq('user_id', user_id)
        
        if chat_id:
            query = query.eq('chat_id', chat_id)
        
        # Order by created_at ascending to maintain conversation flow
        messages = query.order('created_at', desc=False) \
            .limit(limit) \
            .execute() \
            .data

        return messages
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
    chat_id = request.form.get('chat_id') or str(uuid.uuid4())
    
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
        
        # Extract text with error handling
        text = extract_pdf_text(filepath)
        if not text:
            return jsonify({'error': 'Could not extract text from PDF'}), 400
            
        # Store in database
        supabase.table('pdf_documents').insert({
            'user_id': session['user']['id'],
            'file_id': file_id,
            'chat_id': chat_id,
            'filename': filename,
            'text_content': text,
            'uploaded_at': datetime.now(timezone.utc).isoformat()
        }).execute()
        
        # Add system message about PDF
        save_message_async(
            session['user']['id'],
            f"📄 PDF uploaded: {filename}",
            'system',
            chat_id
        )
            
        return jsonify({
            'success': True,
            'file_id': file_id,
            'filename': filename,
            'chat_id': chat_id
        })
            
    except Exception as e:
        print(f"Upload error: {str(e)}")
        return jsonify({'error': 'Error processing PDF'}), 500
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)

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

    # Save user message
    save_message_async(session['user']['id'], message, 'user', chat_id)

    # Get PDF context for this chat
    context = ""
    try:
        # Query the database for PDFs associated with this chat
        pdf_docs = supabase.table('pdf_documents') \
            .select('*') \
            .eq('user_id', session['user']['id']) \
            .eq('chat_id', chat_id) \
            .execute()
        
        if pdf_docs.data:
            context = "Here is the content from the uploaded documents:\n\n"
            for doc in pdf_docs.data:
                context += f"=== Content from {doc['filename']} ===\n"
                context += f"{doc['text_content']}\n\n"
            context += "\nPlease analyze the above content and answer the following question:\n"
    except Exception as e:
        print(f"Error fetching PDF context: {str(e)}")

    def generate_response():
        messages = [
            {
                "role": "system",
                "content": "You are Najib & Nabirah AI, a helpful assistant. Always maintain a professional yet warm tone."
            }
        ]
        
        # Get previous messages for context (last 10 messages)
        try:
            previous_messages = get_chat_history(session['user']['id'], chat_id, limit=10)
            for msg in previous_messages:
                messages.append({
                    "role": msg['role'],
                    "content": msg['message']
                })
        except Exception as e:
            print(f"Error fetching chat history: {str(e)}")
        
        # Add PDF context if available
        if context:
            messages.append({
                "role": "system",
                "content": context
            })

        # Add the current user message
        messages.append({
            "role": "user",
            "content": message
        })

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
                    "stream": True,
                    "temperature": 0.7  # Add temperature for better context handling
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