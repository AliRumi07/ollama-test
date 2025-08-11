# main.py
import os
import logging
from typing import Optional

import requests
from flask import Flask, request, jsonify, render_template_string

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
OLLAMA_URL  = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL_NAME  = os.getenv("LLM_MODEL",  "gemma3:1b-it-qat")
TIMEOUT_SEC = int(os.getenv("OLLAMA_TIMEOUT", "300"))

# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s"
)
log = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Flask
# ------------------------------------------------------------------
app = Flask(__name__)

HTML = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Gemma 3 Chatbot</title>
<style>
 body{font-family:sans-serif;background:#f9f9f9;margin:0;padding:2rem;}
 #chat{max-width:800px;margin:auto;}
 .bubble{padding:.6rem 1rem;border-radius:8px;margin:.3rem 0;max-width:90%;}
 .user{background:#d1e7dd;text-align:right;margin-left:10%;}
 .bot {background:#fff;border:1px solid #ccc;}
 .err {background:#ffe6e6;border:1px solid #e69393;color:#b30000;}
 form{display:flex;gap:.5rem;margin-top:1rem;max-width:800px;margin:auto;}
 input[type=text]{flex:1;padding:.5rem;font-size:1rem;}
 button{padding:.5rem 1rem;font-size:1rem;}
</style>
</head>
<body>
<h2 style="text-align:center;">Gemma 3 Chatbot ({{model}})</h2>
<div id="chat"></div>

<form id="form">
  <input id="prompt" type="text" autocomplete="off"
         placeholder="Type your message…">
  <button type="submit">Send</button>
</form>

<script>
const chat   = document.getElementById('chat');
const prompt = document.getElementById('prompt');

document.getElementById('form').addEventListener('submit', async evt => {
  evt.preventDefault();
  const text = prompt.value.trim();
  if (!text) return;

  chat.innerHTML += `<div class="bubble user">${text}</div>`;
  prompt.value = '';
  chat.scrollTop = chat.scrollHeight;

  try {
    const res  = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({prompt: text})
    });
    const data = await res.json();
    if (data.error){
      chat.innerHTML += `<div class="bubble err">${data.error}</div>`;
    } else {
      chat.innerHTML += `<div class="bubble bot">${data.response}</div>`;
    }
  } catch (err){
    chat.innerHTML += `<div class="bubble err">${err}</div>`;
  }
  chat.scrollTop = chat.scrollHeight;
});
</script>
</body>
</html>
"""

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def call_ollama(prompt: str) -> Optional[str]:
    """Send the prompt to Ollama and return the assistant reply."""
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }
    log.info("→ Ollama request: %s", payload)
    r = requests.post(f"{OLLAMA_URL}/api/chat",
                      json=payload,
                      timeout=TIMEOUT_SEC)
    r.raise_for_status()
    data = r.json()
    log.info("← Ollama response: %s", data)

    # According to the API spec the answer is in message.content
    return data.get("message", {}).get("content")

# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------
@app.route("/")
def index():
    return render_template_string(HTML, model=MODEL_NAME)

@app.route("/api/chat", methods=["POST"])
def chat_api():
    user_prompt = request.json.get("prompt", "").strip()
    if not user_prompt:
        return jsonify(error="Prompt is empty"), 400

    try:
        answer = call_ollama(user_prompt)
        if not answer:
            raise RuntimeError("No content field in Ollama reply.")
        return jsonify(response=answer)
    except Exception as exc:
        log.exception("Chat failed")
        return jsonify(error=str(exc)), 500

# ------------------------------------------------------------------
# Run
# ------------------------------------------------------------------
if __name__ == "__main__":
    # Pull once if you haven't already:
    #    ollama run gemma3:1b-it-qat
    app.run(host="0.0.0.0", port=8080)
