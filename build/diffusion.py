#!/usr/bin/env python3
"""Publie les nouveaux articles de Radar IA sur Bluesky et Mastodon après un déploiement.

Activé seulement si les secrets du dépôt existent (Settings → Secrets and variables → Actions) :
  BLUESKY_HANDLE + BLUESKY_APP_PASSWORD      (mot de passe d'application Bluesky, pas le mot de passe du compte)
  MASTODON_URL (ex. https://mastodon.social) + MASTODON_TOKEN (jeton d'application, droit write:statuses)
Anti-doublon : avant de publier, le script relit les derniers messages du compte et saute les URL déjà présentes.

Usage : python3 build/diffusion.py --dist dist [--heures 30] [--max 3] [--essai]
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, sys, urllib.error, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

UA = {"User-Agent": "radar-ia-diffusion", "Content-Type": "application/json"}
TAGS_MASTODON = "#IA #OpenSource #HuggingFace #LLM"

def http(method, url, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode() or "{}")

def clip(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"

def nouveaux(dist: Path, heures: int, maxi: int) -> list[dict]:
    feed = json.loads((dist / "feed.json").read_text(encoding="utf-8"))
    limite = datetime.now(timezone.utc) - timedelta(hours=heures)
    out = []
    for it in feed.get("items") or []:
        try:
            d = datetime.fromisoformat(it.get("date_published", ""))
        except ValueError:
            continue
        if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
        if d >= limite and it.get("url"):
            out.append(it)
    return out[:maxi]

# ------------------------------------------------------------------ Bluesky (AT Protocol)

def bluesky(articles, essai):
    handle, pw = os.environ.get("BLUESKY_HANDLE"), os.environ.get("BLUESKY_APP_PASSWORD")
    if not (handle and pw):
        print("Bluesky : non configuré."); return
    pds = "https://bsky.social/xrpc/"
    s = http("POST", pds + "com.atproto.server.createSession", {"identifier": handle, "password": pw})
    auth = {"Authorization": "Bearer " + s["accessJwt"]}
    fil = http("GET", pds + f"app.bsky.feed.getAuthorFeed?actor={s['did']}&limit=50", headers=auth)
    deja = json.dumps(fil)
    for a in articles:
        if a["url"] in deja:
            print(f"Bluesky : déjà publié — {a['title']}"); continue
        tete = clip(a["title"], 120)
        texte = f"{tete}\n\n{clip(a.get('summary') or '', 280 - len(tete) - 4)}"  # limite Bluesky : 300 caractères ; le lien va dans la carte
        record = {"$type": "app.bsky.feed.post", "text": texte, "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                  "langs": ["fr"], "embed": {"$type": "app.bsky.embed.external",
                  "external": {"uri": a["url"], "title": clip(a["title"], 200), "description": clip(a.get("summary") or "", 280)}}}
        if essai:
            print("Bluesky (essai) :", texte.replace("\n", " ")); continue
        http("POST", pds + "com.atproto.repo.createRecord", {"repo": s["did"], "collection": "app.bsky.feed.post", "record": record}, auth)
        print(f"Bluesky : publié — {a['title']}")

# ------------------------------------------------------------------ Mastodon

def mastodon(articles, essai):
    base, tok = (os.environ.get("MASTODON_URL") or "").rstrip("/"), os.environ.get("MASTODON_TOKEN")
    if not (base.startswith("https://") and tok):
        print("Mastodon : non configuré."); return
    auth = {"Authorization": "Bearer " + tok}
    moi = http("GET", base + "/api/v1/accounts/verify_credentials", headers=auth)
    deja = json.dumps(http("GET", base + f"/api/v1/accounts/{moi['id']}/statuses?limit=40", headers=auth))
    for a in articles:
        if a["url"] in deja:
            print(f"Mastodon : déjà publié — {a['title']}"); continue
        texte = f"{clip(a['title'], 150)}\n\n{clip(a.get('summary') or '', 230)}\n\n{a['url']}\n\n{TAGS_MASTODON}"
        if essai:
            print("Mastodon (essai) :", texte.replace("\n", " ")); continue
        http("POST", base + "/api/v1/statuses", {"status": texte, "language": "fr", "visibility": "public"},
             {**auth, "Idempotency-Key": hashlib.sha1(a["url"].encode()).hexdigest()})
        print(f"Mastodon : publié — {a['title']}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", required=True); ap.add_argument("--heures", type=int, default=30); ap.add_argument("--max", type=int, default=3)
    ap.add_argument("--essai", action="store_true", help="affiche sans publier")
    a = ap.parse_args()
    arts = nouveaux(Path(a.dist), a.heures, a.max)
    if not arts:
        print("Diffusion : aucun article de moins de", a.heures, "h."); return
    for fn in (bluesky, mastodon):
        try:
            fn(arts, a.essai)
        except (urllib.error.URLError, KeyError, ValueError) as e:  # un réseau en panne ne bloque pas l'autre
            print(f"{fn.__name__} : échec ({e})", file=sys.stderr)

if __name__ == "__main__":
    main()
