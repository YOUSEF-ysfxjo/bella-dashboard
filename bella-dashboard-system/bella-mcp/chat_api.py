"""
Bella Dashboard Chat API.

A lightweight HTTP endpoint that powers the in-page Bella chat in bella-dashboard.
Run from bella-mcp folder:
  uv run python chat_api.py
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

HOST = os.environ.get("BELLA_CHAT_HOST", "0.0.0.0")
PORT = int(os.environ.get("BELLA_CHAT_PORT", "3002"))
MODEL = (
    os.environ.get("BELLA_CHAT_MODEL", "").strip()
    or os.environ.get("OPENAI_MODEL", "").strip()
    or "gpt-4o-mini"
)
SYSTEM_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "system_prompt.txt")


def _load_system_prompt() -> str:
    try:
        with open(SYSTEM_PROMPT_PATH, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "You are Bella, a focused assistant for the Bella dashboard roadmap."


def _llm_config() -> tuple[str, str] | None:
    """
    Returns (base_url, api_key) for an OpenAI-compatible endpoint.
    Supported:
    - OPENAI_API_KEY + optional OPENAI_BASE_URL
    - OPENROUTER_API_KEY (auto base URL)
    """
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or "https://api.openai.com/v1"

    if openai_key:
        return base_url, openai_key
    if openrouter_key:
        return "https://openrouter.ai/api/v1", openrouter_key
    return None


def _compose_messages(message: str, context: str, history: list[dict[str, Any]]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": _load_system_prompt()}]
    if context:
        messages.append(
            {
                "role": "system",
                "content": f"Dashboard context snapshot:\n{context}",
            }
        )
    for item in history[-12:]:
        role = item.get("role", "")
        text = item.get("text", "")
        if role in {"user", "assistant"} and isinstance(text, str) and text.strip():
            messages.append({"role": role, "content": text.strip()})
    messages.append({"role": "user", "content": message})
    return messages


def _generate_llm_reply(message: str, context: str, history: list[dict[str, Any]]) -> str:
    cfg = _llm_config()
    if not cfg:
        raise RuntimeError("No LLM key configured. Set OPENAI_API_KEY or OPENROUTER_API_KEY in .env.")
    base_url, api_key = cfg
    payload = {
        "model": MODEL,
        "messages": _compose_messages(message, context, history),
        "temperature": 0.35,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=45.0) as client:
        response = client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    choice = (data.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content", "")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("LLM returned an empty response.")
    return content.strip()


class ChatHandler(BaseHTTPRequestHandler):
    server_version = "BellaChatAPI/1.0"

    def _set_headers(self, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._set_headers(204)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/chat":
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not found"}).encode("utf-8"))
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            body = json.loads(raw) if raw else {}
            message = str(body.get("message", "")).strip()
            context = str(body.get("context", "")).strip()
            history = body.get("history", [])
            if not message:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "message is required"}).encode("utf-8"))
                return
            if not isinstance(history, list):
                history = []
            reply = _generate_llm_reply(message, context, history)
            self._set_headers(200)
            self.wfile.write(json.dumps({"reply": reply}).encode("utf-8"))
        except httpx.HTTPStatusError as e:
            self._set_headers(502)
            msg = f"Upstream LLM error: {e.response.status_code}"
            self.wfile.write(json.dumps({"error": msg}).encode("utf-8"))
        except Exception as e:  # noqa: BLE001
            self._set_headers(500)
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), ChatHandler)
    print(f"[Bella Chat API] Listening on http://{HOST}:{PORT}/chat")
    server.serve_forever()


if __name__ == "__main__":
    main()

