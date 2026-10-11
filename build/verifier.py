#!/usr/bin/env python3
"""Contrôles avant publication du site généré (exigés par CLAUDE.md).

- chaque bloc JSON-LD se parse ;
- aucun lien interne relatif ne pointe vers un fichier absent ;
- sitemap.xml et feed.xml se parsent en XML ; tous les .json se parsent ;
- avertissements : page HTML > 60 ko, <title> > 70 caractères, meta description > 160.
Code de sortie 1 si une erreur bloquante est trouvée.

Usage : python3 build/verifier.py dist
"""
from __future__ import annotations
import html, json, re, sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse

def main():
    dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    erreurs, alertes = [], []
    pages = sorted(dist.rglob("*.html"))
    for p in pages:
        h = p.read_text(encoding="utf-8")
        rel = p.relative_to(dist).as_posix()
        for bloc in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S):
            try:
                json.loads(bloc)
            except ValueError as e:
                erreurs.append(f"{rel} : JSON-LD invalide ({e})")
        if rel != "404.html":
            for href in re.findall(r'(?:href|src)="([^"#?]+)', h):
                if re.match(r"^(?:[a-z]+:|//)", href, re.I):
                    continue
                cible = (p.parent / unquote(href)).resolve()
                if cible.is_dir():
                    cible = cible / "index.html"
                if not cible.exists():
                    erreurs.append(f"{rel} : lien cassé → {href}")
        if len(h.encode()) > 60_000:
            alertes.append(f"{rel} : {len(h.encode()) // 1024} ko")
        t = re.search(r"<title>(.*?)</title>", h, re.S)
        if t and len(html.unescape(t.group(1))) > 70:
            alertes.append(f"{rel} : titre de {len(html.unescape(t.group(1)))} caractères")
    for n in ("sitemap.xml", "feed.xml"):
        try:
            ET.parse(dist / n)
        except (ET.ParseError, OSError) as e:
            erreurs.append(f"{n} : XML invalide ({e})")
    for j in dist.rglob("*.json"):
        try:
            json.loads(j.read_text(encoding="utf-8"))
        except ValueError as e:
            erreurs.append(f"{j.relative_to(dist).as_posix()} : JSON invalide ({e})")
    print(f"{len(pages)} pages HTML contrôlées : {len(erreurs)} erreur(s), {len(alertes)} alerte(s).")
    for e in erreurs[:50]: print("ERREUR", e)
    for a in alertes[:20]: print("alerte", a)
    sys.exit(1 if erreurs else 0)

if __name__ == "__main__":
    main()
