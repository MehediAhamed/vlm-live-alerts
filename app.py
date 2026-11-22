import os, time
import gradio as gr
from dotenv import load_dotenv
from core.stream import StreamReader
from core.gateway import GatewayStream, METHODS
from core.draw import overlay
from core.alerts import notify
from usecases import load

load_dotenv()
API_KEY = os.getenv("VLM_API_KEY", "")
BASE_URL = os.getenv("VLM_BASE_URL", "https://dev-gateway.vlm.run/v1/openai")
DEFAULT_SOURCE = os.getenv("SOURCE_URL", "https://ireplay.tv/test/blender.m3u8")
USECASES = load()


def run(name, source, model, prompt, fps):
    if not API_KEY:
        raise gr.Error("Set VLM_API_KEY in .env")
    uc = USECASES[name]
    reader = StreamReader(source)
    gw = GatewayStream(API_KEY, BASE_URL, model, METHODS[model], prompt, uc.method_params if model == uc.model else None)
    log, hits, seen, last_alert = [], 0, 0, 0.0
    alert, msg = False, "Waiting for first result..."
    try:
        while True:
            frame = reader.read()
            if frame is None:
                yield None, f"Connecting... {reader.error or ''}", "\n".join(log)
                time.sleep(0.5)
                continue
            gw.submit(frame)
            if gw.results != seen:
                seen = gw.results
                alert, msg = uc.check(gw.payload)
                hits = hits + 1 if alert else 0
                if hits >= uc.hits_needed and time.time() - last_alert > uc.cooldown:
                    last_alert = time.time()
                    log.insert(0, f"🚨 {time.strftime('%H:%M:%S')}  {msg}")
                    gr.Warning(f"{uc.name}: {msg}")
                    notify(uc.name, msg)
            info = f"{model} | {gw.transport} | {gw.latency:.0f} ms | sent {gw.sent} | results {gw.results} | err {gw.errors}"
            status = f"{'🚨 ALERT' if alert else '✅ Clear'} — {msg}"
            if gw.results == 0 and gw.last_error:
                status = f"⚠️ No results yet — {gw.last_error}"
            yield overlay(frame, gw.payload, alert, msg, info), status, "\n".join(log[:50])
            time.sleep(1 / fps)
    finally:
        gw.stop()
        reader.stop()


def pick(name):
    uc = USECASES[name]
    return uc.description, uc.model, uc.prompt


with gr.Blocks(title="VLM Live Alerts") as demo:
    gr.Markdown("# 🎥 VLM Live Alerts")
    first = next(iter(USECASES))
    with gr.Row():
        with gr.Column(scale=1):
            usecase = gr.Dropdown(list(USECASES), value=first, label="Use case")
            desc = gr.Markdown(USECASES[first].description)
            source = gr.Textbox(DEFAULT_SOURCE, label="Source (YouTube / HLS / RTSP / MP4 URL or webcam index)")
            with gr.Accordion("Advanced", open=False):
                model = gr.Dropdown(list(METHODS), value=USECASES[first].model, label="Model")
                prompt = gr.Textbox(USECASES[first].prompt, label="Prompt", lines=4)
                fps = gr.Slider(1, 15, 5, step=1, label="Display FPS")
            with gr.Row():
                start = gr.Button("▶ Start", variant="primary")
                stop = gr.Button("■ Stop", variant="stop")
            status = gr.Textbox(label="Status", interactive=False)
            alerts = gr.Textbox(label="Alert log", lines=10, interactive=False)
        with gr.Column(scale=2):
            video = gr.Image(label="Live", interactive=False)
    usecase.change(pick, usecase, [desc, model, prompt])
    job = start.click(run, [usecase, source, model, prompt, fps], [video, status, alerts])
    stop.click(None, cancels=[job])

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0")
