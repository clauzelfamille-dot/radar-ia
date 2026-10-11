#!/usr/bin/env python3
"""Signale toutes les URL du sitemap à IndexNow après un déploiement.

IndexNow est relayé entre Bing (qui alimente aussi ChatGPT Search et Copilot), Yandex, Seznam et Naver : les pages
nouvelles ou modifiées sont explorées en quelques heures au lieu de quelques semaines. Sans clé configurée, ne fait rien.

Usage : python3 build/indexnow.py --dist dist --site-url https://exemple.org/radar-ia/ [--config config/site.json]
"""
from __future__ import annotations
import argparse, json, re, sys, urllib.error, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

RACINE_DEPOT = Path(__file__).resolve().parent.parent
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", required=True); ap.add_argument("--site-url", required=True)
    ap.add_argument("--config", default=str(RACINE_DEPOT / "config" / "site.json"))
    a = ap.parse_args()
    try:
        cle = str(json.loads(Path(a.config).read_text(encoding="utf-8")).get("indexnow", {}).get("cle") or "")
    except (OSError, ValueError):
        cle = ""
    if not re.fullmatch(r"[a-zA-Z0-9-]{8,128}", cle):
        print("IndexNow : pas de clé configurée, rien à signaler."); return
    base = a.site_url.rstrip("/") + "/"
    if not (Path(a.dist) / f"{cle}.txt").is_file():
        print("IndexNow : fichier de clé absent du site généré, abandon."); return
    urls = [e.text.strip() for e in ET.parse(Path(a.dist) / "sitemap.xml").iter(NS + "loc") if e.text and e.text.startswith(base)]
    if not urls:
        print("IndexNow : sitemap vide."); return
    body = json.dumps({"host": urlparse(base).netloc, "key": cle, "keyLocation": base + f"{cle}.txt", "urlList": urls[:10000]}).encode()
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "radar-ia-indexnow"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"IndexNow : {len(urls)} URL signalées (HTTP {r.status}).")
    except urllib.error.HTTPError as e:  # 202 = accepté ; 403 clé non vérifiée ; 422 URL hors hôte ; 429 trop de requêtes
        print(f"IndexNow : HTTP {e.code} {e.read().decode(errors='replace')[:300]}", file=sys.stderr)
    except urllib.error.URLError as e:
        print(f"IndexNow : réseau indisponible ({e.reason}).", file=sys.stderr)

if __name__ == "__main__":
    main()
