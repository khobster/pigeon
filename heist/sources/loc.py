"""From the Vault: a find from the Library of Congress archives."""
import requests

API = "https://www.loc.gov/photos/"
TOPICS = [
    "wpa poster", "travel poster", "panoramic photograph", "lighthouse",
    "circus poster", "baseball 1920", "world's fair", "old new york",
    "route 66", "jazz musician", "vaudeville", "national park poster",
    "ocean liner", "railroad poster", "diner", "drive-in theater",
]


def steal(rng):
    topic = rng.choice(TOPICS)
    results = requests.get(
        API,
        params={"q": topic, "fo": "json", "c": 60},
        timeout=30,
        headers={"User-Agent": "pigeon-heist/1.0"},
    ).json().get("results") or []
    rng.shuffle(results)
    for item in results:
        images = item.get("image_url") or []
        if not images:
            continue
        return {
            "title": (item.get("title") or "").strip(". "),
            "date": item.get("date") or "",
            "image": images[-1],  # largest listed
            "url": item.get("id") or item.get("url") or "https://www.loc.gov",
            "topic": topic,
        }
    raise RuntimeError(f"LOC: nothing usable for '{topic}'")
