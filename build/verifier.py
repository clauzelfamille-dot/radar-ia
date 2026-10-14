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
    titres: dict[str, list] = {}; descs: dict[str, list] = {}
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
        if rel != "404.html":  # référencement : titre et description présents et uniques
            tt = re.search(r"<title>(.*?)</title>", h, re.S); dd = re.search(r'<meta name="description" content="([^"]*)"', h)
            if not tt or not tt.group(1).strip(): erreurs.append(f"{rel} : <title> absent")
            else: titres.setdefault(html.unescape(tt.group(1)).strip(), []).append(rel)
            if not dd or len(dd.group(1).strip()) < 50: alertes.append(f"{rel} : meta description absente ou trop courte")
            else: descs.setdefault(html.unescape(dd.group(1)).strip(), []).append(rel)
        t = re.search(r"<title>(.*?)</title>", h, re.S)
        if t and html.unescape(t.group(1)).rstrip().endswith("…") and not rel.startswith("modeles/"):  # noms Hugging Face parfois > 70 car.
            alertes.append(f"{rel} : titre tronqué")
        if t and len(html.unescape(t.group(1))) > 70 and not rel.startswith(("articles/", "editions/")):  # titres éditoriaux gardés entiers
            alertes.append(f"{rel} : titre de {len(html.unescape(t.group(1)))} caractères")
    for t_, rs in titres.items():
        if len(rs) > 1: alertes.append(f"titre en double ({len(rs)} pages) : {t_[:60]} — {', '.join(rs[:3])}")
    for d_, rs in descs.items():
        if len(rs) > 1: alertes.append(f"description en double ({len(rs)} pages) : {d_[:60]} — {', '.join(rs[:3])}")
    for n in ["sitemap.xml", "feed.xml"] + [f.relative_to(dist).as_posix() for f in sorted((dist / "feeds").glob("*.xml"))]:
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
