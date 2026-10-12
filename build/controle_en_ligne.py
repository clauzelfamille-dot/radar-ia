#!/usr/bin/env python3
"""Contrôle du site publié après un déploiement GitHub Pages.

Vérifie que les pages clés et un échantillon du sitemap répondent (HTTP 200), et que llms.txt en ligne annonce la même
dernière édition que le site généré. Réessaie quelques fois (le CDN met parfois une minute à se mettre à jour).
Code de sortie 1 si un problème persiste : le workflow passe alors en rouge.

Usage : python3 build/controle_en_ligne.py --dist dist --site-url https://exemple.org/radar-ia/
"""
from __future__ import annotations
import argparse, random, re, sys, time, urllib.error, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

CLES = ["", "llms.txt", "sitemap.xml", "feed.xml", "robots.txt", "classements.html", "modeles.html", "guides.html", "api/v1/index.json"]

def lire(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url + ("&" if "?" in url else "?") + f"_={int(time.time())}", headers={"User-Agent": "radar-ia-controle"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (urllib.error.URLError, TimeoutError) as e:
        return 0, str(e)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", required=True); ap.add_argument("--site-url", required=True)
    ap.add_argument("--essais", type=int, default=6); ap.add_argument("--pause", type=int, default=20)
    a = ap.parse_args()
    base, dist = a.site_url.rstrip("/") + "/", Path(a.dist)
    attendu = re.search(r"Dernière édition : ([^.]+)\.", (dist / "llms.txt").read_text(encoding="utf-8"))
    attendu = attendu.group(1) if attendu else None
    locs = [e.text for e in ET.parse(dist / "sitemap.xml").iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc") if e.text]
    echantillon = random.Random(len(locs)).sample(locs, min(10, len(locs)))
    urls = [base + c for c in CLES] + echantillon
    problemes: list[str] = []
    for essai in range(1, a.essais + 1):
        problemes = []
        for u in urls:
            code, corps = lire(u)
            if code != 200:
                problemes.append(f"{u} → HTTP {code}")
            elif u.endswith("llms.txt") and attendu and attendu not in corps:
                problemes.append(f"llms.txt en ligne n'annonce pas encore l'édition du {attendu}")
        if not problemes:
            print(f"Contrôle en ligne : {len(urls)} URL en HTTP 200, édition du {attendu} publiée (essai {essai}).")
            return
        if essai < a.essais:
            time.sleep(a.pause)
    print("Contrôle en ligne : ÉCHEC", *problemes, sep="\n  ", file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    main()
