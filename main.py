from flask import Flask, render_template_string, request, jsonify, session
import requests
import json
import os
import subprocess
import time
import threading
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # For session management

# Configuration - Change model name here
MODEL_NAME = "llama3.1:8b"  # Change this to use a different model

# Ollama API endpoint
OLLAMA_API_URL = "http://localhost:11434/api/generate"

# HTML template for the chat interface
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>EMAM AI</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: Arial, sans-serif;
            background-color: #f5f5f5;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        
        .header {
            background-color: #333;
            color: white;
            padding: 15px;
            text-align: center;
            position: relative;
        }
        
        .header h1 {
            font-size: 24px;
            font-weight: normal;
        }
        
        .clear-button {
            position: absolute;
            right: 15px;
            top: 50%;
            transform: translateY(-50%);
            padding: 5px 15px;
            background-color: #555;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }
        
        .clear-button:hover {
            background-color: #777;
        }
        
        #status {
            background-color: #e0e0e0;
            padding: 10px;
            text-align: center;
            font-size: 14px;
        }
        
        .model-info {
            font-size: 12px;
            color: #666;
        }
        
        .chat-container {
            flex: 1;
            display: flex;
            flex-direction: column;
            max-width: 800px;
            width: 100%;
            margin: 0 auto;
            background-color: white;
        }
        
        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
        }
        
        .message {
            margin-bottom: 15px;
            padding: 10px 15px;
            border-radius: 8px;
            max-width: 70%;
        }
        
        .user-message {
            background-color: #e3f2fd;
            margin-left: auto;
            text-align: right;
        }
        
        .bot-message {
            background-color: #f5f5f5;
            border: 1px solid #ddd;
        }
        
        .input-area {
            border-top: 1px solid #ddd;
            padding: 15px;
            display: flex;
            gap: 10px;
        }
        
        #user-input {
            flex: 1;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 16px;
        }
        
        #send-button {
            padding: 10px 20px;
            background-color: #333;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
        }
        
        #send-button:hover:not(:disabled) {
            background-color: #555;
        }
        
        #send-button:disabled {
            background-color: #999;
            cursor: not-allowed;
        }
        
        .loading {
            text-align: center;
            color: #666;
            padding: 10px;
        }
        
        .context-indicator {
            font-size: 12px;
            color: #666;
            padding: 5px 10px;
            text-align: center;
            font-style: italic;
        }
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
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'ready') {
                        updateStatus('Ready');
                    } else if (data.status === 'loading') {
                        updateStatus(data.message);
                        setTimeout(checkOllamaStatus, 2000);
                    } else {
                        updateStatus('Error: ' + data.message);
                        setTimeout(checkOllamaStatus, 5000);
                    }
                })
                .catch(error => {
                    updateStatus('Connection error');
                    setTimeout(checkOllamaStatus, 5000);
                });
        }

        function addMessage(message, isUser) {
            const messagesDiv = document.getElementById('messages');
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message ' + (isUser ? 'user-message' : 'bot-message');
            messageDiv.textContent = message;
            messagesDiv.appendChild(messageDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        function showLoading() {
            const messagesDiv = document.getElementById('messages');
            const loadingDiv = document.createElement('div');
            loadingDiv.className = 'loading';
            loadingDiv.id = 'loading';
            loadingDiv.textContent = '...';
            messagesDiv.appendChild(loadingDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        function hideLoading() {
            const loadingDiv = document.getElementById('loading');
            if (loadingDiv) {
                loadingDiv.remove();
            }
        }

        function checkContextIndicator() {
            fetch('/has-context')
                .then(response => response.json())
                .then(data => {
                    const indicator = document.getElementById('context-indicator');
                    if (data.has_context) {
                        indicator.style.display = 'block';
                    } else {
                        indicator.style.display = 'none';
                    }
                });
        }

        async function sendMessage() {
            if (!ollamaReady) return;

            const userInput = document.getElementById('user-input');
            const sendButton = document.getElementById('send-button');
            const message = userInput.value.trim();
            
            if (!message) return;
            
            addMessage(message, true);
            userInput.value = '';
            sendButton.disabled = true;
            showLoading();
            
            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ message: message }),
                });
                
                const data = await response.json();
                hideLoading();
                addMessage(data.response, false);
                checkContextIndicator();
                
            } catch (error) {
                hideLoading();
                addMessage('Error: Unable to get response.', false);
            } finally {
                sendButton.disabled = false;
                userInput.focus();
            }
        }

        function clearHistory() {
            if (confirm('Are you sure you want to clear the conversation history?')) {
                fetch('/clear-history', { method: 'POST' })
                    .then(() => {
                        document.getElementById('messages').innerHTML = '';
                        checkContextIndicator();
                    });
            }
        }

        document.getElementById('user-input').addEventListener('keypress', function(event) {
            if (event.key === 'Enter' && !document.getElementById('send-button').disabled) {
                sendMessage();
            }
        });

        window.onload = function() {
            checkOllamaStatus();
        };
    </script>
