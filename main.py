"""
Flask chat front-end for an Ollama model.
System prompt is now hard-coded in the variable SYSTEM_PROMPT.
"""

# ─── Imports ──────────────────────────────────────────────────────────
from flask import Flask, render_template_string, request, jsonify, session
import requests
import os
import subprocess
import time
import threading
import secrets

# ─── App object & session secret ──────────────────────────────────────
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)        # for session management

# ─── Configuration ────────────────────────────────────────────────────
MODEL_NAME = "llama3.1:8b"                # change if you use another model
OLLAMA_API_URL = "http://localhost:11434/api/generate"

# Hard-coded system prompt (edit freely)
SYSTEM_PROMPT = """
You are EMAM AI, an expert assistant.
• Answer in the same language the user used, unless instructed otherwise.
• Keep replies concise and cite evidence where appropriate.
""".strip()

# ─── HTML template (UI) ───────────────────────────────────────────────
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>EMAM AI</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:Arial,Helvetica,sans-serif;background:#f5f5f5;height:100vh;display:flex;flex-direction:column}
        .header{background:#333;color:#fff;padding:15px;text-align:center;position:relative}
        .header h1{font-size:24px;font-weight:normal}
        .clear-button{position:absolute;right:15px;top:50%;transform:translateY(-50%);padding:5px 15px;background:#555;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:14px}
        .clear-button:hover{background:#777}
        #status{background:#e0e0e0;padding:10px;text-align:center;font-size:14px}
        .model-info{font-size:12px;color:#666}
        .chat-container{flex:1;display:flex;flex-direction:column;max-width:800px;width:100%;margin:0 auto;background:#fff}
        .messages{flex:1;overflow-y:auto;padding:20px}
        .message{margin-bottom:15px;padding:10px 15px;border-radius:8px;max-width:70%}
        .user-message{background:#e3f2fd;margin-left:auto;text-align:right}
        .bot-message{background:#f5f5f5;border:1px solid #ddd}
        .input-area{border-top:1px solid #ddd;padding:15px;display:flex;gap:10px}
        #user-input{flex:1;padding:10px;border:1px solid #ddd;border-radius:4px;font-size:16px}
        #send-button{padding:10px 20px;background:#333;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:16px}
        #send-button:hover:not(:disabled){background:#555}
        #send-button:disabled{background:#999;cursor:not-allowed}
        .loading{text-align:center;color:#666;padding:10px}
        .context-indicator{font-size:12px;color:#666;padding:5px 10px;text-align:center;font-style:italic}
    </style>
</head>
<body>
    <div class="header">
        <h1>EMAM AI</h1>
        <button class="clear-button" onclick="clearHistory()">Clear History</button>
    </div>
    <div id="status">
        <div>Initializing...</div>
        <div class="model-info">Model: {{ model }}</div>
    </div>
    <div class="chat-container">
        <div class="messages" id="messages"></div>
        <div id="context-indicator" class="context-indicator" style="display:none">
            Conversation context is being maintained
        </div>
        <div class="input-area">
            <input type="text" id="user-input" placeholder="Type your message..." disabled>
            <button id="send-button" onclick="sendMessage()" disabled>Send</button>
        </div>
    </div>

    <script>
        let ready = false;
        function updateStatus(msg){
            const s=document.getElementById('status');
            s.children[0].textContent=msg;
            if(msg==='Ready'){
                s.style.background='#c8e6c9';
                document.getElementById('user-input').disabled=false;
                document.getElementById('send-button').disabled=false;
                ready=true; checkIndicator();
            }
        }
        function poll(){
            fetch('/ollama-status').then(r=>r.json()).then(d=>{
                if(d.status==='ready') updateStatus('Ready');
                else if(d.status==='loading'){updateStatus(d.message);setTimeout(poll,2000)}
                else {updateStatus('Error: '+d.message);setTimeout(poll,5000)}
            }).catch(()=>{updateStatus('Connection error');setTimeout(poll,5000)});
        }
        function addMessage(txt,user){
            const div=document.createElement('div');
            div.className='message '+(user?'user-message':'bot-message');
            div.textContent=txt;
            const box=document.getElementById('messages');
            box.appendChild(div); box.scrollTop=box.scrollHeight;
        }
        function loader(on){
            if(on){
                const l=document.createElement('div');l.id='loading';l.className='loading';l.textContent='...';
                document.getElementById('messages').appendChild(l);
            }else{
                const l=document.getElementById('loading');if(l)l.remove();
            }
        }
        function checkIndicator(){
            fetch('/has-context').then(r=>r.json()).then(d=>{
                document.getElementById('context-indicator').style.display=d.has_context?'block':'none';
            });
        }
        async function sendMessage(){
            if(!ready) return;
            const inp=document.getElementById('user-input');
            const txt=inp.value.trim(); if(!txt)return;
            addMessage(txt,true); inp.value=''; document.getElementById('send-button').disabled=true; loader(true);
            try{
                const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:txt})});
                const j=await r.json(); loader(false); addMessage(j.response,false); checkIndicator();
            }catch{loader(false);addMessage('Error getting response',false)}
            finally{document.getElementById('send-button').disabled=false;inp.focus();}
        }
        function clearHistory(){
            if(!confirm('Clear conversation history?'))return;
            fetch('/clear-history',{method:'POST'}).then(()=>{document.getElementById('messages').innerHTML='';checkIndicator();});
        }
        document.getElementById('user-input').addEventListener('keypress',e=>{
            if(e.key==='Enter'&&!document.getElementById('send-button').disabled)sendMessage();
        });
        window.onload=poll;
    </script>
</body>
</html>
'''

# ─── Ollama start-up helper ───────────────────────────────────────────
ollama_status = {'status': 'loading', 'message': 'Starting Ollama...'}

def start_ollama():
    global ollama_status
    try:
        app.logger.info("Starting Ollama service …")
        subprocess.Popen(['ollama', 'serve'],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        time.sleep(5)
        ollama_status['message'] = f'Checking for {MODEL_NAME} model…'
        result = subprocess.run(['ollama', 'list'], capture_output=True, text=True)
        if MODEL_NAME not in result.stdout:
            ollama_status['message'] = f'Downloading {MODEL_NAME} (may take a few minutes)…'
            subprocess.run(['ollama', 'pull', MODEL_NAME], check=True)
        ollama_status['message'] = 'Testing connection…'
        for _ in range(10):
            try:
                if requests.get('http://localhost:11434/api/tags').status_code == 200:
                    ollama_status.update(status='ready', message='Ollama is ready!')
                    return
            except: time.sleep(2)
        ollama_status.update(status='error', message='Ollama started but not responding')
    except Exception as e:
        ollama_status.update(status='error', message=f'Error starting Ollama: {e}')

# ─── Flask routes ────────────────────────────────────────────────────
@app.route('/')
def index():
    session.setdefault('conversation_history', [])
    return render_template_string(HTML_TEMPLATE, model=MODEL_NAME)

@app.route('/ollama-status')
def get_status():
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
        user_msg = request.json.get('message', '')
        hist = session.get('conversation_history', [])

        # build prompt
        parts = [SYSTEM_PROMPT, ""] if SYSTEM_PROMPT else []
        if hist:
            for m in hist[-6:]:                     # last 3 exchanges (6 msgs)
                parts.append(f"{m['role']}: {m['content']}")
        parts.append(f"User: {user_msg}")
        parts.append("Assistant:")
        prompt = "\n".join(parts)

        payload = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.7, "top_p": 0.9, "top_k": 40}
        }
        r = requests.post(OLLAMA_API_URL, json=payload, timeout=30)
        r.raise_for_status()
        bot = r.json().get('response', '').strip()
        if bot.lower().startswith("assistant:"):
            bot = bot.split(":", 1)[1].strip()

        # update history
        hist.extend([{'role': 'User', 'content': user_msg},
                     {'role': 'Assistant', 'content': bot}])
        if len(hist) > 20: hist[:] = hist[-20:]
        session['conversation_history'] = hist; session.modified = True
        return jsonify({'response': bot})
    except requests.exceptions.Timeout:
        return jsonify({'response': 'The request to the model timed out. Try again.'}), 500
    except requests.exceptions.RequestException:
        return jsonify({'response': 'Could not contact Ollama backend.'}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error: {e}")
        return jsonify({'response': 'Unexpected server error.'}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200

# ─── Main ────────────────────────────────────────────────────────────
if __name__ == '__main__':
    threading.Thread(target=start_ollama, daemon=True).start()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
