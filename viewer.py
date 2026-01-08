# viewer.py
import os, json, tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from pathlib import Path
from sandbox_manager import list_projects, run_project_by_name, list_pending_requests, approve_request

BASE = Path(__file__).resolve().parent
LOGS_DIR = BASE / "sandbox" / "logs"
PENDING_DIR = BASE / "sandbox" / "pending"

def load_logs():
    items = []
    if LOGS_DIR.exists():
        for p in sorted(LOGS_DIR.iterdir(), reverse=True):
            if p.suffix == ".json":
                try:
                    obj = json.loads(p.read_text(encoding="utf-8"))
                    items.append((p.name, obj))
                except Exception:
                    continue
    return items

def show_viewer():
    root = tk.Tk()
    root.title("Gary Sandbox Viewer")
    root.geometry("1000x650")

    # left frame: projects + pending
    left = tk.Frame(root, width=340)
    left.pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=6)
    tk.Label(left, text="Projects (sandbox/files)").pack(anchor="w")
    proj_list = tk.Listbox(left, width=45)
    proj_list.pack(fill=tk.Y, expand=False)

    tk.Label(left, text="Pending Requests").pack(anchor="w", pady=(8,0))
    pend_list = tk.Listbox(left, width=45)
    pend_list.pack(fill=tk.Y, expand=False)

    btn_frame = tk.Frame(left)
    btn_frame.pack(fill=tk.X, pady=6)
    run_btn = tk.Button(btn_frame, text="Run Project", width=12)
    approve_btn = tk.Button(btn_frame, text="Approve Request", width=12)
    refresh_btn = tk.Button(btn_frame, text="Refresh", width=12)
    run_btn.pack(side=tk.LEFT, padx=2)
    approve_btn.pack(side=tk.LEFT, padx=2)
    refresh_btn.pack(side=tk.LEFT, padx=2)

    # right frame: logs and details
    right = tk.Frame(root)
    right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
    tabs = ttk.Notebook(right)
    tabs.pack(fill=tk.BOTH, expand=True)
    tab_logs = ttk.Frame(tabs); tabs.add(tab_logs, text="Logs")
    tab_mem = ttk.Frame(tabs); tabs.add(tab_mem, text="Pending/Preview")

    log_tree = ttk.Treeview(tab_logs, columns=("fn","status"), show="headings")
    log_tree.heading("fn", text="File")
    log_tree.heading("status", text="Status")
    log_tree.column("fn", width=400)
    log_tree.column("status", width=120)
    log_tree.pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=6)
    txt_detail = scrolledtext.ScrolledText(tab_logs)
    txt_detail.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=6, pady=6)

    def load_all():
        proj_list.delete(0, tk.END)
        for p in list_projects():
            proj_list.insert(tk.END, p["name"])
        pend_list.delete(0, tk.END)
        for r in list_pending_requests():
            pend_list.insert(tk.END, r.get("request_file"))

        log_tree.delete(*log_tree.get_children())
        for fn, obj in load_logs():
            status = "OK" if obj.get("ok") else "ERR"
            log_tree.insert("", tk.END, values=(fn, status))

    def on_run():
        sel = proj_list.curselection()
        if not sel:
            messagebox.showinfo("Run", "Select a project first.")
            return
        name = proj_list.get(sel[0])
        res = run_project_by_name(name)
        messagebox.showinfo("Run result", json.dumps(res, indent=2)[:2000])
        load_all()

    def on_approve():
        sel = pend_list.curselection()
        if not sel:
            messagebox.showinfo("Approve", "Select a pending request first.")
            return
        reqfile = pend_list.get(sel[0])
        ok = approve_request(reqfile)
        messagebox.showinfo("Approve", json.dumps(ok, indent=2))
        load_all()

    def on_select_log(event):
        sel = log_tree.selection()
        if not sel:
            return
        item = log_tree.item(sel[0])
        fn = item["values"][0]
        path = LOGS_DIR / fn
        if not path.exists():
            txt_detail.delete("1.0", tk.END); txt_detail.insert(tk.END, "missing")
            return
        txt_detail.delete("1.0", tk.END)
        txt_detail.insert(tk.END, path.read_text(encoding="utf-8"))

    run_btn.config(command=on_run)
    approve_btn.config(command=on_approve)
    refresh_btn.config(command=load_all)
    log_tree.bind("<<TreeviewSelect>>", on_select_log)

    load_all()
    root.mainloop()

if __name__ == "__main__":
    show_viewer()
