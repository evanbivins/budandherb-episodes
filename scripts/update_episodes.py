#!/usr/bin/env python3
"""Pull the Art19 feed and write episodes.json (Main Story + Cryptid Club only)."""
import html
import json
import re
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

FEED = "https://rss.art19.com/the-adventures-of-bud-herb"
OUT = Path("episodes.json")
MGCC_PREFIX = "mystra's glen cryptid club"
NS = {
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "content": "http://purl.org/rss/1.0/modules/content/",
}

FIRST_PARA = re.compile(r"^\s*<p>([\s\S]*?)</p>")
FOOTER_START = re.compile(r"<p>\s*(<strong>)?\s*Follow us on social", re.I)
DROP_PARA = re.compile(
    r"<p>[^<]*(Join the Mystra's Glen Cryptid Club on Patreon|Check out our Dashery store)[\s\S]*?</p>",
    re.I,
)
EMPTY_RUN = re.compile(r"(<p>(\s|&nbsp;|<br\s*/?>)*</p>\s*)+")
EDGE_EMPTY = re.compile(r"^(\s*<p><br></p>)+|(<p><br></p>\s*)+$")
TAGS = re.compile(r"<[^>]+>")


def text(item, path):
    el = item.find(path, NS)
    return (el.text or "").strip() if el is not None else ""


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def slugify(value):
    value = value.replace("ø", "o").replace("Ø", "o").replace("'", "").replace("\u2019", "")
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def iso_utc(pub_date):
    dt = parsedate_to_datetime(pub_date)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def split_description(desc):
    desc = desc.replace("\u2060", "")
    match = FIRST_PARA.match(desc)
    summary = html.unescape(TAGS.sub("", match.group(1))).strip() if match else ""
    notes = desc[match.end():] if match else desc
    cut = FOOTER_START.search(notes)
    if cut:
        notes = notes[: cut.start()]
    notes = DROP_PARA.sub("", notes)
    notes = EMPTY_RUN.sub("<p><br></p>", notes)
    notes = EDGE_EMPTY.sub("", notes).strip()
    return summary, notes


def main():
    req = urllib.request.Request(FEED, headers={"User-Agent": "budandherb-episodes/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        root = ET.fromstring(resp.read())

    episodes, seen = [], set()
    for item in root.iter("item"):
        title = text(item, "title")
        ep_type = text(item, "itunes:episodeType").lower()
        is_mgcc = title.lower().startswith(MGCC_PREFIX)

        if ep_type == "full":
            series, short = "Main Story", title
            slug = slugify(title)
        elif is_mgcc:
            series = "Cryptid Club"
            short = title.split(":", 1)[1].strip() if ":" in title else title
            slug = "cryptid-club-" + slugify(short)
        else:
            continue

        enclosure = item.find("enclosure")
        if enclosure is None or not enclosure.get("url"):
            continue

        base, n = slug, 2
        while slug in seen:
            slug, n = f"{base}-{n}", n + 1
        seen.add(slug)

        image = item.find("itunes:image", NS)
        summary, notes = split_description(
            text(item, "content:encoded") or text(item, "description")
        )

        episodes.append({
            "name": title,
            "shortTitle": short,
            "slug": slug,
            "series": series,
            "season": to_int(text(item, "itunes:season")),
            "episode": to_int(text(item, "itunes:episode")),
            "published": iso_utc(text(item, "pubDate")),
            "duration": text(item, "itunes:duration"),
            "audioUrl": enclosure.get("url"),
            "cover": image.get("href") if image is not None else "",
            "summary": summary,
            "showNotes": notes,
            "guid": text(item, "guid"),
        })

    if not episodes:
        sys.exit("No episodes parsed; leaving the existing file alone.")

    episodes.sort(key=lambda e: e["published"], reverse=True)

    if OUT.exists():
        try:
            if json.loads(OUT.read_text(encoding="utf-8")).get("episodes") == episodes:
                print("No changes.")
                return
        except (ValueError, KeyError):
            pass

    payload = {
        "updated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "count": len(episodes),
        "episodes": episodes,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(episodes)} episodes.")


if __name__ == "__main__":
    main()
