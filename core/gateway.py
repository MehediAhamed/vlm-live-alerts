import asyncio, base64, inspect, json, re, threading, time
from urllib.parse import urlparse
import cv2, httpx, websockets

CHAT_MODELS = ("gemma-4-e2b-it-realtime", "qwen3.5-0.8b-realtime")
METHODS = {**{m: "chat" for m in CHAT_MODELS}, "rfdetr-large": "detect", "rfdetr-seg-large": "segment",
           "sam3.1": "segment", "vitpose-plus-large": "pose", "hamer": "pose", "pp-ocrv6": "ocr"}


def encode_jpeg(img, quality=82, max_dim=768):
    h, w = img.shape[:2]
    if max(h, w) > max_dim:
        s = max_dim / max(h, w)
        img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()


def parse(content):
    if isinstance(content, str) and content.strip()[:1] in "{[":
        try:
            return json.loads(content)
        except Exception:
            pass
    return content


def _content(resp):
    ch = resp.get("choices") or [{}]
    return parse(ch[0].get("message", {}).get("content", ""))


class GatewayStream:
    """WebSocket session to the VLM Run gateway, falls back to HTTP."""

    def __init__(self, api_key, base_url, model, method, prompt="", method_params=None, max_inflight=2):
        self.key, self.base = api_key, base_url.rstrip("/")
        self.model, self.method, self.prompt = model, method, prompt
        self.params = method_params or {}
        self.max_inflight = max_inflight
        self.payload, self.latency, self.results, self.sent, self.errors = None, 0.0, 0, 0, 0
        self.transport, self._jpg, self._stop = "idle", None, False
        self.last_error, self._inflight, self._retry_after = "", 0, 0.0
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_until_complete, args=(self._run(),), daemon=True).start()

    def submit(self, frame):
        self._jpg = encode_jpeg(frame)

    def stop(self):
        self._stop = True

    def _set(self, payload, latency):
        self.payload, self.latency, self.results = payload, latency, self.results + 1

    def _take(self):
        jpg, self._jpg = self._jpg, None
        return jpg

    async def _run(self):
        """Keep a WS session alive. Realtime models are socket-only, so HTTP is
        used as a fallback only for models that actually support it."""
        backoff = 1.0
        while not self._stop:
            started = time.time()
            await self._ws()
            if self._stop:
                return
            if self.model not in CHAT_MODELS:
                await self._http()
                return
            # socket-only model: never fall back to HTTP, reconnect instead
            self.transport = "reconnecting"
            delay = self._retry_after or (1.0 if time.time() - started > 30 else min(backoff * 2, 15.0))
            backoff = delay if not self._retry_after else backoff
            self._retry_after = 0
            await asyncio.sleep(delay)

    def _ws_url(self):
        """Accept https://host/v1/openai, wss://host/v1/ws, etc. and return the wss URL."""
        p = urlparse(self.base)
        scheme = "ws" if p.scheme in ("http", "ws") else "wss"
        return f"{scheme}://{p.netloc}/v1/ws"

    def _http_base(self):
        """HTTP chat-completions base, derived from whatever URL style was configured."""
        p = urlparse(self.base)
        scheme = "http" if p.scheme in ("http", "ws") else "https"
        return f"{scheme}://{p.netloc}/v1/openai"

    async def _ws(self):
        url = self._ws_url()
        token = self.key
        # the gateway may answer with session.redirect to an edge server; follow it
        for _ in range(3):
            redirect = await self._session(url, token)
            if not redirect:
                return
            url = redirect.get("url") or url
            token = redirect.get("client_secret") or redirect.get("token") or token
        self.errors += 1
        self.last_error = "WS: too many session.redirect hops"

    async def _session(self, url, token):
        """Run one WS session. Returns the redirect dict if the server redirected us."""
        msg = {"type": "session.create", "model": self.model, "method": self.method, "max_inflight": self.max_inflight}
        if self.params:
            msg["method_params"] = self.params
        if self.prompt and self.model in CHAT_MODELS:
            msg["prompt"] = self.prompt
        headers = {"Authorization": f"Bearer {token}"}
        # websockets >=14 uses additional_headers, older versions use extra_headers
        hdr_kw = "additional_headers" if "additional_headers" in inspect.signature(websockets.connect).parameters else "extra_headers"
        self._inflight = 0
        self._jpg = None
        self.transport = "connecting"
        try:
            async with websockets.connect(url, **{hdr_kw: headers},
                                          open_timeout=12, ping_interval=15, max_size=8 << 20) as ws:
                await ws.send(json.dumps(msg))
                first = json.loads(await asyncio.wait_for(ws.recv(), 15))
                if first.get("type") == "session.redirect":
                    return first
                if first.get("type") == "error":
                    # e.g. model_provisioning_error: model is (re)starting, server says when to retry
                    self.errors += 1
                    self._retry_after = float(first.get("retry_after") or 0)
                    self.last_error = (f"{first.get('error_type')}: {first.get('message')} "
                                       f"(retrying in {self._retry_after:.0f}s)")[:300]
                    return None
                if first.get("type") != "session.created":
                    raise RuntimeError(first)
                gap = 1 / max(1.0, float(first.get("max_fps") or 20))
                limit = int(first.get("max_inflight") or self.max_inflight)
                self.transport = "WS"
                rx = asyncio.create_task(self._recv(ws))
                while not rx.done() and not self._stop:
                    jpg = self._take() if self._inflight < limit else None
                    if jpg is None:
                        await asyncio.sleep(0.01)
                        continue
                    self._inflight += 1
                    await ws.send(jpg)
                    self.sent += 1
                    await asyncio.sleep(gap)
                if self._stop:
                    rx.cancel()
                    await ws.send(json.dumps({"type": "session.close"}))
                    return
                # receiver ended first: server closed the socket or errored
                exc = rx.exception()
                raise exc or ConnectionError("server closed the WebSocket")
        except Exception as exc:
            self.errors += 1
            err = re.sub(r"ek_[\w.\-]+", "ek_***", str(exc))
            self.last_error = f"WS {url}: {type(exc).__name__}: {err}"[:300]
        return None

    async def _recv(self, ws):
        async for m in ws:
            if isinstance(m, str):
                ev = json.loads(m)
                if ev.get("type") == "frame.dropped":
                    # server skipped this frame (rate/busy): free the slot or we stall
                    self._inflight = max(0, self._inflight - 1)
                elif ev.get("type") == "result":
                    self._inflight = max(0, self._inflight - 1)
                    self._set(_content(ev.get("response", {})), float(ev.get("latency_ms") or 0))
                elif ev.get("type") == "error":
                    self._inflight = max(0, self._inflight - 1)
                    self.errors += 1
                    self.last_error = f"WS error: {ev.get('error_type')}: {ev.get('message')}"[:200]

    async def _http(self):
        self.transport = "HTTP"
        async with httpx.AsyncClient(timeout=30) as c:
            while not self._stop:
                jpg = self._take()
                if jpg is None:
                    await asyncio.sleep(0.02)
                    continue
                content = [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpg).decode()}}]
                if self.prompt:
                    content.append({"type": "text", "text": self.prompt})
                body = {"model": self.model, "method": self.method, "messages": [{"role": "user", "content": content}]}
                if self.params:
                    body["method_params"] = self.params
                if self.model not in CHAT_MODELS:
                    body["response_format"] = {"type": "json_object"}
                t0 = time.perf_counter()
                try:
                    r = await c.post(self._http_base() + "/chat/completions", json=body, headers={"Authorization": f"Bearer {self.key}"})
                    r.raise_for_status()
                    self.sent += 1
                    self._set(_content(r.json()), (time.perf_counter() - t0) * 1000)
                except Exception as exc:
                    self.errors += 1
                    detail = getattr(getattr(exc, "response", None), "text", "") or str(exc)
                    self.last_error = f"HTTP: {type(exc).__name__}: {detail}"[:200]
                    await asyncio.sleep(1)
