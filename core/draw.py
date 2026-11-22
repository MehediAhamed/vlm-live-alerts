import cv2

RED, GREEN, DARK, CYAN = (40, 40, 230), (80, 200, 80), (42, 23, 15), (248, 189, 56)


def boxes(img, payload):
    items = next((payload[k] for k in ("predictions", "detections", "objects", "instances")
                  if isinstance(payload, dict) and isinstance(payload.get(k), list)), [])
    h, w = img.shape[:2]
    for it in items:
        b = it.get("bbox")
        if not b or len(b) != 4:
            continue
        if max(b) <= 1.5:
            b = [b[0] * w, b[1] * h, b[2] * w, b[3] * h]
        x1, y1, x2, y2 = map(int, b)
        cv2.rectangle(img, (x1, y1), (x2, y2), CYAN, 2)
        cv2.putText(img, str(it.get("class") or it.get("label") or ""), (x1, max(18, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, CYAN, 2)


def overlay(frame, payload, alert, text, info):
    img = frame.copy()
    h, w = img.shape[:2]
    boxes(img, payload)
    if alert:
        cv2.rectangle(img, (0, 0), (w - 1, h - 1), RED, 8)
    cv2.rectangle(img, (0, 0), (w, 30), DARK, -1)
    cv2.putText(img, info, (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 230, 230), 1, cv2.LINE_AA)
    cv2.rectangle(img, (0, h - 34), (w, h), RED if alert else DARK, -1)
    cv2.putText(img, text[:90], (8, h - 11), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (255, 255, 255) if alert else GREEN, 2, cv2.LINE_AA)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
