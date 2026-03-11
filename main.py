"""
USPTO Patent AI – Flask application.

Bridges the synchronous OpenAIAgent to Flask routes using SSE streaming.
"""

import logging
import os
import sys
import json
from functools import wraps

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

from flask import (
    Flask, render_template, request, jsonify,
    Response, session, redirect, url_for
)
from flask_cors import CORS

from config import USERS
from agents import OpenAIAgent

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(
    __name__,
    template_folder=os.path.join(PROJECT_ROOT, "frontend", "templates"),
    static_folder=os.path.join(PROJECT_ROOT, "frontend", "static"),
)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))
CORS(app)

agent = OpenAIAgent()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            if request.is_json:
                return jsonify({"error": "Authentication required", "redirect": "/login"}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


def sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
@require_auth
def index():
    first_name = session.get("first_name", "User")
    return render_template("index.html", firstName=first_name)


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    try:
        data     = request.get_json()
        username = (data.get("username") or "").strip()
        password = (data.get("password") or "")
    except Exception:
        return jsonify({"success": False, "message": "Invalid request"}), 400

    if not username or not password:
        return jsonify({"success": False, "message": "Username and password are required"}), 400

    expected = USERS.get(username)
    if expected and expected == password:
        session["authenticated"] = True
        session["username"]      = username
        session["first_name"]    = username.capitalize()
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Invalid username or password"}), 401


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})


@app.route("/chat_stream", methods=["POST"])
@require_auth
def chat_stream():
    try:
        data         = request.get_json()
        user_message = (data.get("message") or "") if data else ""
    except Exception as e:
        return jsonify({"error": f"Invalid request: {e}"}), 400

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    def generate(message: str):
        try:
            for event in agent.process_message_stream(message):
                yield sse(event)
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield sse({"type": "error", "error": str(e)})

    return Response(generate(user_message), mimetype="text/event-stream",
                    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


@app.route("/clear", methods=["POST"])
@require_auth
def clear_chat():
    username = session.get("username", "unknown")
    agent.clear_history(username=username)
    return jsonify({"message": "Chat history cleared"})


@app.route("/history", methods=["GET"])
@require_auth
def get_history():
    return jsonify({"history": agent.chat_history})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        app.run(debug=False, host="127.0.0.1", port=5000)
    except KeyboardInterrupt:
        print("\nServer stopped.")
    except Exception as e:
        print(f"Server error: {e}")
