# sandbox_manager.py
# Safe-ish sandbox runner: runs Python snippets/projects in a separate process,
# in a dedicated sandbox folder, with a strict timeout and minimal environment.
# NOT as secure as Docker/VM, but much safer than running code inline.

import os
import sys
import tempfile
import uuid
import json
import shutil
import time
import subprocess
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent
SANDBOX_ROOT = BASE / "sandbox"
FILES_DIR = SANDBOX_ROOT / "files"
LOGS_DIR = SANDBOX_ROOT / "logs"
PENDING_DIR = SANDBOX_ROOT / "pending"

# ensure directories exist
for d in (FILES_DIR, LOGS_DIR, PENDING_DIR):
    d.mkdir(parents=True, exist_ok=True)

def _timestamp():
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")

def _safe_env():
    """
    Minimal environment for the subprocess: remove host secrets and proxies.
    Keep only necessary variables (python exec path provided explicitly).
    """
    env = {}
    # keep locale vars so Python doesn't crash on weird locales
    for k in ("SYSTEMROOT","PATH","TMP","TEMP"):
        if k in os.environ:
            env[k] = os.environ[k]
    # Ensure unbuffered to get complete output
    env["PYTHONUNBUFFERED"] = "1"
    return env

def run_code_snippet(code: str, timeout: int = 7):
    """
    Run `code` as a python script inside a temp file in the sandbox.
    Returns dict with ok/output/error, logs the run.
    """
    tmpdir = tempfile.mkdtemp(prefix="gary_sandbox_")
    script_path = Path(tmpdir) / "script.py"
    try:
        script_path.write_text(code, encoding="utf-8")
        start = time.time()
        # Run using sys.executable with -I (isolated mode) to reduce env influence
        cmd = [sys.executable, "-I", str(script_path)]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            text=True,
            env=_safe_env(),
            cwd=tmpdir
        )
        elapsed = time.time() - start
        out = proc.stdout or ""
        result = {"ok": True, "output": out, "elapsed": elapsed}
    except subprocess.TimeoutExpired:
        result = {"ok": False, "error": "timeout", "output": ""}
    except Exception as e:
        result = {"ok": False, "error": str(e), "output": ""}
    finally:
        # write a log file
        log_name = f"{_timestamp()}_{uuid.uuid4().hex[:6]}.json"
        log_path = LOGS_DIR / log_name
        log_data = {
            "ts": _timestamp(),
            "type": "snippet",
            "ok": result.get("ok", False),
            "error": result.get("error"),
            "elapsed": result.get("elapsed"),
            "output": result.get("output")[:10000],  # cap
            "code_preview": code[:2000]
        }
        try:
            log_path.write_text(json.dumps(log_data, indent=2), encoding="utf-8")
        except Exception:
            pass
        # cleanup temp dir
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass
    return result

def save_project(filename: str, code: str):
    """
    Save a file to sandbox/files (this is Gary's working project area).
    filename should end with .py
    """
    safe = os.path.basename(filename)
    if not safe.endswith(".py"):
        safe += ".py"
    path = FILES_DIR / safe
    path.write_text(code, encoding="utf-8")
    return str(path)

def list_projects():
    files = []
    for p in sorted(FILES_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.suffix == ".py":
            files.append({
                "name": p.name,
                "size": p.stat().st_size,
                "created": datetime.utcfromtimestamp(p.stat().st_ctime).isoformat()
            })
    return files

def run_project_by_name(name: str, timeout: int = 10):
    """
    Run a project file from sandbox/files safely (same isolation).
    """
    safe = os.path.basename(name)
    path = FILES_DIR / safe
    if not path.exists():
        return {"ok": False, "error": "not found"}
    code = path.read_text(encoding="utf-8")
    # run via run_code_snippet but set cwd to the files dir to allow relative imports inside sandbox
    tmpdir = tempfile.mkdtemp(prefix="gary_sandbox_project_")
    script_copy = Path(tmpdir) / safe
    script_copy.write_text(code, encoding="utf-8")
    try:
        start = time.time()
        cmd = [sys.executable, "-I", str(script_copy)]
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout, text=True, env=_safe_env(), cwd=tmpdir
        )
        elapsed = time.time() - start
        out = proc.stdout or ""
        result = {"ok": True, "output": out, "elapsed": elapsed}
    except subprocess.TimeoutExpired:
        result = {"ok": False, "error": "timeout", "output": ""}
    except Exception as e:
        result = {"ok": False, "error": str(e), "output": ""}
    finally:
        log_name = f"{_timestamp()}_{uuid.uuid4().hex[:6]}.json"
        (LOGS_DIR / log_name).write_text(json.dumps({
            "ts": _timestamp(),
            "type": "project",
            "project": safe,
            "ok": result.get("ok", False),
            "error": result.get("error"),
            "elapsed": result.get("elapsed"),
            "output": result.get("output")[:10000],
        }, indent=2), encoding="utf-8")
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass
    return result

def create_pending_request(name: str, code: str, reason: str = ""):
    """
    Gary can request that a file be added to the approved toolset.
    Store it in sandbox/pending as a JSON for you to review.
    """
    req = {
        "ts": _timestamp(),
        "name": name,
        "reason": reason,
        "code_preview": code[:4000],
        "code_full_path": None
    }
    # save full code file
    fname = f"{_timestamp()}_{uuid.uuid4().hex[:6]}_{name}"
    if not fname.endswith(".py"):
        fname += ".py"
    fullpath = PENDING_DIR / fname
    fullpath.write_text(code, encoding="utf-8")
    req["code_full_path"] = str(fullpath)
    reqpath = PENDING_DIR / (fname + ".request.json")
    reqpath.write_text(json.dumps(req, indent=2), encoding="utf-8")
    return {"ok": True, "request_file": str(reqpath)}

def list_pending_requests():
    out = []
    for p in sorted(PENDING_DIR.iterdir(), reverse=True):
        if p.name.endswith(".request.json"):
            try:
                obj = json.loads(p.read_text(encoding="utf-8"))
                out.append({"request_file": str(p), **obj})
            except Exception:
                continue
    return out

def approve_request(request_file: str, approved_dir: Path = None):
    """
    Move pending request's code into sandbox/files (approved) and remove pending file.
    """
    approved_dir = approved_dir or FILES_DIR
    try:
        req = json.loads(Path(request_file).read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"bad request file: {e}"}
    code_path = Path(req.get("code_full_path"))
    if not code_path.exists():
        return {"ok": False, "error": "code file missing"}
    target = approved_dir / Path(code_path).name
    shutil.move(str(code_path), str(target))
    # remove request json
    try:
        Path(request_file).unlink()
    except Exception:
        pass
    return {"ok": True, "approved_path": str(target)}
