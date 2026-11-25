"""Writes what docs/desk/ needs to set Kevin's line exactly as heist/squishy.py
will: the empty clipping (box, paper, no words), the type spec, the font and
pyphen's en_US patterns. Rerun after changing the box or the type settings.

    python tools/squishy_desk_assets.py
"""
import io
import json
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from heist import squishy as s  # noqa: E402

OUT = ROOT / "docs" / "desk"


def main():
    OUT.mkdir(exist_ok=True)
    blank = s.render("", seed=0)
    (OUT / "box.jpg").write_bytes(blank)
    w = Image.open(io.BytesIO(blank)).width
    box_w = Image.open(s.ASSETS / "box_ink.png").width
    m, g = s.MARGIN * s.U, s.GUTTER * s.U
    # working width of a page whose column is empty, as render() lays it out
    W = m + box_w + g + (s.COL * s.U + 2 * s.U) + 2 * m
    spec = {
        "scale": w / W,                       # working px to final image px
        "size": int(s.SIZE * s.U),            # type size, working px (as PIL draws it)
        "shape_size": s.SIZE * s.U,           # the scale harfbuzz positions with
        "ascender": s._pil.getmetrics()[0],   # PIL draws from the ascender line
        "pitch": s.PITCH * s.U,
        "col": s.COL * s.U,
        "indent": 1.1 * s.SIZE * s.U,
        "x": m + box_w + g,
        "y": m,
        "lines": s.LINES,
        "max_chars": 1200,
    }
    (OUT / "spec.json").write_text(json.dumps(spec, indent=1))
    shutil.copy(s.FONT, OUT / "Merriweather-Squishy.ttf")
    shutil.copy(s.ASSETS / "OFL.txt", OUT / "OFL.txt")
    hd = s.HY.hd
    pats = {k: [v[0], list(v[1])] for k, v in hd.patterns.items()}
    (OUT / "hyph-en_US.json").write_text(json.dumps({"left": s.HY.left, "right": s.HY.right,
                                                      "maxlen": hd.maxlen, "patterns": pats},
                                                     separators=(",", ":")))
    print(json.dumps(spec))


if __name__ == "__main__":
    main()
