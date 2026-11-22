# VLM Live Alerts

A Gradio app for real-time alerts on live video (YouTube, HLS, RTSP, MP4 or a webcam), using the VLM Run Gateway. It connects over WebSocket and falls back to HTTP. YouTube links, including live streams and regular videos, are resolved to a playable stream and read like any other source.

## Use cases
| Folder | Alert |
|---|---|
| `usecases/shop_theft` | Someone hiding items in a bag or pocket |
| `usecases/fire_smoke` | Visible smoke or flames |

## Run
```bash
pip install -r requirements.txt
cp .env.example .env   # add VLM_API_KEY
python app.py          # http://localhost:7860
```

## Add a use case
Create `usecases/<name>/__init__.py`:
```python
from ..base import UseCase

class Ppe(UseCase):
    name = "PPE Check"
    description = "Workers without helmets."
    prompt = "If anyone lacks a hard hat reply 'ALERT: <who>', else 'CLEAR'."

USECASE = Ppe()
```
The app finds new folders on its own. If a use case uses a detection model, override `model` and `check(payload) -> (alert, message)`.

Options: `hits_needed` sets how many positive frames in a row trigger an alert. `cooldown` sets the minimum number of seconds between alerts. When `ALERT_WEBHOOK_URL` is set, each alert is also sent to that webhook.