</body>
</html>
'''

# Global variable to track Ollama status
ollama_status = {
    'status': 'loading',
    'message': 'Starting Ollama...'
}

def start_ollama():
    """Start Ollama service in the background"""
    global ollama_status
    
    try:
        # Start Ollama serve
        app.logger.info("Starting Ollama service...")
        subprocess.Popen(['ollama', 'serve'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Wait for Ollama to start
        time.sleep(5)
        
        # Check if model exists, if not pull it
        ollama_status['message'] = f'Checking for {MODEL_NAME} model...'
        result = subprocess.run(['ollama', 'list'], capture_output=True, text=True)
        
        if MODEL_NAME not in result.stdout:
            ollama_status['message'] = f'Downloading {MODEL_NAME} model (this may take a few minutes)...'
            app.logger.info(f"Pulling {MODEL_NAME} model...")
            subprocess.run(['ollama', 'pull', MODEL_NAME], check=True)
        
        # Test if Ollama is responsive
        ollama_status['message'] = 'Testing Ollama connection...'
        for i in range(10):
            try:
                response = requests.get('http://localhost:11434/api/tags')
                if response.status_code == 200:
                    ollama_status['status'] = 'ready'
                    ollama_status['message'] = 'Ollama is ready!'
                    app.logger.info("Ollama is ready!")
                    return
            except:
                time.sleep(2)
        
        ollama_status['status'] = 'error'
        ollama_status['message'] = 'Ollama started but not responding'
        
    except Exception as e:
        app.logger.error(f"Error starting Ollama: {str(e)}")
        ollama_status['status'] = 'error'
        ollama_status['message'] = f'Error starting Ollama: {str(e)}'

@app.route('/')
def index():
    # Initialize session conversation history
    if 'conversation_history' not in session:
        session['conversation_history'] = []
    return render_template_string(HTML_TEMPLATE)

@app.route('/ollama-status')
def get_ollama_status():
    return jsonify(ollama_status)

@app.route('/has-context')
def has_context():
    """Check if there's conversation history"""
    has_history = len(session.get('conversation_history', [])) > 0
    return jsonify({'has_context': has_history})

@app.route('/clear-history', methods=['POST'])
def clear_history():
    """Clear conversation history"""
    session['conversation_history'] = []
    return jsonify({'status': 'cleared'})

@app.route('/chat', methods=['POST'])
def chat():
    try:
        user_message = request.json.get('message', '')
        
        # Get conversation history from session
        conversation_history = session.get('conversation_history', [])
        
        # Build conversation context
        full_prompt = ""
        if conversation_history:
            # Include last 3 exchanges (6 messages) for context
            recent_history = conversation_history[-6:]
            for msg in recent_history:
                full_prompt += f"{msg['role']}: {msg['content']}\n"
            full_prompt += f"User: {user_message}\nAssistant:"
        else:
            full_prompt = user_message
        
        # Prepare the request to Ollama
        ollama_payload = {
            "model": MODEL_NAME,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "top_k": 40
            }
        }
        
        # Make request to Ollama
        response = requests.post(OLLAMA_API_URL, json=ollama_payload, timeout=30)
        response.raise_for_status()
        
        # Extract the response text
        ollama_response = response.json()
        bot_response = ollama_response.get('response', 'Sorry, I could not generate a response.')
        
        # Clean up the response (remove any "Assistant:" prefix if present)
        bot_response = bot_response.strip()
        if bot_response.startswith("Assistant:"):
            bot_response = bot_response[10:].strip()
        
        # Update conversation history
        conversation_history.append({'role': 'User', 'content': user_message})
        conversation_history.append({'role': 'Assistant', 'content': bot_response})
        
        # Keep only last 10 exchanges (20 messages) to prevent context from growing too large
        if len(conversation_history) > 20:
            conversation_history = conversation_history[-20:]
        
        # Save updated history to session
        session['conversation_history'] = conversation_history
        session.modified = True
        
        return jsonify({'response': bot_response})
        
    except requests.exceptions.Timeout:
        app.logger.error("Ollama request timed out")
        return jsonify({'response': 'The request timed out. Please try again.'}), 500
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Ollama API error: {str(e)}")
        return jsonify({'response': 'Error: Could not connect to Ollama. Please refresh the page and wait for Ollama to initialize.'}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error: {str(e)}")
        return jsonify({'response': 'An unexpected error occurred. Please try again.'}), 500

@app.route('/health')
def health():
    """Health check endpoint for Render"""
    return jsonify({'status': 'healthy'}), 200

if __name__ == '__main__':
    # Start Ollama in a separate thread
    ollama_thread = threading.Thread(target=start_ollama)
    ollama_thread.daemon = True
    ollama_thread.start()
    
    # Get port from environment variable (Render sets this)
    port = int(os.environ.get('PORT', 8080))
    
    # Run the Flask app
    app.run(host='0.0.0.0', port=port, debug=False)
