import requests

url = "http://127.0.0.1:8000/chat"
user_id = "Nolan"

while True:
    msg = input("You: ")
    if msg.lower() in ("exit", "quit"):
        break
    resp = requests.post(url, json={"user_id": user_id, "message": msg})
    print("Gary:", resp.json().get("reply"))
