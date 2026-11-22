import os, threading, time
import httpx


def notify(usecase, message):
    url = os.getenv("ALERT_WEBHOOK_URL")
    if url:
        body = {"usecase": usecase, "message": message, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "text": f"🚨 {usecase}: {message}"}
        threading.Thread(target=lambda: httpx.post(url, json=body, timeout=10), daemon=True).start()
