"""Retest whether the Art Institute of Chicago is reachable from CI.

AIC was retired from the rotation on 2026-07-14 because Cloudflare hard-blocked
the GitHub Actions runner's datacenter IP (403/429 on both the API and the image
host, even through the wsrv proxy). A 2026-10 scout got clean 200s from a
different datacenter IP, suggesting the block MAY have lifted — but the only IP
that matters is the runner's. This script answers that, from inside CI.

It must be run on the runner (via the aic-retest workflow), NOT locally: a local
run tests your home IP, which was never the blocked one. It exercises the exact
production path — aic.steal() for the API, then the wsrv-wrapped + direct image
fetch with the build's real iPhone User-Agent — and prints a clear verdict. It
changes nothing; re-adding AIC to the rotation stays a manual decision.
"""
import random
import sys
from urllib.parse import quote

import requests

sys.path.insert(0, ".")
from heist.sources import aic  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"}


def resized(url, width=1120):
    return f"https://wsrv.nl/?url={quote(url, safe='')}&w={width}&fit=inside"


def probe(url, **kw):
    try:
        r = requests.get(url, headers=UA, timeout=30, stream=True, **kw)
        ct = r.headers.get("content-type", "")
        r.close()
        return f"{r.status_code} {ct}"
    except Exception as e:  # noqa: BLE001
        return f"ERR {e}"


def main():
    rng = random.Random(1)
    api_ok = img_ok = 0
    print("=== AIC API (aic.steal) ===")
    images = []
    for i in range(5):
        try:
            art = aic.steal(rng)
            api_ok += 1
            images.append(art["image"])
            print(f"  steal {i}: OK  {art['title'][:50]!r}")
        except Exception as e:  # noqa: BLE001
            print(f"  steal {i}: FAIL  {e}")

    print("=== AIC image fetch (production path: wsrv first, then direct) ===")
    for img in images[:3]:
        via_wsrv = probe(resized(img))
        direct = probe(img)
        if via_wsrv.startswith("200") or direct.startswith("200"):
            img_ok += 1
        print(f"  wsrv={via_wsrv:28} direct={direct}")

    print("\n=== VERDICT ===")
    if api_ok >= 1 and img_ok >= 1:
        print(f"AIC REACHABLE from this runner (api {api_ok}/5, images {img_ok}/{len(images[:3])}).")
        print("Block appears lifted — safe to re-add `aic` to build_haul's museums list.")
    else:
        print(f"AIC STILL BLOCKED from this runner (api {api_ok}/5, images {img_ok}/{len(images[:3])}).")
        print("Keep it retired.")


if __name__ == "__main__":
    main()
