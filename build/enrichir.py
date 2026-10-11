#!/usr/bin/env python3
"""Vérifie les faits de chaque élément suivi auprès de l'API publique Hugging Face.

Pour chaque data/items/<id>.json, écrit data/hf/<id>.json : licence (nom exact et lien), dates de création et de mise à
jour, likes, téléchargements (30 jours), tâche, bibliothèque, langues déclarées, nombre de paramètres, formats (GGUF,
safetensors…), longueur de contexte, modèle de base et relation (quantification, fine-tune…), accès restreint, articles
arXiv. Ces faits priment sur les valeurs saisies par les agents. En cas d'échec réseau, l'ancien fichier est conservé.

Usage : python3 build/enrichir.py --data data [--workers 4]
"""
from __future__ import annotations
import argparse, json, os, sys, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

API = {"model": "models", "dataset": "datasets", "space": "spaces"}
PAGE = {"model": "", "dataset": "datasets/", "space": "spaces/"}
FORMATS = {"gguf": "GGUF", "safetensors": "safetensors", "onnx": "ONNX", "mlx": "MLX", "gptq": "GPTQ", "awq": "AWQ", "exl2": "EXL2"}

def liste(v) -> list:
    if v is None: return []
    return [str(x) for x in (v if isinstance(v, list) else [v]) if x not in (None, "")]

def faits(it: dict, d: dict, maintenant: str) -> dict:
    t = it.get("type") if it.get("type") in API else "model"
    page = "https://huggingface.co/" + PAGE[t] + it["hfId"]
    tags = [str(x) for x in d.get("tags") or []]
    card = d.get("cardData") or {}
    lic = card.get("license") or next((x.split(":", 1)[1] for x in tags if x.startswith("license:")), None)
    if isinstance(lic, list): lic = lic[0] if lic else None
    lien = card.get("license_link")
    if lic == "other" and card.get("license_name"):
        lic = card["license_name"]
    if lien and not str(lien).startswith("http"):
        lien = f"{page}/blob/main/{str(lien).lstrip('./')}"
    langues = liste(card.get("language")) or [x.split(":", 1)[1] for x in tags if x.startswith("language:")]
    bases, vus = [], set()
    for x in tags:  # « base_model:quantized:org/nom » ou « base_model:org/nom »
        if not x.startswith("base_model:"): continue
        parts = x.split(":")
        rel, bid = (parts[1], ":".join(parts[2:])) if len(parts) > 2 else (None, parts[1])
        if bid in vus and rel is None: continue
        bases = [b for b in bases if not (b["id"] == bid and b["relation"] is None)]
        bases.append({"id": bid, "relation": rel}); vus.add(bid)
    st, gg = d.get("safetensors") or {}, d.get("gguf") or {}
    out = {
        "hfId": it["hfId"], "type": t, "url": page, "verifieLe": maintenant,
        "creeLe": (d.get("createdAt") or "")[:10] or None, "majLe": (d.get("lastModified") or "")[:10] or None,
        "likes": d.get("likes"), "downloads": d.get("downloads"),
        "licence": lic, "licenceLien": lien if lien and str(lien).startswith("http") else None,
        "tache": d.get("pipeline_tag") or ", ".join(liste(card.get("task_categories"))) or d.get("sdk"),
        "bibliotheque": d.get("library_name"),
        "langues": [l.lower() for l in langues],
        "parametres": st.get("total") or gg.get("total"),
        "contexte": gg.get("context_length"),
        "formats": sorted({v for k, v in FORMATS.items() if k in tags or (k == "gguf" and gg)}),
        "modeleBase": bases,
        "acces": "sur demande" if d.get("gated") else "libre",
        "arxiv": sorted({x.split(":", 1)[1] for x in tags if x.startswith("arxiv:")}),
        "volumetrie": ", ".join(liste(card.get("size_categories"))) or None,
    }
    return {k: v for k, v in out.items() if v not in (None, [], "")}

def un(item_path: Path, out_dir: Path, maintenant: str, token: str | None) -> str:
    it = json.loads(item_path.read_text(encoding="utf-8"))
    if not it.get("hfId"): return f"ignoré {item_path.stem} (pas de hfId)"
    t = it.get("type") if it.get("type") in API else "model"
    req = urllib.request.Request(f"https://huggingface.co/api/{API[t]}/{it['hfId']}",
                                 headers={"User-Agent": "radar-ia-verification", **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code} {it['hfId']}"
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return f"échec {it['hfId']} ({e})"
    (out_dir / f"{item_path.stem}.json").write_text(json.dumps(faits(it, d, maintenant), ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return "ok"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    items, out_dir = Path(a.data) / "items", Path(a.data) / "hf"
    out_dir.mkdir(parents=True, exist_ok=True)
    maintenant = datetime.now(timezone.utc).isoformat(timespec="minutes")
    token = os.environ.get("HF_TOKEN")  # facultatif : lecture publique sans jeton
    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        res = list(ex.map(lambda p: un(p, out_dir, maintenant, token), sorted(items.glob("*.json"))))
    for f in out_dir.glob("*.json"):  # élément retiré du suivi : sa vérification aussi
        if not (items / f.name).exists(): f.unlink()
    ok = res.count("ok")
    print(f"Vérification Hugging Face : {ok}/{len(res)} éléments à jour.")
    for r in res:
        if r != "ok": print(" ", r, file=sys.stderr)

if __name__ == "__main__":
    main()
