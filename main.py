# main.py
import os
import requests
from flask import Flask, request, jsonify, render_template_string

# -------------------------------------------------------------------
# Basic configuration — change via environment variables if needed
# -------------------------------------------------------------------
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")  # Ollama daemon
MODEL_NAME = os.getenv("LLM_MODEL", "gemma3:1b-it-qat")         # Model to use

app = Flask(__name__)

# -------------------------------------------------------------------
# A very small HTML UI served by Flask
# -------------------------------------------------------------------
HTML_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Gemma 3 Chatbot</title>
  <style>
    body{font-family:sans-serif;background:#f2f2f2;margin:0;padding:2rem;}
    #chat{max-width:800px;margin:auto;}
    .bubble{padding:.6rem 1rem;border-radius:8px;margin:.3rem 0;max-width:90%;}
    .user {background:#d1e7dd;text-align:right;margin-left:10%;}
    .bot  {background:#fff;border:1px solid #ccc;}
    form  {display:flex;gap:.5rem;margin-top:1rem;max-width:800px;margin:auto;}
    input[type=text]{flex:1;padding:.5rem;font-size:1rem;}
    button{padding:.5rem 1rem;font-size:1rem;}
  </style>
</head>
<body>
  <h2 style="text-align:center;">Gemma 3 Chatbot ({{model}})</h2>
  <div id="chat"></div>

  <form id="form">
    <input id="prompt" type="text" autocomplete="off" placeholder="Type your message…">
    <button type="submit">Send</button>
  </form>

  <script>
    const chat   = document.getElementById('chat');
    const prompt = document.getElementById('prompt');

    document.getElementById('form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const text = prompt.value.trim();
      if (!text) return;

      chat.innerHTML += `<div class="bubble user">${text}</div>`;
      prompt.value = '';
      chat.scrollTop = chat.scrollHeight;

      const res  = await fetch('/api/chat', {
                     method: 'POST',
                     headers: {'Content-Type':'application/json'},
                     body: JSON.stringify({prompt: text})
                   });
      const data = await res.json();
      chat.innerHTML += `<div class="bubble bot">${data.response}</div>`;
      chat.scrollTop = chat.scrollHeight;
    });
  </script>
</body>
</html>
"""

# -------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------
@app.route("/")
def index():
    return render_template_string(HTML_PAGE, model=MODEL_NAME)

@app.route("/api/chat", methods=["POST"])
def chat():
    user_prompt = request.json.get("prompt", "").strip()
    if not user_prompt:
        return jsonify({"error": "Prompt is empty"}), 400

    try:
        ollama_payload = {
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": user_prompt}],
            "stream": False          # return a single, non-streaming JSON response
        }
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=ollama_payload, timeout=300)
        r.raise_for_status()
        content = r.json()["message"]["content"]
        return jsonify({"response": content})
    except Exception as err:
        return jsonify({"error": str(err)}), 500

# -------------------------------------------------------------------
# Entry-point
# -------------------------------------------------------------------
if __name__ == "__main__":
    # Before starting you may want to pull/load the model once:
    #   ollama run gemma3:1b-it-qat  (this downloads & caches the model)
    app.run(host="0.0.0.0", port=8080)
