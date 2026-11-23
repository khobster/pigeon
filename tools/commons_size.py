"""Real pixel size of Wikimedia Commons files, 50 per API call, so the
Commons-backed pools can drop originals too small to look sharp."""
from urllib.parse import unquote

import requests

API = "https://commons.wikimedia.org/w/api.php"
HEAD = {"User-Agent": "the-heist-newsletter/1.0 (https://heist.arugulamotors.com; kevin.murawinski@gmail.com)"}


def filename(image_url):
    """https://commons.wikimedia.org/wiki/Special:FilePath/X.jpg?width=1600 -> X.jpg"""
    return unquote(image_url.split("Special:FilePath/", 1)[1].split("?", 1)[0])


def long_sides(image_urls):
    """{image_url: max(width, height)} for every file Commons knows about."""
    names = {filename(u).replace("_", " "): u for u in image_urls}
    out, todo = {}, list(names)
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        r = requests.get(API, headers=HEAD, timeout=120, params={
            "action": "query", "format": "json", "prop": "imageinfo", "iiprop": "size",
            "titles": "|".join("File:" + n for n in batch)}).json()
        norm = {n["to"]: n["from"] for n in r["query"].get("normalized", [])}
        for page in r["query"]["pages"].values():
            info = (page.get("imageinfo") or [{}])[0]
            title = norm.get(page["title"], page["title"])[5:]
            if title in names and info.get("width"):
                out[names[title]] = max(info["width"], info["height"])
    return out
