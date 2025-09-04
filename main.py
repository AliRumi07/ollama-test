from flask import Flask, render_template_string, request, jsonify, session
import requests
import json
import os
import subprocess
import time
import threading
import secrets
from pathlib import Path          # NEW: for system-prompt file

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # For session management

# ─── Configuration ─────────────────────────────────────────────────────────────────────
MODEL_NAME = "llama3.1:8b"  # Change this to use a different model

# Path of the file that holds the system prompt
SYSTEM_PROMPT_FILE = Path("system_prompt.txt")

# Load the system prompt once at start-up
try:
    SYSTEM_PROMPT = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8").strip()
except FileNotFoundError:
    SYSTEM_PROMPT = ""
    app.logger.warning(
        f"[WARNING] {SYSTEM_PROMPT_FILE} not found. Proceeding with empty system prompt."
    )

# Ollama API endpoint
OLLAMA_API_URL = "http://localhost:11434/api/generate"

# ─── HTML template (unchanged) ─────────────────────────────────────────────────────────
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>EMAM AI</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body {
            font-family: Arial, sans-serif; background-color:#f5f5f5;
            height:100vh; display:flex; flex-direction:column;
        }
        .header { background-color:#333; color:white; padding:15px;
                  text-align:center; position:relative; }
        .header h1 { font-size:24px; font-weight:normal; }
        .clear-button { position:absolute; right:15px; top:50%;
                        transform:translateY(-50%); padding:5px 15px;
                        background-color:#555; color:white; border:none;
                        border-radius:4px; cursor:pointer; font-size:14px; }
        .clear-button:hover { background-color:#777; }
        #status { background-color:#e0e0e0; padding:10px; text-align:center; font-size:14px; }
        .model-info { font-size:12px; color:#666; }
        .chat-container { flex:1; display:flex; flex-direction:column;
                          max-width:800px; width:100%; margin:0 auto;
                          background-color:white; }
        .messages { flex:1; overflow-y:auto; padding:20px; }
        .message { margin-bottom:15px; padding:10px 15px; border-radius:8px; max-width:70%; }
        .user-message { background-color:#e3f2fd; margin-left:auto; text-align:right; }
        .bot-message { background-color:#f5f5f5; border:1px solid #ddd; }
        .input-area { border-top:1px solid #ddd; padding:15px; display:flex; gap:10px; }
        #user-input { flex:1; padding:10px; border:1px solid #ddd; border-radius:4px; font-size:16px; }
        #send-button { padding:10px 20px; background-color:#333; color:white;
                       border:none; border-radius:4px; cursor:pointer; font-size:16px; }
        #send-button:hover:not(:disabled) { background-color:#555; }
        #send-button:disabled { background-color:#999; cursor:not-allowed; }
        .loading { text-align:center; color:#666; padding:10px; }
        .context-indicator { font-size:12px; color:#666; padding:5px 10px;
                             text-align:center; font-style:italic; }
    </style>
</head>
<body>
    <div class="header">
        <h1>EMAM AI</h1>
        <button class="clear-button" onclick="clearHistory()">Clear History</button>
    </div>
    
    <div id="status">
        <div>Initializing...</div>
        <div class="model-info">Model: ''' + MODEL_NAME + '''</div>
    </div>
    
    <div class="chat-container">
        <div class="messages" id="messages"></div>
        <div id="context-indicator" class="context-indicator" style="display: none;">
            Conversation context is being maintained
        </div>
        <div class="input-area">
            <input type="text" id="user-input" placeholder="Type your message..." disabled>
            <button id="send-button" onclick="sendMessage()" disabled>Send</button>
        </div>
    </div>

    <script>
        let ollamaReady = false;

        function updateStatus(message) {
            const statusDiv = document.getElementById('status');
            const statusText = statusDiv.querySelector('div:first-child');
            statusText.textContent = message;
            if (message === 'Ready') {
                statusDiv.style.backgroundColor = '#c8e6c9';
                document.getElementById('user-input').disabled = false;
                document.getElementById('send-button').disabled = false;
                ollamaReady = true;
                checkContextIndicator();
            }
        }

        function checkOllamaStatus() {
            fetch('/ollama-status')
                .then(r => r.json())
                .then(data => {
                    if (data.status === 'ready') updateStatus('Ready');
                    else if (data.status === 'loading') {
                        updateStatus(data.message); setTimeout(checkOllamaStatus, 2000);
                    } else {
                        updateStatus('Error: ' + data.message); setTimeout(checkOllamaStatus, 5000);
                    }
                })
                .catch(() => { updateStatus('Connection error'); setTimeout(checkOllamaStatus, 5000); });
        }

        function addMessage(msg, isUser) {
            const box = document.getElementById('messages');
            const div = document.createElement('div');
            div.className = 'message ' + (isUser ? 'user-message' : 'bot-message');
            div.textContent = msg;
            box.appendChild(div);
            box.scrollTop = box.scrollHeight;
        }

        function showLoading() {
            const box = document.getElementById('messages');
            const div = document.createElement('div');
            div.className = 'loading'; div.id = 'loading'; div.textContent = '...';
            box.appendChild(div); box.scrollTop = box.scrollHeight;
        }

        function hideLoading() {
            const div = document.getElementById('loading'); if (div) div.remove();
        }

        function checkContextIndicator() {
            fetch('/has-context')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('context-indicator').style.display =
                        data.has_context ? 'block' : 'none';
                });
        }

        async function sendMessage() {
            if (!ollamaReady) return;
            const input = document.getElementById('user-input');
            const btn = document.getElementById('send-button');
            const msg = input.value.trim();
            if (!msg) return;
            addMessage(msg, true); input.value = ''; btn.disabled = true; showLoading();
            try {
                const r = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: msg }),
                });
                const data = await r.json();
                hideLoading(); addMessage(data.response, false); checkContextIndicator();
            } catch {
                hideLoading(); addMessage('Error: Unable to get response.', false);
            } finally {
                btn.disabled = false; input.focus();
            }
        }

        function clearHistory() {
            if (!confirm('Are you sure you want to clear the conversation history?')) return;
            fetch('/clear-history', { method: 'POST' })
                .then(() => { document.getElementById('messages').innerHTML = ''; checkContextIndicator(); });
        }

        document.getElementById('user-input').addEventListener('keypress', e => {
            if (e.key === 'Enter' && !document.getElementById('send-button').disabled) sendMessage();
        });
        window.onload = () => checkOllamaStatus();
    </script>
