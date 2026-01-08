# gary_api.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os, json
from dotenv import load_dotenv
import openai

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY") or ""
if OPENAI_KEY:
    openai.api_key = OPENAI_KEY

app = FastAPI(title="ElegantAI")

# --------- CORS (for local testing) ---------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------- Data Models ---------
class ChatRequest(BaseModel):
    user_id: str
    message: str
    chat_name: Optional[str] = "default"

# --------- Memory ---------
MEMORY_FILE = "memory.json"
if not os.path.exists(MEMORY_FILE):
    json.dump({"facts": [], "personality": ""}, open(MEMORY_FILE, "w"))

def recall_context():
    mem = json.load(open(MEMORY_FILE, "r"))
    return " ".join(mem.get("facts", []))

def remember_fact(fact: str):
    fact = fact.strip()
    if not fact:
        return False
    mem = json.load(open(MEMORY_FILE, "r"))
    mem.setdefault("facts", [])
    mem["facts"].append(fact)
    json.dump(mem, open(MEMORY_FILE, "w"))
    return True

# --------- OpenAI Chat ---------
def ask_openai(prompt: str) -> str:
    if not OPENAI_KEY:
        return "(offline) " + prompt[::-1]
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-5-mini",
            messages=[
                {"role":"system","content":"You are ElegantAI, friendly, elegant, and witty."},
                {"role":"user","content":prompt}
            ],
            max_completion_tokens=1000,
            temperature=0.9
        )
        return resp.choices[0].message["content"].strip()
    except Exception as e:
        return f"(error) {e}"

# --------- API Routes ---------
@app.post("/chat")
def chat(req: ChatRequest):
    context = recall_context()
    prompt = f"{context}\nUser: {req.message}"
    reply = ask_openai(prompt)
    return {"reply": reply}

@app.post("/remember")
def remember(req: ChatRequest):
    ok = remember_fact(req.message)
    return {"success": ok}

@app.get("/memory")
def get_memory():
    mem = json.load(open(MEMORY_FILE, "r"))
    return mem
