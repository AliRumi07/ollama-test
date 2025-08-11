from flask import Flask, render_template_string, request, jsonify
import requests
import json
import os
import subprocess
import time
import threading

app = Flask(__name__)

# Ollama API endpoint
OLLAMA_API_URL = "http://localhost:11434/api/generate"

# HTML template for the chat interface
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Gemma Chatbot</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f0f0f0;
        }
        .chat-container {
            background-color: white;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            padding: 20px;
            height: 500px;
            display: flex;
            flex-direction: column;
        }
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 5px;
            margin-bottom: 10px;
        }
        .message {
            margin: 10px 0;
            padding: 10px;
            border-radius: 5px;
        }
        .user-message {
            background-color: #007bff;
            color: white;
            text-align: right;
        }
        .bot-message {
            background-color: #e9ecef;
            color: #333;
        }
        .input-container {
            display: flex;
            gap: 10px;
        }
        #user-input {
            flex: 1;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 16px;
        }
        #send-button {
            padding: 10px 20px;
            background-color: #007bff;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
        }
        #send-button:hover {
            background-color: #0056b3;
        }
        #send-button:disabled {
            background-color: #ccc;
            cursor: not-allowed;
        }
        .loading {
            text-align: center;
            color: #666;
            font-style: italic;
        }
        .status {
            text-align: center;
            padding: 10px;
            margin-bottom: 10px;
            border-radius: 5px;
        }
        .status.ready {
            background-color: #d4edda;
            color: #155724;
        }
        .status.loading {
            background-color: #fff3cd;
            color: #856404;
        }
        .status.error {
            background-color: #f8d7da;
            color: #721c24;
        }
    </style>
</head>
<body>
    <h1>Gemma Chatbot</h1>
    <div id="status" class="status loading">Initializing Ollama...</div>
    <div class="chat-container">
        <div class="chat-messages" id="chat-messages"></div>
        <div class="input-container">
            <input type="text" id="user-input" placeholder="Type your message here..." autofocus disabled>
            <button id="send-button" onclick="sendMessage()" disabled>Send</button>
        </div>
    </div>

    <script>
        let ollamaReady = false;

        function updateStatus(message, type) {
            const statusDiv = document.getElementById('status');
            statusDiv.textContent = message;
            statusDiv.className = 'status ' + type;
            
            if (type === 'ready') {
                document.getElementById('user-input').disabled = false;
                document.getElementById('send-button').disabled = false;
                ollamaReady = true;
            }
        }

        function checkOllamaStatus() {
            fetch('/ollama-status')
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'ready') {
                        updateStatus('Ollama is ready! You can start chatting.', 'ready');
                    } else if (data.status === 'loading') {
                        updateStatus(data.message, 'loading');
                        setTimeout(checkOllamaStatus, 2000);
                    } else {
                        updateStatus(data.message, 'error');
                        setTimeout(checkOllamaStatus, 5000);
                    }
                })
                .catch(error => {
                    updateStatus('Error checking Ollama status', 'error');
                    setTimeout(checkOllamaStatus, 5000);
                });
        }

        function addMessage(message, isUser) {
            const chatMessages = document.getElementById('chat-messages');
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message ' + (isUser ? 'user-message' : 'bot-message');
            messageDiv.textContent = message;
            chatMessages.appendChild(messageDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        function showLoading() {
            const chatMessages = document.getElementById('chat-messages');
            const loadingDiv = document.createElement('div');
            loadingDiv.className = 'loading';
            loadingDiv.id = 'loading';
            loadingDiv.textContent = 'Thinking...';
            chatMessages.appendChild(loadingDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        function hideLoading() {
            const loadingDiv = document.getElementById('loading');
            if (loadingDiv) {
                loadingDiv.remove();
            }
        }

        async function sendMessage() {
            if (!ollamaReady) {
                alert('Ollama is not ready yet. Please wait...');
                return;
            }

            const userInput = document.getElementById('user-input');
            const sendButton = document.getElementById('send-button');
            const message = userInput.value.trim();
            
            if (!message) return;
            
            // Add user message to chat
            addMessage(message, true);
            
            // Clear input and disable button
            userInput.value = '';
            sendButton.disabled = true;
            
            // Show loading indicator
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
                
                // Hide loading and add bot response
                hideLoading();
                addMessage(data.response, false);
                
            } catch (error) {
                hideLoading();
                addMessage('Error: Unable to get response. Please try again.', false);
            } finally {
                sendButton.disabled = false;
                userInput.focus();
            }
        }

        // Allow sending message with Enter key
        document.getElementById('user-input').addEventListener('keypress', function(event) {
            if (event.key === 'Enter' && !document.getElementById('send-button').disabled && ollamaReady) {
                sendMessage();
            }
        });

        // Check Ollama status on page load
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
        ollama_status['message'] = 'Checking for Gemma model...'
        result = subprocess.run(['ollama', 'list'], capture_output=True, text=True)
        
        if 'gemma3:1b-it-qat' not in result.stdout:
            ollama_status['message'] = 'Downloading Gemma model (this may take a few minutes)...'
            app.logger.info("Pulling gemma3:1b-it-qat model...")
            subprocess.run(['ollama', 'pull', 'gemma3:1b-it-qat'], check=True)
        
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
    return render_template_string(HTML_TEMPLATE)

@app.route('/ollama-status')
def get_ollama_status():
    return jsonify(ollama_status)

@app.route('/chat', methods=['POST'])
def chat():
    try:
        user_message = request.json.get('message', '')
        
        # Prepare the request to Ollama
        ollama_payload = {
            "model": "gemma3:1b-it-qat",
            "prompt": user_message,
            "stream": False
        }
        
        # Make request to Ollama
        response = requests.post(OLLAMA_API_URL, json=ollama_payload)
        response.raise_for_status()
        
        # Extract the response text
        ollama_response = response.json()
        bot_response = ollama_response.get('response', 'Sorry, I could not generate a response.')
        
        return jsonify({'response': bot_response})
        
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