</body>
</html>
'''

# ─── Ollama start-up helper ────────────────────────────────────────────────────────────
ollama_status = {'status': 'loading', 'message': 'Starting Ollama...'}

def start_ollama():
    global ollama_status
    try:
        app.logger.info("Starting Ollama service...")
        subprocess.Popen(['ollama', 'serve'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(5)

        ollama_status['message'] = f'Checking for {MODEL_NAME} model...'
        result = subprocess.run(['ollama', 'list'], capture_output=True, text=True)
        if MODEL_NAME not in result.stdout:
            ollama_status['message'] = f'Downloading {MODEL_NAME} model (this may take a few minutes)...'
            app.logger.info(f"Pulling {MODEL_NAME} model...")
            subprocess.run(['ollama', 'pull', MODEL_NAME], check=True)

        ollama_status['message'] = 'Testing Ollama connection...'
        for _ in range(10):
            try:
                r = requests.get('http://localhost:11434/api/tags')
                if r.status_code == 200:
                    ollama_status.update(status='ready', message='Ollama is ready!')
                    app.logger.info("Ollama is ready!")
                    return
            except: time.sleep(2)

        ollama_status.update(status='error', message='Ollama started but not responding')
    except Exception as e:
        app.logger.error(f"Error starting Ollama: {e}")
        ollama_status.update(status='error', message=f'Error starting Ollama: {e}')

# ─── Flask routes ──────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    if 'conversation_history' not in session:
        session['conversation_history'] = []
    return render_template_string(HTML_TEMPLATE)

@app.route('/ollama-status')
def get_ollama_status():
    return jsonify(ollama_status)

@app.route('/has-context')
def has_context():
    return jsonify({'has_context': len(session.get('conversation_history', [])) > 0})

@app.route('/clear-history', methods=['POST'])
def clear_history():
    session['conversation_history'] = []
    return jsonify({'status': 'cleared'})

@app.route('/chat', methods=['POST'])
def chat():
    try:
        user_message = request.json.get('message', '')
        history = session.get('conversation_history', [])

        # ── Build the prompt ──
        prompt_parts = []
        if SYSTEM_PROMPT:
            prompt_parts.append(SYSTEM_PROMPT)
            prompt_parts.append("")          # blank line for readability

        if history:
            recent = history[-6:]            # last 3 exchanges (6 msgs)
            for msg in recent:
                prompt_parts.append(f"{msg['role']}: {msg['content']}")
        prompt_parts.append(f"User: {user_message}")
        prompt_parts.append("Assistant:")
        full_prompt = "\n".join(prompt_parts)

        # Call Ollama
        payload = {
            "model": MODEL_NAME,
            "prompt": full_prompt,
            "stream": False,
            "options": {"temperature": 0.7, "top_p": 0.9, "top_k": 40}
        }
        r = requests.post(OLLAMA_API_URL, json=payload, timeout=30)
        r.raise_for_status()
        bot_response = r.json().get('response', '').strip()
        if bot_response.lower().startswith("assistant:"):
            bot_response = bot_response.split(":", 1)[1].strip()

        # Update session history
        history.extend([{'role': 'User', 'content': user_message},
                        {'role': 'Assistant', 'content': bot_response}])
        if len(history) > 20: history[:] = history[-20:]
        session['conversation_history'] = history
        session.modified = True

        return jsonify({'response': bot_response})
    except requests.exceptions.Timeout:
        app.logger.error("Ollama request timed out")
        return jsonify({'response': 'The request timed out. Please try again.'}), 500
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Ollama API error: {e}")
        return jsonify({'response': 'Error: Could not connect to Ollama. Please refresh the page and wait for Ollama to initialize.'}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error: {e}")
        return jsonify({'response': 'An unexpected error occurred. Please try again.'}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200

# ─── Main ──────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    threading.Thread(target=start_ollama, daemon=True).start()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
