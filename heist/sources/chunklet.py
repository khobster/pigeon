"""The Line: one line lifted from the western canon, via chubby chunklet."""
import time

import requests

API = "https://pu30nzsu59.execute-api.us-east-1.amazonaws.com/dev/chunklet"
PARAMS = {"style": "canon", "modern": 0, "context": 1, "tts": 0}


def steal(rng):
    last = None
    for attempt in range(3):  # Lambda cold starts deserve a second chance
        try:
            data = requests.get(API, params=PARAMS, timeout=30).json()
            text = (data.get("text") or "").strip()
            if text:
                work = (data.get("work") or "").strip()
                author = (data.get("author") or "").strip()
                summary = ""
                ctx = data.get("context")
                if isinstance(ctx, dict):
                    summary = (ctx.get("summary") or "").split(". ")[0].rstrip(".")
                    summary = summary + "." if summary else ""
                attribution = ", ".join(p for p in (work, author) if p)
                return {"text": text, "attribution": attribution, "summary": summary}
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"chunklet unavailable: {last}")
