#!/usr/bin/env python3
"""Push new episodes from episodes.json into the Webflow Episodes collection (live)."""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

COLLECTION_ID = "6aabd45c1a896a6ef8137d3a"
API = f"https://api.webflow.com/v2/collections/{COLLECTION_ID}/items"
SERIES = {
    "Main Story": "f3b2f014ac1033b8137d24e4f16e9d2f",
    "Cryptid Club": "8401355ccf3da8f1e20ea23681076a47",
}
FEATURED = "featured-episode"
TOKEN = os.environ.get("WEBFLOW_TOKEN")


def call(method, url, body=None, tries=4):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as err:
            if err.code == 429 and attempt < tries - 1:
                time.sleep(int(err.headers.get("Retry-After", "5")) + 1)
                continue
            sys.exit(f"{method} {url} failed: {err.code} {err.read().decode(errors='replace')}")


def existing_items():
    items, offset = [], 0
    while True:
        page = call("GET", f"{API}?limit=100&offset={offset}")
        items += page.get("items", [])
        total = page.get("pagination", {}).get("total", 0)
        offset += 100
        if offset >= total:
            return items


def field_data(ep, slug, featured):
    data = {
        "name": ep["name"],
        "slug": slug,
        "series": SERIES[ep["series"]],
        "published": ep["published"],
        "duration": ep["duration"],
        "audio-url": ep["audioUrl"],
        "summary": ep["summary"],
        "show-notes": ep["showNotes"],
        "guid": ep["guid"],
        FEATURED: featured,
    }
    if ep.get("season") is not None:
        data["season"] = ep["season"]
    if ep.get("episode") is not None:
        data["episode"] = ep["episode"]
    if ep.get("cover"):
        data["cover"] = {"url": ep["cover"]}
    return data


def main():
    if not TOKEN:
        sys.exit("WEBFLOW_TOKEN secret is missing.")

    feed = json.loads(Path("episodes.json").read_text(encoding="utf-8"))["episodes"]
    items = existing_items()
    known = {i["fieldData"].get("guid") for i in items}
    slugs = {i["fieldData"].get("slug") for i in items}

    new = [ep for ep in feed if ep["guid"] not in known and ep["series"] in SERIES]
    if not new:
        print("No new episodes.")
        return

    newest_guid = max(feed, key=lambda e: e["published"])["guid"]
    new.sort(key=lambda e: e["published"])

    for ep in new:
        slug, n = ep["slug"], 2
        while slug in slugs:
            slug, n = f'{ep["slug"]}-{n}', n + 1
        slugs.add(slug)
        is_newest = ep["guid"] == newest_guid
        call("POST", f"{API}/live", {
            "isArchived": False,
            "isDraft": False,
            "fieldData": field_data(ep, slug, is_newest),
        })
        print(f'Added: {ep["name"]}' + (" (featured)" if is_newest else ""))
        time.sleep(1)

    if any(ep["guid"] == newest_guid for ep in new):
        stale = [
            {"id": i["id"], "fieldData": {FEATURED: False}}
            for i in items if i["fieldData"].get(FEATURED)
        ]
        if stale:
            call("PATCH", f"{API}/live", {"items": stale})
            print(f"Unfeatured {len(stale)} older item(s).")


if __name__ == "__main__":
    main()
