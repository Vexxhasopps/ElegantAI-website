# sandbox_autorun.py
# Safe offline sandbox autorun for Gary
# Generates and runs tasks autonomously when idle

import threading
import time
import json
import os
from pathlib import Path
from sandbox_manager import run_project_by_name, run_code_snippet, list_projects
import random

# ---------- CONFIG ----------
AUTORUN_CONFIG = {
    "enabled": True,           # True to let it run automatically
    "idle_seconds": 200,        # Seconds of inactivity before running tasks
    "loop_interval": 20,       # Seconds between idle checks
    "task_mode": "autotasks",  # 'projects' or 'autotasks'
    "max_runs_per_cycle": 2,   # Max tasks/projects to run per loop
    "generate_tasks": True,    # Generate new tasks if none exist
}

# ---------- STATE ----------
_state = {
    "last_activity_ts": time.time(),
    "running": True
}

# ---------- PATHS ----------
BASE_DIR = Path(__file__).resolve().parent
PENDING_DIR = BASE_DIR / "sandbox" / "pending"
LOG_FILE = BASE_DIR / "sandbox_autorun.log"
PENDING_DIR.mkdir(parents=True, exist_ok=True)

# ---------- UTILITIES ----------
def log(message: str):
    ts = time.strftime("[%Y-%m-%d %H:%M:%S]")
    line = f"{ts} {message}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def set_activity_now():
    _state["last_activity_ts"] = time.time()
    log("Activity registered. Resetting idle timer.")

def generate_autotask_file():
    """
    Create a simple Python task file for Gary to run.
    """
    task_templates = [
        "print('Hello from Gary!')",
        "x = sum(range(10)); print('Sum 0-9 =', x)",
        "for i in range(3): print('Task iteration', i)",
        f"print('Gary idle task executed at {time.strftime('%H:%M:%S')}')",
    ]
    code = random.choice(task_templates)
    ts = int(time.time() * 1000)
    fname = PENDING_DIR / f"autotask_{ts}.py"
    try:
        fname.write_text(code, encoding="utf-8")
        log(f"Generated new autotask: {fname.name}")
    except Exception as e:
        log(f"Failed to write autotask: {e}")

# ---------- AUTORUN LOOP ----------
def autorun_loop():
    _state["running"] = True
    log("Sandbox autorun started.")
    
    while _state["running"]:
        try:
            cfg = AUTORUN_CONFIG
            if not cfg["enabled"]:
                log("Autorun disabled. Sleeping...")
                time.sleep(cfg["loop_interval"])
                continue

            idle = time.time() - _state["last_activity_ts"]
            log(f"Idle check: {idle:.1f}s")
            if idle < cfg["idle_seconds"]:
                log("Not idle yet. Skipping this loop.")
                time.sleep(cfg["loop_interval"])
                continue

            runs = 0

            # ---------- Projects ----------
            if cfg["task_mode"] == "projects":
                projects = list_projects()
                if not projects and cfg.get("generate_tasks", False):
                    log("No projects found to run.")
                for p in projects[:cfg["max_runs_per_cycle"]]:
                    name = p["name"]
                    log(f"Running project: {name}")
                    try:
                        run_project_by_name(name)
                        runs += 1
                    except Exception as e:
                        log(f"Error running project {name}: {e}")
                    if runs >= cfg["max_runs_per_cycle"]:
                        break

            # ---------- Autotasks ----------
            elif cfg["task_mode"] == "autotasks":
                pending_files = sorted(PENDING_DIR.glob("autotask_*.py"))
                
                # Generate new tasks if none exist
                if not pending_files and cfg.get("generate_tasks", False):
                    log("No pending autotasks found. Generating new tasks...")
                    for _ in range(cfg["max_runs_per_cycle"]):
                        generate_autotask_file()
                    pending_files = sorted(PENDING_DIR.glob("autotask_*.py"))

                # Run pending tasks
                for f in pending_files[:cfg["max_runs_per_cycle"]]:
                    log(f"Running autotask: {f.name}")
                    try:
                        code = f.read_text(encoding="utf-8")
                        run_code_snippet(code)
                        f.unlink(missing_ok=True)
                        runs += 1
                    except Exception as e:
                        log(f"Error running autotask {f.name}: {e}")
                    if runs >= cfg["max_runs_per_cycle"]:
                        break

            if runs > 0:
                log(f"Cycle completed. Ran {runs} task(s).")
            else:
                log("No tasks were run this cycle.")

        except Exception as e_outer:
            log(f"Autorun loop exception: {e_outer}")
        
        time.sleep(cfg["loop_interval"])

    log("Sandbox autorun stopped.")

# ---------- THREAD CONTROL ----------
def start_autorun_thread():
    t = threading.Thread(target=autorun_loop, daemon=True)
    t.start()
    return t

def stop_autorun():
    _state["running"] = False
