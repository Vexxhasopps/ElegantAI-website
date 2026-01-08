"""
ElegantAI — Multi-user Premium AI Assistant
- Users can set a nickname (no preset name)
- Memory is per user (facts + personality)
- Premium tier (GPT-5) vs free tier (GPT-5-mini)
- Safe web search integration
- Token usage tracking
"""

import os
import json
import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import openai
import requests
import threading

# ----------------- CONFIG -----------------
load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY") or ""
SEARCH_API_KEY = os.getenv("SEARCH_API_KEY") or ""
openai.api_key = OPENAI_KEY

DATA_DIR = Path("elegantai_data")
MEMORY_DIR = DATA_DIR / "memory"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)
CHAT_DIR = DATA_DIR / "chat_history"
CHAT_DIR.mkdir(parents=True, exist_ok=True)

WEB_SEARCH_TIMEOUT = 8
WEB_SEARCH_RATE_LIMIT_PER_MIN = 6
MAX_CHAT_MESSAGES = 1000
MAX_SNIPPET_LENGTH = 800

FORBIDDEN_PATTERNS = [
    r"\brm\b", r"\brmdir\b", r"\brm -rf\b", r"\bdel\s+C:\\", r"\bsudo\b", r"\bshutdown\b",
    r"\bformat\b", r"\bpasswd\b", r"\bchown\b", r"\bchmod\b", r"curl\s", r"wget\s",
    r"nc\s", r"ncat\s", r"bash\s", r"exec\(", r"subprocess", r"system\("
]

_search_timestamps = []

# ----------------- UTILS -----------------
def clamp_text(s: str, max_len: int):
    return s if len(s) <= max_len else s[:max_len] + "..."

def is_forbidden_input(text: str) -> bool:
    t = text.lower()
    for p in FORBIDDEN_PATTERNS:
        if re.search(p, t):
            return True
    return False

def rate_limit_allows():
    global _search_timestamps
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=1)
    _search_timestamps = [t for t in _search_timestamps if t > cutoff]
    return len(_search_timestamps) < WEB_SEARCH_RATE_LIMIT_PER_MIN

def register_search_timestamp():
    _search_timestamps.append(datetime.utcnow())

# ----------------- MEMORY -----------------
def get_memory_path(user_id: str):
    return MEMORY_DIR / f"{user_id}.json"

def load_memory(user_id: str):
    path = get_memory_path(user_id)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"facts": [], "personality": ""}

def save_memory(user_id: str, memory: dict):
    path = get_memory_path(user_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2, ensure_ascii=False)

def remember_fact(user_id: str, fact: str):
    if is_forbidden_input(fact): return False
    memory = load_memory(user_id)
    memory.setdefault("facts", []).append(clamp_text(fact, 1000))
    save_memory(user_id, memory)
    return True

def set_personality(user_id: str, personality: str):
    if is_forbidden_input(personality): return False
    memory = load_memory(user_id)
    memory["personality"] = clamp_text(personality, 1000)
    save_memory(user_id, memory)
    return True

def recall_context(user_id: str) -> str:
    memory = load_memory(user_id)
    facts = " ".join(memory.get("facts", [])[:200])
    personality = memory.get("personality", "")
    return f"{personality} {facts}".strip()

# ----------------- WEB SEARCH -----------------
def safe_snippet_from_serpapi(resp_json):
    try:
        if "organic_results" in resp_json and resp_json["organic_results"]:
            snippet = resp_json["organic_results"][0].get("snippet", "")
            snippet = re.sub(r"https?://\S+", "[link]", snippet)
            snippet = re.sub(r"[\x00-\x1f]+", " ", snippet)
            return clamp_text(snippet, MAX_SNIPPET_LENGTH)
    except:
        pass
    return "(no web snippet)"

def web_search_safe(query: str) -> str:
    if not SEARCH_API_KEY: return "(web search disabled)"
    if not rate_limit_allows(): return "(rate limit reached)"
    if re.search(r"[<>\\\x00]", query): return "(invalid characters)"
    try:
        register_search_timestamp()
        params = {"q": query, "api_key": SEARCH_API_KEY}
        resp = requests.get("https://serpapi.com/search.json", params=params, timeout=WEB_SEARCH_TIMEOUT)
        data = resp.json()
        return safe_snippet_from_serpapi(data)
    except:
        return "(web search error)"

# ----------------- OPENAI -----------------
def ask_openai(prompt: str, user_id: str, premium: bool = False, use_search: bool = False) -> str:
    if not OPENAI_KEY:
        return "(offline) " + clamp_text(prompt[::-1], 500)

    model = "gpt-5" if premium else "gpt-5-mini"
    context = recall_context(user_id)
    system_msg = (
        f"You are ElegantAI, a premium personal AI assistant. "
        f"User nickname: {user_id}. Keep a chill, confident, and lively tone. "
        f"{context}"
    )

    user_prompt = prompt
    if use_search:
        snippet = web_search_safe(prompt)
        user_prompt += f"\n\nWeb search snippet:\n{snippet}"

    try:
        resp = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_prompt}
            ],
            max_completion_tokens=1000,
            temperature=1
        )
        text = resp.choices[0].message["content"].strip()
        if is_forbidden_input(text):
            return "(blocked) Unsafe content."
        return clamp_text(text, 3000)
    except Exception as e:
        return f"(AI error: {e})"

# ----------------- FASTAPI -----------------
app = FastAPI(title="ElegantAI API")

class ChatRequest(BaseModel):
    user_id: str
    message: str
    premium: Optional[bool] = False
    use_search: Optional[bool] = False

class MemoryRequest(BaseModel):
    user_id: str
    fact: Optional[str] = None
    personality: Optional[str] = None

@app.post("/chat")
def chat(req: ChatRequest):
    if is_forbidden_input(req.message):
        raise HTTPException(status_code=400, detail="Forbidden input detected")
    response = ask_openai(req.message, req.user_id, premium=req.premium, use_search=req.use_search)
    return {"reply": response}

@app.post("/memory")
def memory(req: MemoryRequest):
    if req.fact:
        ok = remember_fact(req.user_id, req.fact)
        return {"ok": ok, "type": "fact"}
    elif req.personality:
        ok = set_personality(req.user_id, req.personality)
        return {"ok": ok, "type": "personality"}
    return {"ok": False, "type": "none"}

@app.get("/memory/{user_id}")
def get_memory(user_id: str):
    return load_memory(user_id)

