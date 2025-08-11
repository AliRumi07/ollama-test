from flask import Flask, render_template_string, request, jsonify
import requests
import json
import os

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
    </style>
</head>
<body>
    <h1>Gemma Chatbot</h1>
    <div class="chat-container">
        <div class="chat-messages" id="chat-messages"></div>
        <div class="input-container">
            <input type="text" id="user-input" placeholder="Type your message here..." autofocus>
            <button id="send-button" onclick="sendMessage()">Send</button>
        </div>
    </div>

    <script>
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
            if (event.key === 'Enter' && !document.getElementById('send-button').disabled) {
                sendMessage();
            }
        });
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

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
        return jsonify({'response': 'Error: Could not connect to Ollama. Make sure Ollama is running and the model is pulled.'}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error: {str(e)}")
        return jsonify({'response': 'An unexpected error occurred. Please try again.'}), 500

@app.route('/health')
def health():
    """Health check endpoint for Render"""
    return jsonify({'status': 'healthy'}), 200

if __name__ == '__main__':
    # Get port from environment variable (Render sets this)
    port = int(os.environ.get('PORT', 8080))
    
    # Run the Flask app
    app.run(host='0.0.0.0', port=port, debug=False)
