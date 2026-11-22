import re


class UseCase:
    name = "Base"
    description = ""
    model = "gemma-4-e2b-it-realtime"
    prompt = ""
    method_params = None
    hits_needed = 2
    cooldown = 15

    def check(self, payload):
        """Return (alert, message). Default: VLM replies 'ALERT: <reason>' or 'CLEAR'."""
        text = str(payload or "").strip()
        m = re.match(r"\W*ALERT\W*(.*)", text, re.I | re.S)
        return (True, m.group(1).strip() or self.name) if m else (False, text or "Clear")
