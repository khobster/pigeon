# Pigeon

A newsletter engine that actually goes out. No vendor, no platform, no monthly fee. A Google Sheet holds the list, a GitHub Action is the scheduler, and every issue is archived in public.

Pigeon is an [Arugula Motors](https://www.arugulamotors.com) build.

## The Heist

The first newsletter shipped on Pigeon: **the heist**, your personal art thief. One beautiful artwork a day, lifted from the world's open-access museums, plus a line from the canon, a find from the Library of Congress vaults, and a place to lay low.

Sections, daily:

- **Tonight's Haul** — one masterpiece, full size, from the Met, the Art Institute of Chicago, the Cleveland Museum of Art, or the Rijksmuseum
- **The Line** — a line lifted from somewhere in the western canon
- **From the Vault** — a find from the Library of Congress archives
- **On the Lam** — tonight's hideout, somewhere on earth

The archive lives in `docs/` and publishes via GitHub Pages. Every issue, every day, never a miss. That archive is the proof.

## How it runs

```
.github/workflows/heist-daily.yml   the cron
heist/build_issue.py                assembles the day's sections, renders, archives
engine/render.py                    template fill
engine/send.py                      sends to the list (Google Sheet) via SMTP
```

Local test (sends only to you):

```
cp .env.example .env   # fill in
python -m heist.build_issue --send
```

## Configuration

See `.env.example`. Subscribers live in a Google Sheet with a single `email` column header, shared with the service account. If no sheet is configured, Pigeon sends to `GMAIL_USER` only (test mode).
