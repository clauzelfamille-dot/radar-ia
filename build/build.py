#!/usr/bin/env python3
"""Radar IA — générateur de site statique optimisé SEO + GEO.

Entrée : un dossier de données exporté de la base (un sous-dossier par collection, un JSON par document) :
  <data>/items/*.json  articles/*.json  editions/*.json  classements/*.json  domaines/*.json
Sortie : un site statique complet (HTML sans JavaScript, .md jumeaux, JSON-LD, sitemap, RSS, JSON Feed,
llms.txt, llms-full.txt, API JSON + OpenAPI, robots.txt).

Usage : python3 build.py --data DATA --out DIST [--site-url https://exemple.org/radar-ia/] [--config config/site.json]

La configuration (config/site.json, facultative) active les leviers d'audience et de revenus : vérification des moteurs,
mesure d'audience sans cookie, newsletter, sponsor, dons, affiliation, IndexNow, réseaux. Champ vide = bloc masqué.
"""
from __future__ import annotations
import argparse, html, json, math, os, re, shutil, sys, unicodedata
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

RACINE_DEPOT = Path(__file__).resolve().parent.parent

SITE_NAME = "Radar IA"
SITE_TAGLINE = "Le quotidien des modèles IA ouverts : tendances Hugging Face, scores et analyses en français"
SITE_DESC = ("Chaque matin, les modèles, datasets et Spaces qui comptent sur Hugging Face : classements avec Score Radar, "
             "fiches techniques et articles pour faire tourner l'IA en local, traiter des documents, bâtir des agents.")
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/deed.fr"
DOMAIN_ORDER_FALLBACK = ["local", "documents", "agents", "audio", "code", "multilingue", "image-video", "donnees", "tendances"]
PERIODES = [("jour", "Aujourd'hui"), ("7j", "7 jours"), ("30j", "30 jours"), ("90j", "3 mois")]
TYPE_LABEL = {"model": "Modèle", "dataset": "Dataset", "space": "Space", "paper": "Paper"}
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]

# ------------------------------------------------------------------ utilitaires

def esc(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)

def load_dir(p: Path) -> dict:
    out = {}
    if p.is_dir():
        for f in sorted(p.glob("*.json")):
            try:
                out[f.stem] = json.loads(f.read_text(encoding="utf-8"))
            except Exception as e:  # données partagées = non fiables
                print(f"ignoré {f}: {e}", file=sys.stderr)
    return out

def fmt_n(n) -> str:
    if n is None:
        return "—"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "—"
    if n >= 1e6:
        return f"{n/1e6:.1f}".replace(".", ",").replace(",0", "") + " M"
    if n >= 1e3:
        return f"{n/1e3:.1f}".replace(".", ",").replace(",0", "") + " k"
    return str(int(n))

def fmt_params(n) -> str:
    """Nombre de paramètres lisible : 27,3 B (milliards), 287 M (millions)."""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return ""
    if n >= 1e9: return f"{n/1e9:.1f}".replace(".", ",").replace(",0", "") + " B"
    if n >= 1e6: return f"{n/1e6:.0f} M"
    return f"{n:.0f}" if n else ""

LANGUES = {"fr": "français", "en": "anglais", "de": "allemand", "es": "espagnol", "it": "italien", "pt": "portugais", "nl": "néerlandais",
           "pl": "polonais", "zh": "chinois", "ja": "japonais", "ko": "coréen", "ru": "russe", "ar": "arabe", "tr": "turc", "hi": "hindi",
           "vi": "vietnamien", "uk": "ukrainien", "sv": "suédois", "cs": "tchèque", "multilingual": "multilingue (langues non détaillées)"}
TACHES = {  # étiquettes « pipeline » de Hugging Face → (slug, nom français)
    "text-generation": ("generation-de-texte", "Génération de texte (LLM)"),
    "image-text-to-text": ("vision-langage", "Vision-langage (image et texte vers texte)"),
    "text-to-image": ("texte-vers-image", "Génération d'images"),
    "automatic-speech-recognition": ("transcription-audio", "Transcription audio (ASR)"),
    "text-classification": ("classification-de-texte", "Classification de texte"),
    "feature-extraction": ("embeddings", "Embeddings (recherche sémantique, RAG)"),
    "sentence-similarity": ("similarite-de-phrases", "Similarité de phrases"),
    "text-to-speech": ("synthese-vocale", "Synthèse vocale"),
    "image-to-video": ("image-vers-video", "Génération de vidéo à partir d'images"),
    "token-classification": ("extraction-d-entites", "Extraction d'entités (NER)"),
    "image-to-text": ("image-vers-texte", "Image vers texte (OCR, légendes)"),
    "translation": ("traduction", "Traduction"),
}
RELATIONS = {"quantized": "quantification", "finetune": "fine-tune", "adapter": "adaptateur", "merge": "fusion", None: "dérivé"}
# Résumés de licences connues. Toute autre licence reçoit le texte prudent LICENCE_AUTRE (pas d'interprétation inventée).
LICENCES = {
    "apache-2.0": "Licence permissive : usage, modification et redistribution autorisés, y compris commercialement, en conservant la licence et les mentions ; elle comprend une licence sur les brevets des contributeurs.",
    "mit": "Licence permissive : usage, y compris commercial, modification et redistribution autorisés, à condition de conserver la mention de copyright et la licence.",
    "cc-by-4.0": "Réutilisation libre, y compris commerciale, à condition de citer l'auteur et d'indiquer les modifications.",
    "cc-by-sa-4.0": "Réutilisation libre, y compris commerciale, avec citation de l'auteur ; les œuvres dérivées doivent être partagées sous la même licence.",
    "cc-by-nc-4.0": "Réutilisation libre avec citation de l'auteur, mais usage commercial interdit.",
}
LICENCE_AUTRE = "Licence propre à l'éditeur : ses conditions (usage commercial, seuils d'utilisateurs, restrictions d'usage) sont à lire avant tout déploiement en entreprise."
LICENCE_AUCUNE = "Aucune licence déclarée sur Hugging Face : sans autorisation explicite de l'auteur, la réutilisation n'est pas garantie."

GLOSSAIRE = [
    ("poids-ouverts", "Poids ouverts (open weights)", "Modèle dont les paramètres entraînés sont téléchargeables, ce qui permet de l'exécuter chez soi. Cela ne dit rien de la licence : certains poids ouverts interdisent l'usage commercial."),
    ("parametres", "Paramètres", "Nombres appris pendant l'entraînement ; leur quantité (en milliards, « B ») donne l'ordre de grandeur de la taille du modèle et de la mémoire nécessaire."),
    ("quantification", "Quantification", "Réduction de la précision des paramètres (par exemple de 16 bits à 4 ou 8 bits) pour diminuer la mémoire et accélérer l'exécution, au prix d'une légère perte de qualité."),
    ("gguf", "GGUF", "Format de fichier de llama.cpp, repris par Ollama et LM Studio, qui regroupe les poids quantifiés et les métadonnées d'un modèle en un seul fichier exécutable sur un PC."),
    ("safetensors", "Safetensors", "Format de stockage des poids conçu pour être chargé rapidement et sans exécuter de code, utilisé par défaut par la bibliothèque transformers."),
    ("mlx", "MLX", "Bibliothèque d'Apple pour exécuter des modèles sur les puces Apple Silicon ; un dépôt MLX contient des poids préparés pour elle."),
    ("fine-tune", "Fine-tune (affinage)", "Entraînement complémentaire d'un modèle existant sur des données ciblées, pour le spécialiser sur une tâche, un style ou une langue."),
    ("adaptateur", "Adaptateur (LoRA)", "Petit jeu de paramètres supplémentaires entraîné par-dessus un modèle de base, qu'on charge avec lui ; LoRA est la méthode la plus répandue."),
    ("fusion", "Fusion (merge)", "Modèle obtenu en combinant les poids de plusieurs modèles de même architecture, sans nouvel entraînement complet."),
    ("modele-de-base", "Modèle de base", "Modèle dont un autre est dérivé (quantification, fine-tune, adaptateur, fusion). Hugging Face l'indique dans les métadonnées base_model."),
    ("moe", "Mixture of Experts (MoE)", "Architecture où seule une partie des paramètres (les « experts » choisis) travaille pour chaque mot : le modèle est gros sur le disque mais moins coûteux à exécuter qu'un modèle dense de même taille."),
    ("contexte", "Fenêtre de contexte", "Quantité maximale de texte, comptée en tokens, que le modèle peut prendre en compte en une fois (consigne, documents et réponse compris)."),
    ("token", "Token", "Unité de texte manipulée par un modèle : un mot court, un morceau de mot ou un signe."),
    ("acces-restreint", "Accès restreint (gated)", "Dépôt Hugging Face dont le téléchargement exige d'accepter des conditions ou d'être approuvé par l'éditeur."),
    ("licence-permissive", "Licence permissive", "Licence (Apache 2.0, MIT…) qui autorise l'usage, y compris commercial, la modification et la redistribution, sous réserve de conserver les mentions."),
    ("embedding", "Embedding (plongement)", "Vecteur de nombres qui représente le sens d'un texte ; sert à la recherche sémantique et au RAG."),
    ("rag", "RAG", "Retrieval-Augmented Generation : le modèle répond en s'appuyant sur des passages retrouvés dans vos documents au lieu de sa seule mémoire."),
    ("ocr", "OCR", "Reconnaissance optique de caractères : transformation d'une image ou d'un PDF scanné en texte exploitable."),
    ("asr", "Transcription (ASR)", "Reconnaissance automatique de la parole : conversion d'un enregistrement audio en texte."),
    ("diarisation", "Diarisation", "Repérage de « qui parle quand » dans un enregistrement, souvent combiné à la transcription."),
    ("vision-langage", "Modèle vision-langage", "Modèle qui prend en entrée des images et du texte, par exemple pour décrire une image ou lire un document."),
    ("appel-outils", "Appel d'outils (tool calling)", "Capacité d'un modèle à produire un appel structuré vers une fonction ou une API, base des agents IA."),
    ("space", "Space", "Application de démonstration hébergée sur Hugging Face, souvent faite avec Gradio ou Streamlit."),
    ("dataset", "Dataset", "Jeu de données publié sur Hugging Face pour entraîner ou évaluer des modèles."),
    ("score-radar", "Score Radar", "Note de 0 à 100 calculée par Radar IA : 40 % popularité, 30 % diffusion, 20 % fraîcheur, 10 % pertinence pour l'IA pratique (voir la page Méthode)."),
]

def langue(code: str) -> str:
    return LANGUES.get(code, code)

def d_long(s: str | None) -> str:
    if not s:
        return "—"
    try:
        d = date.fromisoformat(s[:10])
    except ValueError:
        return esc(s)
    return f"{d.day} {MOIS[d.month-1]} {d.year}"

def d_short(s: str | None) -> str:
    if not s:
        return "—"
    try:
        d = date.fromisoformat(s[:10]); return d.strftime("%d/%m/%Y")
    except ValueError:
        return esc(s)

def iso_dt(s: str | None) -> str:
    if not s:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    if len(s) == 10:
        return s + "T07:00:00+02:00"
    return s

def rfc822(s: str | None) -> str:
    try:
        dt = datetime.fromisoformat(iso_dt(s))
    except ValueError:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S %z")

def slugify(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", s).strip("-.").lower()
    return s[:120] or "x"

def titre_court(*variantes: str, n: int = 70) -> str:
    """Première variante de titre qui tient en n caractères (sinon la plus courte)."""
    for v in variantes:
        if v and len(v) <= n: return v
    return min((v for v in variantes if v), key=len)

def clip(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"

def safe_url(u: str | None) -> str:
    u = str(u or "")
    return u if re.match(r"^https?://", u, re.I) else "#"

# ------------------------------------------------------------------ configuration (leviers d'audience et de revenus)

CONFIG_DEFAUT = {"depot": "", "verification": {}, "mesure": {}, "newsletter": {}, "soutien": [], "sponsor": {}, "contact": {},
                 "offres": [], "affiliation": {}, "indexnow": {}, "reseaux": []}

def load_config(p: Path | None) -> dict:
    cfg = json.loads(json.dumps(CONFIG_DEFAUT))
    if p and p.is_file():
        try:
            cfg.update({k: v for k, v in json.loads(p.read_text(encoding="utf-8")).items() if not k.startswith("_")})
        except Exception as e:  # une configuration illisible ne doit pas bloquer la publication
            print(f"configuration ignorée {p}: {e}", file=sys.stderr)
    return cfg

def has_url(u) -> bool:
    return safe_url(u) != "#"

# ------------------------------------------------------------------ HTML d'article : nettoyage + Markdown

OK_TAGS = {"p", "h2", "h3", "h4", "ul", "ol", "li", "a", "strong", "em", "b", "i", "table", "thead", "tbody", "tr", "th",
           "td", "blockquote", "code", "pre", "br", "hr"}

class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.out = []; self.stack = []
    def handle_starttag(self, tag, attrs):
        if tag not in OK_TAGS:
            return
        if tag == "a":
            href = safe_url(dict(attrs).get("href"))
            self.out.append(f'<a href="{esc(href)}" rel="noopener">')
        elif tag in ("br", "hr"):
            self.out.append(f"<{tag}>"); return
        else:
            self.out.append(f"<{tag}>")
        self.stack.append(tag)
    def handle_endtag(self, tag):
        if tag in OK_TAGS and tag not in ("br", "hr") and tag in self.stack:
            while self.stack:
                t = self.stack.pop(); self.out.append(f"</{t}>")
                if t == tag:
                    break
    def handle_data(self, data):
        self.out.append(esc(data))
    def result(self):
        while self.stack:
            self.out.append(f"</{self.stack.pop()}>")
        return "".join(self.out)

def sanitize(h: str) -> str:
    p = _Sanitizer(); p.feed(h or ""); p.close(); return p.result()

class _ToMd(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.out = []; self.href = None; self.list = []; self.row = []; self.cell = None; self.rows = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("h2", "h3", "h4"): self.out.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "p": self.out.append("\n\n")
        elif tag in ("ul", "ol"): self.list.append([tag, 0]); self.out.append("\n")
        elif tag == "li":
            if self.list:
                self.list[-1][1] += 1
                mark = f"{self.list[-1][1]}." if self.list[-1][0] == "ol" else "-"
            else:
                mark = "-"
            self.out.append("\n" + "  " * (len(self.list) - 1) + mark + " ")
        elif tag in ("strong", "b"): self.out.append("**")
        elif tag in ("em", "i"): self.out.append("*")
        elif tag == "code": self.out.append("`")
        elif tag == "a": self.href = a.get("href"); self.out.append("[")
        elif tag == "blockquote": self.out.append("\n\n> ")
        elif tag == "tr": self.row = []
        elif tag in ("td", "th"): self.cell = []
        elif tag == "table": self.rows = []
        elif tag == "br": self.out.append("  \n")
    def handle_endtag(self, tag):
        if tag in ("strong", "b"): self.out.append("**")
        elif tag in ("em", "i"): self.out.append("*")
        elif tag == "code": self.out.append("`")
        elif tag == "a": self.out.append(f"]({self.href or ''})"); self.href = None
        elif tag in ("ul", "ol") and self.list: self.list.pop(); self.out.append("\n")
        elif tag in ("td", "th") and self.cell is not None: self.row.append("".join(self.cell).strip().replace("|", "\\|")); self.cell = None
        elif tag == "tr": self.rows.append(self.row)
        elif tag == "table" and self.rows:
            w = max(len(r) for r in self.rows)
            lines = []
            for i, r in enumerate(self.rows):
                r = r + [""] * (w - len(r)); lines.append("| " + " | ".join(r) + " |")
                if i == 0: lines.append("|" + "---|" * w)
            self.out.append("\n\n" + "\n".join(lines) + "\n")
    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)
        else: self.out.append(re.sub(r"\s+", " ", data))
    def result(self):
        return re.sub(r"\n{3,}", "\n\n", "".join(self.out)).strip()

def html_to_md(h: str) -> str:
    p = _ToMd(); p.feed(h or ""); p.close(); return p.result()

def word_count(h: str) -> int:
    return len(re.sub(r"<[^>]+>", " ", h or "").split())

# ------------------------------------------------------------------ modèle de données

class Site:
    def __init__(self, data: Path, site_url: str, cfg: dict | None = None, static: Path | None = None):
        self.url = site_url.rstrip("/") + "/" if site_url else ""
        self.cfg = cfg or load_config(None)
        self.static = static if static and static.is_dir() else None
        self.og = bool(self.static and (self.static / "og.png").is_file())
        self.items = load_dir(data / "items")
        self.articles = {k: v for k, v in load_dir(data / "articles").items() if v.get("statut") == "publie"}
        self.editions = load_dir(data / "editions")
        self.classements = load_dir(data / "classements")
        self.hf = load_dir(data / "hf")  # faits vérifiés sur l'API Hugging Face (build/enrichir.py), prioritaires
        doms = load_dir(data / "domaines")
        if not doms:
            doms = {d: {"nom": d, "description": "", "ordre": i} for i, d in enumerate(DOMAIN_ORDER_FALLBACK)}
        self.domaines = dict(sorted(doms.items(), key=lambda kv: kv[1].get("ordre", 99)))
        for k, it in self.items.items():
            it["_id"] = k; it["_slug"] = slugify(k)
        for k, a in self.articles.items():
            a["_id"] = k; a["_slug"] = slugify(k)
        self.art_sorted = sorted(self.articles.values(), key=lambda a: (a.get("date", ""), a.get("publieLe", "")), reverse=True)
        self.ed_sorted = sorted(self.editions.values(), key=lambda e: e.get("date", ""), reverse=True)
        self.today = self.ed_sorted[0]["date"] if self.ed_sorted else date.today().isoformat()
        self.built_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def abs(self, path: str) -> str:
        return (self.url + path) if self.url else path

    def item_page(self, it) -> str: return f"modeles/{it['_slug']}.html"
    def art_page(self, a) -> str: return f"articles/{a['_slug']}.html"
    def ed_page(self, e) -> str: return f"editions/{e['date']}.html"
    def dom_page(self, d) -> str: return f"domaines/{d}.html"
    def dom_name(self, d) -> str: return self.domaines.get(d, {}).get("nom", d)

    def hf_url(self, it) -> str:
        if it.get("url"): return safe_url(it["url"])
        pre = {"dataset": "datasets/", "space": "spaces/", "paper": "papers/"}.get(it.get("type"), "")
        return "https://huggingface.co/" + pre + it.get("hfId", "")

    def items_in(self, dom):
        return sorted([i for i in self.items.values() if dom in (i.get("domaines") or [])], key=lambda i: -(i.get("score") or 0))

    # --- faits vérifiés : la valeur de l'API Hugging Face prime sur la saisie des agents
    def v(self, it) -> dict: return self.hf.get(it.get("_id")) or {}
    def lic(self, it): return self.v(it).get("licence") or it.get("licence")
    def org(self, it):
        """Éditeur vérifié : nom officiel de l'organisation, identifiant pour un compte personnel, sinon saisie de l'agent."""
        v, acc = self.v(it), (it.get("hfId") or "").split("/")[0]
        if v.get("compteNom"): return v["compteNom"].strip()
        if v.get("compteType") == "utilisateur": return acc
        return it.get("org") or acc
    def cree(self, it): return self.v(it).get("creeLe") or it.get("creeLe")
    def taille(self, it): return fmt_params(self.v(it).get("parametres")) or it.get("taille")
    def by_hf(self) -> dict: return {i.get("hfId"): i for i in self.items.values() if i.get("hfId")}

    def familles(self) -> dict:
        """Modèle de base → dérivés suivis, d'après les tags base_model de Hugging Face (calculé une fois)."""
        if getattr(self, "_fam", None) is None:
            self._fam = self._calc_familles()
        return self._fam

    def _calc_familles(self) -> dict:
        fam: dict[str, list] = {}
        for it in self.items.values():
            for b in self.v(it).get("modeleBase") or []:
                fam.setdefault(b["id"], []).append((it, b.get("relation")))
        suivis = self.by_hf()
        return {b: sorted(d, key=lambda x: -(x[0].get("score") or 0)) for b, d in sorted(fam.items())
                if len(d) >= 2 or (b in suivis and d)}

    def editeurs(self) -> dict:
        """Compte Hugging Face → éléments suivis (triés par score)."""
        ed: dict[str, list] = {}
        for it in self.items.values():
            acc = (it.get("hfId") or "").split("/")[0]
            if acc: ed.setdefault(acc, []).append(it)
        return {k: sorted(v, key=lambda i: -(i.get("score") or 0)) for k, v in sorted(ed.items(), key=lambda kv: kv[0].lower())}

    def ed_page_url(self, acc) -> str: return f"editeurs/{slugify(acc)}.html"
    def has_ed_page(self, acc) -> bool: return len(self.editeurs().get(acc, [])) >= 2

    def comparatifs(self) -> list:
        """Paires (a, b, domaine) : les 3 modèles les mieux classés de chaque domaine, comparés deux à deux, sans doublon."""
        if getattr(self, "_cmp", None) is None:
            vus, out = set(), []
            for dk in self.domaines:
                top = [i for i in self.items_in(dk) if i.get("type") == "model" and "uncensored" not in (i.get("hfId") or "").lower()][:3]
                for x in range(len(top)):
                    for y in range(x + 1, len(top)):
                        a, b = top[x], top[y]
                        k = tuple(sorted((a["_id"], b["_id"])))
                        if k not in vus:
                            vus.add(k); out.append((a, b, dk))
            self._cmp = out
        return self._cmp

    def cmp_page(self, a, b) -> str: return f"comparer/{slugify(a['_id'])}-vs-{slugify(b['_id'])}.html"

    def fam_page(self, base_id) -> str: return f"familles/{slugify(base_id.replace('/', '__'))}.html"

# ------------------------------------------------------------------ gabarit

CSS = r"""
/* Charte Radar IA v2 : « instrument de bord éditorial ». Voir CHARTE.md. */
:root{--bg:#f6f4ee;--bg2:#fffefa;--bg3:#ece8de;--fg:#12161a;--fg2:#4a525c;--fg3:#5f6770;--line:#ddd8cc;--rule:#12161a;
--acc:#0a7155;--acc-ink:#065240;--soft:#dcefe6;--acc2:#a8530a;--star:#a8530a;--ring:#d9d4c7;--band:#12161a;--on-band:#eef1ec;
--d-local:#2463d6;--d-documents:#a8530a;--d-agents:#7a3fd6;--d-audio:#c42a72;--d-code:#08799a;--d-multilingue:#178a3e;
--d-image-video:#d2501a;--d-donnees:#5b7a12;--d-tendances:#5f6b78;
--serif:"Iowan Old Style","Charter","Bitstream Charter","Sitka Text",Cambria,Georgia,serif;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
--mono:ui-monospace,"Cascadia Code","JetBrains Mono",SFMono-Regular,Menlo,Consolas,monospace;--r:4px;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#0b0f12;--bg2:#11171b;--bg3:#18211f;--fg:#e7ece8;--fg2:#a6b0aa;--fg3:#8a968f;--line:#24302c;--rule:#e7ece8;
--acc:#3fd69b;--acc-ink:#7be8bd;--soft:#10291f;--acc2:#f0a64a;--star:#f0a64a;--ring:#24302c;--band:#050709;--on-band:#e7ece8;
--d-local:#6b9cff;--d-documents:#f0a64a;--d-agents:#b08cff;--d-audio:#ff7ab2;--d-code:#4cc9e8;--d-multilingue:#5fd68a;
--d-image-video:#ff8a5c;--d-donnees:#a9cf52;--d-tendances:#9aa6b2;color-scheme:dark}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:16.5px/1.62 var(--sans)}
a{color:var(--acc-ink);text-decoration:underline;text-decoration-color:color-mix(in srgb,currentColor 35%,transparent);text-underline-offset:2px}
a:hover{text-decoration-color:currentColor}:focus-visible{outline:2px solid var(--acc2);outline-offset:2px}
.w{max-width:1160px;margin:0 auto;padding-inline:16px}
h1,h2,h3{font-family:var(--serif);line-height:1.15;text-wrap:balance;margin:0;font-weight:700;letter-spacing:-.01em}
h1{font-size:clamp(1.8rem,4.2vw,2.9rem)}h2{font-size:1.35rem}h3{font-size:1.08rem}
h3 a,h2 a,.card h3 a{color:var(--fg);text-decoration:none}h3 a:hover,h2 a:hover{color:var(--acc-ink)}
.mono,.num{font-family:var(--mono);font-variant-numeric:tabular-nums}
.eb{font-family:var(--mono);font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;color:var(--fg3)}
.mut{color:var(--fg2)}.sm{font-size:.88rem}
.vh{position:absolute;left:0;top:0;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.skip{position:absolute;left:8px;top:-60px;z-index:10;background:var(--acc);color:var(--bg2);padding:8px 12px;border-radius:var(--r);font-weight:600;text-decoration:none}.skip:focus{top:8px}
/* Bandeau et en-tête façon quotidien */
.strip{background:var(--band);color:var(--on-band);font-family:var(--mono);font-size:.72rem;letter-spacing:.06em}
.strip .w{display:flex;justify-content:space-between;gap:12px;padding-block:6px;flex-wrap:wrap}.strip a{color:var(--on-band)}
header.top{background:var(--bg);border-bottom:3px double var(--rule)}
.bar{display:flex;align-items:center;justify-content:space-between;gap:12px;padding-block:16px 12px;flex-wrap:wrap}
.logo{display:inline-flex;align-items:center;gap:10px;color:var(--fg);text-decoration:none}
.logo svg{width:38px;height:38px;flex:none}.logo b{font-family:var(--serif);font-size:1.7rem;letter-spacing:-.02em;line-height:1}
.logo i{font-style:normal;font-family:var(--mono);font-size:.72rem;color:var(--fg3);letter-spacing:.08em;display:block;margin-top:3px}
nav.m{display:flex;gap:2px;flex-wrap:wrap}
nav.m a{font-family:var(--mono);font-size:.8rem;padding:6px 9px;border-radius:var(--r);color:var(--fg2);text-decoration:none}
nav.m a:hover{color:var(--fg);background:var(--bg3)}nav.m a[aria-current=page]{color:var(--fg);box-shadow:inset 0 -2px 0 var(--acc)}
nav.m a.sub{background:var(--acc);color:var(--bg2);font-weight:600}nav.m a.sub:hover{background:var(--acc-ink)}
main{padding-block:30px 60px}section{margin-top:40px}section:first-child{margin-top:0}
.sh{display:flex;align-items:baseline;justify-content:space-between;gap:12px;border-top:2px solid var(--rule);padding-top:8px;margin-bottom:16px}
.sh h2{font-size:1.25rem}.sh a{font-family:var(--mono);font-size:.8rem;white-space:nowrap}.sh .eb{white-space:nowrap}
.crumb{font-family:var(--mono);font-size:.76rem;color:var(--fg3);margin-bottom:14px}.crumb a{color:var(--fg3)}
/* Une */
.lead{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(0,1fr);gap:36px}@media(max-width:860px){.lead{grid-template-columns:1fr}}
.ess{list-style:none;margin:18px 0 0;padding:0;counter-reset:e}
.ess li{counter-increment:e;display:grid;grid-template-columns:2.2rem 1fr;gap:6px;padding:12px 0;border-top:1px solid var(--line)}
.ess li:first-child{border-top:0}.ess li::before{content:counter(e,decimal-leading-zero);font-family:var(--mono);font-weight:700;color:var(--acc);padding-top:2px}
.box{background:var(--bg3);border-radius:var(--r);padding:16px 18px}
.radar{background:var(--bg2);border:1px solid var(--line);border-radius:var(--r);padding:16px 18px}
.radar h2{font-size:1rem;font-family:var(--mono);text-transform:uppercase;letter-spacing:.1em;color:var(--fg2)}
.bars{list-style:none;margin:12px 0 0;padding:0}.bars li{margin:10px 0}.bars a{color:var(--fg);text-decoration:none;font-weight:600;font-size:.92rem}
.bars .t{display:flex;justify-content:space-between;gap:8px}.bars .t span{font-family:var(--mono);font-size:.8rem;color:var(--fg2)}
.bars .g{height:6px;background:var(--ring);border-radius:3px;margin-top:4px;overflow:hidden}.bars .g i{display:block;height:100%;background:var(--acc);border-radius:3px}
/* Cartes */
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}
.card{background:var(--bg2);border:1px solid var(--line);border-top:3px solid var(--dc,var(--line));border-radius:var(--r);padding:14px 16px;display:flex;flex-direction:column;gap:7px;min-width:0}
.card h3{overflow-wrap:anywhere}.card p{margin:0;font-size:.92rem;color:var(--fg2)}
.meta{display:flex;gap:12px;flex-wrap:wrap;font-family:var(--mono);font-size:.75rem;color:var(--fg2);margin-top:auto;padding-top:4px}
/* Jauge Score Radar */
.sc{--p:0;position:relative;display:inline-grid;place-items:center;width:2.35em;height:2.35em;border-radius:50%;vertical-align:middle;flex:none;
background:radial-gradient(closest-side,var(--bg2) 76%,transparent 78% 100%),conic-gradient(var(--fg3) calc(var(--p)*1%),var(--ring) 0);
font:700 .78rem/1 var(--mono);color:var(--fg)}
.sc.hot{background:radial-gradient(closest-side,var(--bg2) 76%,transparent 78% 100%),conic-gradient(var(--acc) calc(var(--p)*1%),var(--ring) 0);color:var(--acc-ink)}
h1 .sc{font-size:1.1rem}
.chip{display:inline-flex;align-items:center;gap:5px;font-family:var(--mono);font-size:.7rem;padding:2px 7px;border-radius:999px;background:var(--bg3);color:var(--fg2);margin:0 4px 4px 0;text-decoration:none}
.chip[data-d]::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--dc,var(--fg3))}
a.chip:hover{color:var(--fg)}
.star{color:var(--star)}
/* Tableaux */
.tw{overflow-x:auto;border:1px solid var(--line);border-radius:var(--r);background:var(--bg2)}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th{font-family:var(--mono);font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;color:var(--fg3);text-align:left;padding:10px;border-bottom:2px solid var(--rule);white-space:nowrap;background:var(--bg2)}
td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:middle}tr:last-child td{border-bottom:0}tbody tr:hover td{background:var(--bg3)}
td a{text-decoration:none}td a strong{color:var(--fg)}.r{text-align:right}.tw table{min-width:680px}
.up{color:#178a3e}.dn{color:var(--acc2)}
/* Articles */
article.a{max-width:68ch}article.a h1{font-size:clamp(1.9rem,4.4vw,3rem)}
article.a .chapo{font-family:var(--serif);font-size:1.22rem;line-height:1.5;color:var(--fg2);margin:14px 0 0}
.by{font-family:var(--mono);font-size:.76rem;color:var(--fg3);border-block:1px solid var(--line);padding-block:9px;margin:18px 0 24px;display:flex;gap:14px;flex-wrap:wrap}
.body{font-size:1.04rem}.body h2{margin:30px 0 10px;font-size:1.4rem}.body h3{margin:20px 0 6px}.body p{margin:0 0 15px}.body ul,.body ol{padding-left:22px;margin:0 0 15px}
.body table{margin-bottom:15px;display:block;overflow-x:auto;max-width:100%}main{overflow-wrap:anywhere}
.body blockquote{margin:0 0 15px;padding:4px 0 4px 16px;border-left:3px solid var(--acc);color:var(--fg2);font-family:var(--serif);font-size:1.08rem}
.body code,code{font-family:var(--mono);font-size:.86em;background:var(--bg3);padding:1px 5px;border-radius:3px}
dl.kv{display:grid;grid-template-columns:max-content 1fr;gap:0;margin:0;border-top:1px solid var(--line)}
dl.kv dt,dl.kv dd{padding:7px 0;border-bottom:1px solid var(--line)}dl.kv dt{font-family:var(--mono);font-size:.76rem;color:var(--fg3);padding-right:18px;text-transform:uppercase;letter-spacing:.05em}dl.kv dd{margin:0}
.faq dt{font-family:var(--serif);font-weight:700;font-size:1.12rem;margin-top:22px}.faq dd{margin:6px 0 0}
pre.code{font-family:var(--mono);font-size:.82rem;background:var(--band);color:var(--on-band);padding:14px 16px;border-radius:var(--r);overflow-x:auto}
/* Pied de page */
footer{background:var(--band);color:var(--on-band);border-top:1px solid var(--line);padding-block:28px 36px;font-size:.86rem;margin-top:20px}
footer a{color:var(--on-band)}footer .w{display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap}
footer nav{display:flex;gap:14px;flex-wrap:wrap;font-family:var(--mono);font-size:.78rem}footer .logo{color:var(--on-band)}footer .logo i{color:color-mix(in srgb,var(--on-band) 65%,transparent)}
footer p{margin:10px 0 0;max-width:62ch;color:color-mix(in srgb,var(--on-band) 78%,transparent)}
/* Audience et revenus */
.spon{margin-top:30px;padding:10px 14px;border:1px dashed var(--line);border-radius:var(--r);font-size:.86rem;color:var(--fg2)}.spon .eb{margin-right:8px}
.cta{margin-top:40px;border-left:4px solid var(--acc);background:var(--soft)}.cta h2{font-size:1.2rem}.cta p{margin:6px 0}
form.nl{margin:10px 0 4px}form.nl div{display:flex;gap:8px;flex-wrap:wrap}form.nl label{display:block;margin-bottom:4px}
form.nl input[type=email]{flex:1 1 220px;min-width:0;font:inherit;padding:9px 11px;border:1px solid var(--line);border-radius:var(--r);background:var(--bg2);color:var(--fg)}
form.nl button,a.btn{font:600 .9rem var(--sans);padding:9px 15px;border:0;border-radius:var(--r);background:var(--acc);color:var(--bg2);cursor:pointer;display:inline-block;text-decoration:none}
a.btn:hover,form.nl button:hover{background:var(--acc-ink)}.btns{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}
.offres{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px;margin-top:12px}.offres .card strong.prix{font-family:var(--mono);color:var(--acc-ink)}
/* Couleurs de domaine */
[data-d=local]{--dc:var(--d-local)}[data-d=documents]{--dc:var(--d-documents)}[data-d=agents]{--dc:var(--d-agents)}[data-d=audio]{--dc:var(--d-audio)}
[data-d=code]{--dc:var(--d-code)}[data-d=multilingue]{--dc:var(--d-multilingue)}[data-d=image-video]{--dc:var(--d-image-video)}[data-d=donnees]{--dc:var(--d-donnees)}[data-d=tendances]{--dc:var(--d-tendances)}
@media(max-width:600px){body{font-size:16px}.bar{padding-block:12px 6px;gap:8px}.logo b{font-size:1.45rem}.logo svg{width:32px;height:32px}.strip .long{display:none}
nav.m{flex-wrap:nowrap;overflow-x:auto;width:100%;gap:0;scrollbar-width:none;margin-inline:-4px}nav.m a{padding:7px 8px;font-size:.78rem;white-space:nowrap}.lead{gap:24px}}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}
@media print{.strip,nav.m,.spon,.cta,footer nav{display:none}body{background:#fff;color:#000}}
"""

LOGO = ('<svg viewBox="0 0 40 40" aria-hidden="true"><circle cx="20" cy="20" r="18" fill="none" stroke="currentColor" stroke-width="2"/>'
        '<circle cx="20" cy="20" r="11" fill="none" stroke="currentColor" stroke-width="1.4" opacity=".5"/>'
        '<path d="M20 20 L20 2 A18 18 0 0 1 35.6 11 Z" fill="var(--acc)" opacity=".3"/>'
        '<line x1="20" y1="20" x2="35.6" y2="11" stroke="var(--acc)" stroke-width="2.4" stroke-linecap="round"/>'
        '<circle cx="27.5" cy="9.6" r="2.7" fill="var(--acc2)"/><circle cx="20" cy="20" r="2.3" fill="currentColor"/></svg>')
FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><circle cx="20" cy="20" r="20" fill="#0b0f12"/>'
           '<circle cx="20" cy="20" r="15" fill="none" stroke="#3fd69b" stroke-width="2.2"/><circle cx="20" cy="20" r="8.5" fill="none" stroke="#3fd69b" stroke-width="1.4" opacity=".55"/>'
           '<line x1="20" y1="20" x2="33" y2="12.5" stroke="#3fd69b" stroke-width="2.6" stroke-linecap="round"/><circle cx="27" cy="11" r="2.8" fill="#f0a64a"/></svg>')

def dom_chip(site, d, root=None) -> str:
    """Pastille de domaine colorée (lien si root est fourni)."""
    if root is None:
        return f'<span class="chip" data-d="{esc(d)}">{esc(site.dom_name(d))}</span>'
    return f'<a class="chip" data-d="{esc(d)}" href="{root}{site.dom_page(d)}">{esc(site.dom_name(d))}</a>'

NAV = [("index.html", "Une"), ("classements.html", "Classements"), ("articles.html", "Articles"), ("modeles.html", "Modèles"),
       ("domaines.html", "Domaines"), ("guides.html", "Guides"), ("editions.html", "Éditions"), ("faq.html", "FAQ"), ("pour-les-ia.html", "API & IA"),
       ("abonnement.html", "S'abonner")]

# ------------------------------------------------------------------ blocs d'audience et de revenus (masqués tant que non configurés)

def bloc_abonnement(site, root) -> str:
    """Appel à s'abonner : formulaire de newsletter s'il est configuré, sinon flux RSS."""
    nl = site.cfg.get("newsletter") or {}
    if has_url(nl.get("action")):
        caches = "".join(f'<input type="hidden" name="{esc(k)}" value="{esc(v)}">' for k, v in (nl.get("champsCaches") or {}).items())
        form = (f'<form class="nl" action="{esc(nl["action"])}" method="post" target="_blank"><label class="sm" for="nl-email">Votre adresse e-mail</label>'
                f'<div><input id="nl-email" type="email" name="{esc(nl.get("champEmail") or "email")}" required placeholder="vous@exemple.fr" autocomplete="email">'
                f'<button type="submit">Recevoir l\'édition</button></div>{caches}</form>'
                '<p class="sm mut">Gratuit. Une adresse utilisée uniquement pour envoyer Radar IA, désinscription en un clic.</p>')
    else:
        form = (f'<p class="btns"><a class="btn" href="{root}feed.xml">Flux RSS</a>'
                f'<a class="btn" href="https://feedly.com/i/subscription/feed/{quote(site.abs("feed.xml"), safe="")}" rel="noopener">Suivre sur Feedly</a></p>')
    return (f'<section class="box cta"><h2>Recevez Radar IA chaque matin</h2><p class="sm">L\'essentiel des modèles IA ouverts en deux minutes : '
            f'nouveautés Hugging Face, modèles à tester en local, scores et analyses en français.</p>{form}'
            f'<p class="sm"><a href="{root}abonnement.html">Toutes les façons de suivre Radar IA →</a></p></section>')

def bloc_sponsor(site, root) -> str:
    """Emplacement partenaire : sponsor actif (lien rel=sponsored) ou invitation à sponsoriser."""
    sp = site.cfg.get("sponsor") or {}
    if sp.get("nom") and has_url(sp.get("url")) and (not sp.get("jusquau") or str(sp["jusquau"]) >= site.today):
        return (f'<aside class="spon"><span class="eb">Partenaire</span><a href="{esc(sp["url"])}" rel="sponsored noopener"><strong>{esc(sp["nom"])}</strong></a>'
                f'{" — " + esc(sp["accroche"]) if sp.get("accroche") else ""}</aside>')
    return (f'<aside class="spon"><span class="eb">Espace partenaire</span>Présentez votre outil IA à des développeurs et décideurs francophones : '
            f'<a href="{root}soutenir.html#annoncer">devenir partenaire de Radar IA</a>.</aside>')

def bloc_affiliation(site, it) -> str:
    """Lien affilié signalé comme tel, seulement sur les fiches de modèles."""
    af = (site.cfg.get("affiliation") or {}).get("gpu") or {}
    if it.get("type") != "model" or not has_url(af.get("url")) or not af.get("nom"):
        return ""
    return (f'<p class="box sm" style="margin-top:12px"><strong>Pas de carte graphique adaptée ?</strong> {esc(af.get("texte") or "Louez un GPU à l’heure pour tester ce modèle")} : '
            f'<a href="{esc(af["url"])}" rel="sponsored noopener">{esc(af["nom"])}</a> <span class="mut">(lien affilié : Radar IA perçoit une commission, sans surcoût pour vous)</span>.</p>')

def pixel(site, path) -> str:
    """Mesure d'audience sans cookie ni JavaScript (pixel image, ex. GoatCounter)."""
    tpl = (site.cfg.get("mesure") or {}).get("pixel") or ""
    if not tpl.startswith("https://"):
        return ""
    src = tpl.replace("{path}", quote("/" + (path if path != "index.html" else ""), safe="/"))
    return f'<img src="{esc(src)}" alt="" width="1" height="1" style="position:absolute;left:-9999px" referrerpolicy="no-referrer-when-downgrade">'

def bloc_partage(site, url, titre) -> str:
    """Liens de partage sans JavaScript ni bouton tiers (aucun traceur chargé)."""
    if not url.startswith("http"):
        return ""
    u, t = quote(url, safe=""), quote(titre, safe="")
    liens = [("LinkedIn", f"https://www.linkedin.com/sharing/share-offsite/?url={u}"), ("Bluesky", f"https://bsky.app/intent/compose?text={t}%20{u}"),
             ("X", f"https://x.com/intent/post?text={t}&url={u}"), ("Mastodon", f"https://tootpick.org/#text={t}%20{u}"),
             ("E-mail", f"mailto:?subject={t}&body={u}")]
    return '<p class="sm mono">Partager : ' + " · ".join(f'<a href="{esc(h)}" rel="noopener nofollow">{n}</a>' for n, h in liens) + "</p>"

def contact_url(site, sujet="Partenariat Radar IA") -> str:
    c = site.cfg.get("contact") or {}
    if c.get("email") and re.match(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", c["email"], re.I):
        return f"mailto:{c['email']}?subject={quote(sujet)}"
    if has_url(c.get("formulaire")):
        return c["formulaire"]
    if has_url(site.cfg.get("depot")):
        return site.cfg["depot"].rstrip("/") + "/issues/new?template=partenariat.md"
    return ""

def page(site: Site, path: str, title: str, desc: str, body: str, *, jsonld: list | None = None, crumbs=None,
         og_type="website", md_path: str | None = None, nav_key: str | None = None, artifact_shell=False,
         published: str | None = None, modified: str | None = None, feed: tuple[str, str] | None = None) -> str:
    depth = path.count("/")
    root = "../" * depth
    if path == "404.html" and site.url:  # servie à n'importe quelle profondeur : liens absolus
        root = site.url
    canonical = site.abs(path if path != "index.html" else "")
    verif = site.cfg.get("verification") or {}
    verif_meta = "".join(f'<meta name="{n}" content="{esc(verif[k])}">' for k, n in (("google", "google-site-verification"), ("bing", "msvalidate.01"))
                         if re.match(r"^[\w-]{6,}$", str(verif.get(k) or "")))
    og_img = (f'<meta property="og:image" content="{esc(site.abs("assets/og.png"))}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
              f'<meta name="twitter:card" content="summary_large_image">') if site.og and site.url else '<meta name="twitter:card" content="summary">'
    # suffixe de marque seulement s'il tient dans 70 caractères (pas de titre tronqué dans les résultats)
    full_title = title if title.endswith(SITE_NAME) or len(f"{title} · {SITE_NAME}") > 70 else f"{title} · {SITE_NAME}"
    ld = [ld_website(site), ld_org(site)] + (jsonld or [])
    if crumbs:
        ld.append(ld_breadcrumb(site, crumbs))
    nav = "".join(f'<a href="{root}{h}"{" class=sub" if h == "abonnement.html" else ""}{" aria-current=page" if (nav_key or path)==h else ""}>{esc(l)}</a>' for h, l in NAV)
    crumb_html = ""
    if crumbs:
        parts = [f'<a href="{root}{h}">{esc(l)}</a>' if h else esc(l) for l, h in crumbs]
        crumb_html = f'<div class="crumb">{" / ".join(parts)}</div>'
    head = f"""<title>{esc(full_title if og_type == "article" else clip(full_title, 70))}</title>
<meta name="description" content="{esc(clip(desc, 158))}">
<meta name="robots" content="{'noindex' if path == '404.html' else 'index,follow,max-snippet:-1,max-image-preview:large'}">{verif_meta}
{f'<link rel="canonical" href="{esc(canonical)}">' if site.url and path != '404.html' else ''}
<link rel="stylesheet" href="{root}assets/style.css"><link rel="icon" href="{root}assets/favicon.svg" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="{SITE_NAME} — RSS" href="{root}feed.xml">{f'<link rel="alternate" type="application/rss+xml" title="{esc(feed[1])}" href="{root}{feed[0]}">' if feed else ''}
<link rel="alternate" type="application/feed+json" title="{SITE_NAME} — JSON Feed" href="{root}feed.json">
<link rel="alternate" type="text/plain" title="llms.txt" href="{root}llms.txt">
{f'<link rel="alternate" type="text/markdown" href="{root}{md_path}">' if md_path else ''}
<link rel="sitemap" type="application/xml" href="{root}sitemap.xml">
<meta property="og:site_name" content="{SITE_NAME}"><meta property="og:locale" content="fr_FR">
<meta property="og:type" content="{og_type}"><meta property="og:title" content="{esc(clip(title, 90))}">
<meta property="og:description" content="{esc(clip(desc, 200))}">{f'<meta property="og:url" content="{esc(canonical)}">' if site.url else ''}
{f'<meta property="article:published_time" content="{esc(iso_dt(published))}">' if published else ''}{f'<meta property="article:modified_time" content="{esc(iso_dt(modified))}">' if modified else ''}
{og_img}<meta name="theme-color" content="#0b0f12">
<script type="application/ld+json">{json.dumps(ld if len(ld) > 1 else ld[0], ensure_ascii=False).replace("</", "<\\/")}</script>"""
    marque = f'{LOGO}<span><b>{SITE_NAME}</b><i>LE QUOTIDIEN DES MODÈLES IA OUVERTS</i></span>'
    shell_top = f"""<a class="skip" href="#contenu">Aller au contenu</a><div class="strip"><div class="w"><span>Édition du {d_long(site.today)}<span class="long"> · veille quotidienne Hugging Face en français</span></span><span><a href="{root}abonnement.html">S'abonner</a> · <a href="{root}feed.xml">RSS</a> · <a href="{root}llms.txt">llms.txt</a></span></div></div>
<header class="top"><div class="w bar"><a class="logo" href="{root}index.html">{marque}</a><nav class="m" aria-label="Rubriques">{nav}</nav></div></header>
<main class="w" id="contenu" tabindex="-1">{crumb_html}{body}</main>
<footer><div class="w"><div><a class="logo" href="{root}index.html">{marque}</a><p>{esc(SITE_TAGLINE)}. Rédigé par des agents IA ; licences, dates et tailles vérifiées sur l'API Hugging Face ; sources liées sur chaque page. Données sous licence <a href="{LICENSE_URL}" rel="license">CC BY 4.0</a> · mise à jour {d_short(site.today)}.</p></div>
<nav aria-label="Pied de page"><a href="{root}abonnement.html">S'abonner</a><a href="{root}soutenir.html">Soutenir</a><a href="{root}soutenir.html#annoncer">Devenir partenaire</a><a href="{root}guides.html">Guides</a><a href="{root}glossaire.html">Glossaire</a><a href="{root}methode.html">Méthode</a><a href="{root}feed.xml">RSS</a><a href="{root}llms.txt">llms.txt</a><a href="{root}api/v1/index.json">API</a><a href="{root}sitemap.xml">Sitemap</a></nav></div></footer>{pixel(site, path)}"""
    if artifact_shell:  # page racine d'un artefact Claude : pas de doctype, le squelette est ajouté à la publication
        return head + "\n" + shell_top
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
{head}
</head><body>
{shell_top}
</body></html>"""

# ------------------------------------------------------------------ JSON-LD

def ld_org(site):
    d = {"@context": "https://schema.org", "@type": "Organization", "@id": site.abs("#org"), "name": SITE_NAME,
         "url": site.abs(""), "description": SITE_DESC}
    same = [r.get("url") for r in site.cfg.get("reseaux") or [] if has_url(r.get("url"))] + ([site.cfg["depot"]] if has_url(site.cfg.get("depot")) else [])
    if same: d["sameAs"] = same
    if site.og and site.url: d["image"] = site.abs("assets/og.png")
    return d

def ld_website(site):
    return {"@context": "https://schema.org", "@type": "WebSite", "@id": site.abs("#site"), "name": SITE_NAME, "url": site.abs(""),
            "inLanguage": "fr-FR", "description": SITE_DESC, "publisher": {"@id": site.abs("#org")}}

def ld_breadcrumb(site, crumbs):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": l, **({"item": site.abs(h)} if h else {})} for i, (l, h) in enumerate(crumbs)]}

def ld_item(site, it):
    t = it.get("type")
    typ = {"dataset": "Dataset", "space": "WebApplication"}.get(t, "SoftwareApplication")
    v = site.v(it)
    d = {"@context": "https://schema.org", "@type": typ, "name": it.get("nom"), "url": site.hf_url(it),
         "description": it.get("resume") or it.get("pourquoi"), "sameAs": site.hf_url(it),
         "creator": {"@type": "Organization", "name": site.org(it)}, "dateModified": v.get("majLe") or it.get("majLe")}
    if site.cree(it): d["datePublished"] = site.cree(it)
    if site.lic(it): d["license"] = v.get("licenceLien") or site.lic(it)
    langs = [l for l in v.get("langues") or [] if l != "multilingual"]
    if langs: d["inLanguage"] = langs
    if typ != "Dataset":
        d["applicationCategory"] = "AI model" if t == "model" else "AI demo"; d["operatingSystem"] = "Cross-platform"
    d["keywords"] = ", ".join([it.get("tache") or ""] + [site.dom_name(x) for x in it.get("domaines") or []])
    d["interactionStatistic"] = [
        {"@type": "InteractionCounter", "interactionType": "https://schema.org/LikeAction", "userInteractionCount": it.get("likes") or 0},
        {"@type": "InteractionCounter", "interactionType": "https://schema.org/DownloadAction", "userInteractionCount": it.get("downloads") or 0}]
    return d

def ld_article(site, a):
    return {"@context": "https://schema.org", "@type": "NewsArticle", "headline": clip(a.get("titre", ""), 110),
            "description": a.get("chapo"), "datePublished": iso_dt(a.get("publieLe") or a.get("date")),
            "dateModified": iso_dt(a.get("publieLe") or a.get("date")), "inLanguage": "fr-FR",
            "author": {"@type": "Organization", "name": f"{SITE_NAME} — {a.get('auteur', 'Rédacteur IA')}"},
            "publisher": {"@id": site.abs("#org")}, "mainEntityOfPage": site.abs(site.art_page(a)),
            "articleSection": site.dom_name(a.get("domaine")), "keywords": ", ".join(a.get("motsCles") or []),
            "wordCount": word_count(a.get("corpsHtml")), "isAccessibleForFree": True,
            "citation": [s.get("url") for s in a.get("sources") or [] if s.get("url")],
            "about": [{"@type": "SoftwareApplication", "name": site.items[i]["nom"], "url": site.hf_url(site.items[i])}
                      for i in a.get("itemIds") or [] if i in site.items]}

def ld_itemlist(site, name, items, url):
    return {"@context": "https://schema.org", "@type": "ItemList", "name": name, "url": site.abs(url), "numberOfItems": len(items),
            "itemListOrder": "https://schema.org/ItemListOrderDescending", "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "url": site.abs(site.item_page(it)), "name": it.get("nom")} for i, it in enumerate(items)]}

def ld_faq(qas):
    return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": re.sub(r"<[^>]+>", "", a)}} for q, a in qas]}

def ld_dataset(site):
    return {"@context": "https://schema.org", "@type": "Dataset", "name": "Radar IA — classements quotidiens des modèles IA ouverts",
            "description": "Relevé quotidien des modèles, datasets et Spaces tendance sur Hugging Face, avec likes, téléchargements, "
                           "domaines, pertinence et Score Radar (0-100). Classements jour, 7 jours, 30 jours, 90 jours.",
            "url": site.abs("pour-les-ia.html"), "license": LICENSE_URL, "inLanguage": "fr", "isAccessibleForFree": True,
            "creator": {"@id": site.abs("#org")}, "dateModified": site.today, "temporalCoverage": f"2026-10-11/{site.today}",
            "keywords": ["Hugging Face", "LLM", "modèles open source", "classement IA", "GGUF", "OCR", "agents IA"],
            "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": site.abs(f"api/v1/{n}.json")}
                             for n in ("items", "classements", "articles", "editions")]}

# ------------------------------------------------------------------ composants HTML

def score_badge(s):
    if s is None: return ""
    s = max(0, min(100, round(float(s))))
    return f'<span class="sc{" hot" if s >= 70 else ""}" style="--p:{s}" title="Score Radar {s}/100"><span class="vh">Score Radar </span>{s}<span class="vh"> sur 100</span></span>'

def item_card(site, it, root, rank=None):
    star = '<span class="star" title="Pertinent : local, documents, agents, audio, code, français">★</span> ' if it.get("pertinent") else ""
    doms = "".join(dom_chip(site, d) for d in it.get("domaines") or [])
    d0 = (it.get("domaines") or ["tendances"])[0]
    return f"""<div class="card" data-d="{esc(d0)}"><div style="display:flex;justify-content:space-between;gap:8px"><div class="eb">{f"#{rank} · " if rank else ""}{esc(site.org(it))}</div>{score_badge(it.get('score'))}</div>
<h3>{star}<a href="{root}{site.item_page(it)}">{esc(it.get('nom'))}</a></h3><div>{doms}<span class="chip">{esc(TYPE_LABEL.get(it.get('type'), ''))}</span></div>
<p>{esc(it.get('pourquoi') or it.get('resume'))}</p><div class="meta"><span>♥ {fmt_n(it.get('likes'))}</span><span>↓ {fmt_n(it.get('downloads'))}</span>{f"<span>{esc(site.taille(it))}</span>" if site.taille(it) else ''}</div></div>"""

def art_card(site, a, root):
    return f"""<div class="card" data-d="{esc(a.get('domaine'))}"><div>{dom_chip(site, a.get('domaine'))}</div><h3><a href="{root}{site.art_page(a)}">{esc(a.get('titre'))}</a></h3>
<p>{esc(a.get('chapo'))}</p><div class="meta"><span>{d_short(a.get('date'))}</span><span>{esc(a.get('tempsLecture') or '')} min</span></div></div>"""

def ranking_table(site, entries, root, limit=None):
    rows = []
    for i, e in enumerate(entries[:limit] if limit else entries):
        it = site.items.get(e.get("itemId"))
        if not it: continue
        d = e.get("delta")
        dl = '<span class="star">nouveau</span>' if d is None else (f'<span class="up">▲ {d}</span>' if d > 0 else (f'<span class="dn">▼ {-d}</span>' if d < 0 else "="))
        rows.append(f"""<tr><td class="num">{e.get('rank') or e.get('rang') or i+1}</td><td><a href="{root}{site.item_page(it)}"><strong>{esc(it.get('nom'))}</strong></a>{' <span class="star">★</span>' if it.get('pertinent') else ''}<div class="sm mut mono">{esc(site.org(it))} · {esc(TYPE_LABEL.get(it.get('type'), ''))}{(' · ' + esc(it['tache'])) if it.get('tache') else ''}</div></td>
<td>{''.join(dom_chip(site, x) for x in it.get('domaines') or [])}</td><td class="r num">{fmt_n(e.get('likes', it.get('likes')))}</td><td class="r num">{fmt_n(e.get('downloads', it.get('downloads')))}</td><td class="r">{score_badge(e.get('score', it.get('score')))}</td><td class="mono sm">{dl}</td></tr>""")
    if not rows: return '<p class="mut">Classement en cours de calcul.</p>'
    return f'<div class="tw"><table><thead><tr><th>#</th><th>Élément</th><th>Domaines</th><th class="r">Likes</th><th class="r">Téléch.</th><th class="r">Score</th><th>Évol.</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'

def rss_domaine(site, dk) -> str:
    """Flux RSS 2.0 d'un domaine : ses articles et ses éléments nouvellement suivis, du plus récent au plus ancien."""
    entrees = [(a.get("publieLe") or a.get("date") or "", a.get("titre"), site.abs(site.art_page(a)), a.get("chapo"), sanitize(a.get("corpsHtml")))
               for a in site.art_sorted if a.get("domaine") == dk]
    entrees += [(it.get("premiereVue") or site.cree(it) or "", f"Nouveau dans le radar : {it.get('nom')} ({site.org(it)})", site.abs(site.item_page(it)),
                 it.get("resume") or it.get("pourquoi"), None) for it in site.items_in(dk) if it.get("premiereVue")]
    entrees.sort(key=lambda e: e[0], reverse=True)
    nom = site.dom_name(dk); url = site.abs(f"feeds/{dk}.xml")
    items = "".join(f"<item><title>{esc(t)}</title><link>{esc(u)}</link><guid isPermaLink=\"true\">{esc(u)}</guid><pubDate>{rfc822(d)}</pubDate>"
                    f"<category>{esc(nom)}</category><description>{esc(c)}</description>"
                    + (f"<content:encoded><![CDATA[{h.replace(']]>', ']]&gt;')}]]></content:encoded>" if h else "") + "</item>" for d, t, u, c, h in entrees[:40])
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
            f"<title>{esc(SITE_NAME)} — {esc(nom)}</title><link>{esc(site.abs(site.dom_page(dk)))}</link><description>{esc(site.domaines.get(dk, {}).get('description') or nom)}</description>"
            f'<language>fr-fr</language><lastBuildDate>{rfc822(site.built_at)}</lastBuildDate><atom:link href="{esc(url)}" rel="self" type="application/rss+xml"/>{items}</channel></rss>')

def radar_panel(site, n=6) -> str:
    """Top du jour en jauges horizontales (CSS seul)."""
    ent = [(e, site.items[e["itemId"]]) for e in (site.classements.get("jour") or {}).get("entrees") or [] if e.get("itemId") in site.items][:n]
    if not ent: return ""
    li = "".join(f'<li><div class="t"><a href="{site.item_page(it)}">{esc(it.get("nom"))}</a><span>{round(float(e.get("score") or it.get("score") or 0))}</span></div>'
                 f'<div class="g" aria-hidden="true"><i style="width:{max(2, min(100, round(float(e.get("score") or it.get("score") or 0))))}%"></i></div></li>' for e, it in ent)
    return f'<div class="radar"><h2>Le radar du jour</h2><ol class="bars">{li}</ol><p class="sm" style="margin:10px 0 0"><a href="classements.html">Classement complet →</a></p></div>'

def ranking_items(site, per):
    cl = site.classements.get(per) or {}
    return [site.items[e["itemId"]] for e in cl.get("entrees") or [] if e.get("itemId") in site.items]

def fiche_faits(site, it, root) -> tuple[str, str]:
    """Lignes « clé : valeur » d'une fiche (HTML pour dl.kv, Markdown) ; faits vérifiés prioritaires."""
    v, rows = site.v(it), []
    add = lambda lab, h, m: rows.append((lab, h, m))
    add("Identifiant", f"<code>{esc(it.get('hfId'))}</code>", None)
    acc = (it.get("hfId") or "").split("/")[0]
    add("Éditeur", (f'<a href="{root}{site.ed_page_url(acc)}">{esc(site.org(it))}</a>' if site.has_ed_page(acc) else esc(site.org(it))), site.org(it))
    if acc: add("Compte Hugging Face", f'<a href="https://huggingface.co/{esc(acc)}" rel="noopener">{esc(acc)}</a>' + (f' <span class="mut sm">({esc(v["compteType"])})</span>' if v.get("compteType") else ""), acc)
    tache = it.get("tache") or v.get("tache")
    add("Tâche", esc(tache) + (f' <span class="mut mono sm">({esc(v["tache"])})</span>' if v.get("tache") and v["tache"] != tache else ""), tache)
    if v.get("parametres"): add("Paramètres", f'<span class="num">{fmt_params(v["parametres"])}</span>', fmt_params(v["parametres"]))
    else: add("Taille", esc(it.get("taille") or "non communiquée"), it.get("taille") or "n.c.")
    lic = site.lic(it)
    add("Licence", (f'<a href="{root}guides/licences.html#{slugify(lic)}">{esc(lic)}</a>' + (f' · <a href="{esc(v["licenceLien"])}" rel="noopener">texte de la licence</a>' if v.get("licenceLien") else ""))
        if lic else "non déclarée", lic or "non déclarée")
    if v.get("langues"):
        add("Langues déclarées", ", ".join(f'<a href="{root}guides/francais.html">français</a>' if l == "fr" else esc(langue(l)) for l in v["langues"]),
            ", ".join(langue(l) for l in v["langues"]))
    if v.get("formats"):
        add("Formats", ", ".join(f'<a href="{root}guides/gguf.html">GGUF</a>' if f == "GGUF" else esc(f) for f in v["formats"]), ", ".join(v["formats"]))
    if v.get("contexte"): add("Contexte", f'<span class="num">{fmt_n(v["contexte"])}</span> <a href="{root}glossaire.html#token">tokens</a>', f'{v["contexte"]} tokens')
    if v.get("modeleBase"):
        fam, suivis = site.familles(), site.by_hf()
        def lien(b):
            bid = b["id"]
            href = root + site.fam_page(bid) if bid in fam else (root + site.item_page(suivis[bid]) if bid in suivis else "https://huggingface.co/" + bid)
            ancre = {"quantized": "quantification", "finetune": "fine-tune", "adapter": "adaptateur", "merge": "fusion"}.get(b.get("relation"), "modele-de-base")
            return f'<a href="{esc(href)}">{esc(bid)}</a> <span class="mut sm">(<a href="{root}glossaire.html#{ancre}">{RELATIONS.get(b.get("relation"), "dérivé")}</a>)</span>'
        add("Modèle de base", "<br>".join(lien(b) for b in v["modeleBase"]),
            ", ".join(f'{b["id"]} ({RELATIONS.get(b.get("relation"), "dérivé")})' for b in v["modeleBase"]))
    if v.get("bibliotheque"): add("Bibliothèque", esc(v["bibliotheque"]), v["bibliotheque"])
    if v.get("volumetrie"): add("Volumétrie", esc(v["volumetrie"]), v["volumetrie"])
    if v.get("acces"): add("Accès aux poids", esc(v["acces"]) + (f' · <a href="{root}glossaire.html#acces-restreint">définition</a>' if v["acces"] != "libre" else ""), v["acces"])
    add("Créé le", d_long(site.cree(it)), site.cree(it) or "n.c.")
    if v.get("majLe"): add("Mis à jour le", d_long(v["majLe"]), v["majLe"])
    likes = v["likes"] if "likes" in v else it.get("likes")
    add("Likes", f'<span class="num">{fmt_n(likes)}</span>', likes)
    if "downloads" in v: add("Téléchargements (30 j)", f'<span class="num">{fmt_n(v["downloads"])}</span>', v["downloads"])
    elif it.get("downloads") is not None: add("Téléchargements", f'<span class="num">{fmt_n(it["downloads"])}</span>', it["downloads"])
    if v.get("arxiv"):
        add("arXiv", ", ".join(f'<a href="https://arxiv.org/abs/{esc(a)}" rel="noopener">{esc(a)}</a>' for a in v["arxiv"]), ", ".join(v["arxiv"]))
    return ("".join(f"<dt>{lab}</dt><dd>{h}</dd>" for lab, h, _ in rows),
            "".join(f"- {lab} : {m}\n" for lab, _, m in rows if m is not None))

def table_faits(site, items, root, cols=("base", "params", "licence", "dl", "score")) -> str:
    """Tableau compact d'éléments avec faits vérifiés (pages guides et familles)."""
    noms = {"base": "Modèle de base", "params": "Paramètres", "contexte": "Contexte", "licence": "Licence", "langues": "Langues",
            "dl": "Téléch. 30 j", "score": "Score", "relation": "Relation"}
    head = "<th>Élément</th>" + "".join(f'<th{" class=r" if c in ("dl", "score", "params", "contexte") else ""}>{noms[c]}</th>' for c in cols)
    rows = []
    for x in items:
        it, rel = x if isinstance(x, tuple) else (x, None)
        v = site.v(it)
        cell = {"base": lambda: ", ".join(esc(b["id"]) for b in v.get("modeleBase") or []) or "—",
                "params": lambda: fmt_params(v.get("parametres")) or esc(it.get("taille") or "—"),
                "contexte": lambda: fmt_n(v["contexte"]) if v.get("contexte") else "—",
                "licence": lambda: esc(site.lic(it) or "non déclarée"),
                "langues": lambda: esc(", ".join(langue(l) for l in v.get("langues") or []) or "—"),
                "dl": lambda: fmt_n(v.get("downloads", it.get("downloads"))),
                "score": lambda: score_badge(it.get("score")),
                "relation": lambda: esc(RELATIONS.get(rel, "dérivé"))}
        rows.append(f'<tr><td><a href="{root}{site.item_page(it)}"><strong>{esc(it.get("nom"))}</strong></a><div class="sm mut mono">{esc(site.org(it))}</div></td>'
                    + "".join(f'<td class="{"r num" if c in ("dl", "score", "params", "contexte") else "sm"}">{cell[c]()}</td>' for c in cols) + "</tr>")
    return f'<div class="tw"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>' if rows else '<p class="mut">Aucun élément suivi pour le moment.</p>'

def build_guides(site, write, write_md) -> list[tuple[str, str, str]]:
    """Pages guides générées uniquement à partir des faits vérifiés sur Hugging Face. Renvoie (titre, page, résumé)."""
    mois = d_long(site.today).split(" ", 1)[-1]
    tous = sorted(site.items.values(), key=lambda i: -(i.get("score") or 0))
    verif = d_short(max((v.get("verifieLe", "") for v in site.hf.values()), default="")) if site.hf else None
    note = (f'<p class="sm mut">Faits relevés sur l’API publique Hugging Face le {verif} ; ils sont déclarés par les auteurs des modèles.</p>' if verif
            else '<p class="sm mut">Vérification Hugging Face indisponible pour cette génération : données des fiches Radar IA.</p>')
    guides = []
    crumbs = lambda t: [("Accueil", "index.html"), ("Guides", "guides.html"), (t, None)]

    # Français
    fr = [i for i in tous if "fr" in (site.v(i).get("langues") or [])]
    multi = [i for i in tous if "multilingual" in (site.v(i).get("langues") or []) and i not in fr]
    t = f"Modèles IA open source en français ({mois})"
    body = (f'<h1>{esc(t)}</h1><p class="mut" style="max-width:70ch">Les modèles, datasets et Spaces suivis par Radar IA dont les auteurs déclarent le français '
            f'sur Hugging Face. Une langue déclarée n’est pas une garantie de qualité : testez sur vos propres textes.</p>{note}'
            f'<section><div class="sh"><h2>Français déclaré ({len(fr)})</h2></div>{table_faits(site, fr, "../", ("params", "langues", "licence", "dl", "score"))}</section>'
            + (f'<section><div class="sh"><h2>Déclarés « multilingues » sans liste de langues ({len(multi)})</h2></div><p class="sm">Le français n’est ni confirmé ni exclu : vérifiez sur la fiche officielle.</p>{table_faits(site, multi, "../", ("params", "licence", "dl", "score"))}</section>' if multi else ""))
    write("guides/francais.html", page(site, "guides/francais.html", t, f"{len(fr)} modèles IA open source suivis déclarent le français sur Hugging Face : taille, licence, téléchargements et Score Radar, vérifiés le {verif or site.today}.",
                                       body, crumbs=crumbs("Français"), nav_key="guides.html", md_path="guides/francais.md", jsonld=[ld_itemlist(site, t, fr, "guides/francais.html")] if fr else None))
    write_md("guides/francais.md", t, f"# {t}\n\nÉléments dont les auteurs déclarent le français sur Hugging Face.\n\n" +
             "\n".join(f"- [{i['nom']}]({site.abs(site.item_page(i))}) — {site.taille(i) or 'taille n.c.'}, licence {site.lic(i) or 'non déclarée'}, score {i.get('score')}" for i in fr))
    guides.append((t, "guides/francais.html", f"{len(fr)} éléments déclarent le français"))

    # Licences
    par_lic: dict[str, list] = {}
    for i in tous: par_lic.setdefault(site.lic(i) or "", []).append(i)
    ordre = sorted(par_lic, key=lambda l: (l == "", -len(par_lic[l]), l))
    t = f"Licences des modèles IA open source suivis ({mois})"
    sommaire = " · ".join(f'<a href="#{slugify(l) if l else "non-declaree"}">{esc(l or "non déclarée")} ({len(par_lic[l])})</a>' for l in ordre)
    secs = "".join(f'<section id="{slugify(l) if l else "non-declaree"}"><div class="sh"><h2>{esc(l or "Licence non déclarée")}</h2><span class="eb">{len(par_lic[l])} élément(s)</span></div>'
                   f'<p class="sm" style="max-width:70ch">{esc(LICENCES.get(l.lower(), LICENCE_AUTRE) if l else LICENCE_AUCUNE)}</p>{table_faits(site, par_lic[l][:12], "../", ("params", "dl", "score"))}{f'<p class="sm mut">Les 12 mieux classés sur {len(par_lic[l])}.</p>' if len(par_lic[l]) > 12 else ""}</section>' for l in ordre)
    body = (f'<h1>{esc(t)}</h1><p class="mut" style="max-width:70ch">Avant d’utiliser un modèle en entreprise, sa licence compte autant que ses performances. '
            f'Voici la licence déclarée de chaque élément suivi, regroupée et résumée. Résumés indicatifs, pas un avis juridique : lisez le texte de la licence (lien sur chaque fiche).</p>{note}'
            f'<p class="sm mono">{sommaire}</p>{secs}')
    write("guides/licences.html", page(site, "guides/licences.html", t, "Licence de chaque modèle IA open source suivi (Apache 2.0, MIT, licences propres aux éditeurs) : ce qu'elle autorise, vérifié sur Hugging Face.",
                                       body, crumbs=crumbs("Licences"), nav_key="guides.html", md_path="guides/licences.md"))
    write_md("guides/licences.md", t, f"# {t}\n\n" + "\n\n".join(f"## {l or 'Licence non déclarée'}\n\n{LICENCES.get(l.lower(), LICENCE_AUTRE) if l else LICENCE_AUCUNE}\n\n" +
             "\n".join(f"- [{i['nom']}]({site.abs(site.item_page(i))})" for i in par_lic[l]) for l in ordre))
    guides.append((t, "guides/licences.html", f"{len(ordre)} licences différentes"))

    # GGUF
    gg = [i for i in tous if "GGUF" in (site.v(i).get("formats") or [])]
    t = f"Modèles GGUF pour llama.cpp, Ollama, LM Studio ({mois})"
    body = (f'<h1>{esc(t)}</h1><p class="mut" style="max-width:70ch">Le format GGUF est celui de llama.cpp et des outils qui l’utilisent (Ollama, LM Studio). '
            f'Voici les dépôts GGUF suivis par Radar IA, avec leur modèle de base, leur nombre de paramètres et leur contexte déclarés.</p>{note}'
            f'{table_faits(site, gg, "../", ("base", "params", "contexte", "licence", "dl", "score"))}'
            '<h2 style="margin-top:24px">Lancer un dépôt GGUF</h2><ul class="sm"><li>llama.cpp : <code>llama-cli -hf organisation/depot</code></li>'
            '<li>Ollama : <code>ollama run hf.co/organisation/depot</code></li><li>LM Studio : rechercher l’identifiant du dépôt dans l’onglet de recherche.</li></ul>'
            '<p class="sm">Chaque dépôt propose plusieurs quantifications (Q4, Q5, Q8…) : la taille du fichier choisi, visible sur la fiche Hugging Face, donne la mémoire nécessaire.</p>')
    write("guides/gguf.html", page(site, "guides/gguf.html", t, f"{len(gg)} modèles au format GGUF suivis par Radar IA : modèle de base, paramètres, contexte, licence, vérifiés sur Hugging Face.",
                                   body, crumbs=crumbs("GGUF"), nav_key="guides.html", md_path="guides/gguf.md", jsonld=[ld_itemlist(site, t, gg, "guides/gguf.html")] if gg else None))
    write_md("guides/gguf.md", t, f"# {t}\n\n" + "\n".join(f"- [{i['nom']}]({site.abs(site.item_page(i))}) — base : {', '.join(b['id'] for b in site.v(i).get('modeleBase') or []) or 'n.c.'} ; {fmt_params(site.v(i).get('parametres')) or 'n.c.'} ; licence {site.lic(i) or 'non déclarée'}" for i in gg))
    guides.append((t, "guides/gguf.html", f"{len(gg)} dépôts GGUF"))

    # Familles : un modèle de base et ses dérivés suivis
    suivis = site.by_hf()
    for bid, ders in site.familles().items():
        p = site.fam_page(bid)
        nom = bid.split("/", 1)[-1]
        t = titre_court(f"{nom} : dérivés, GGUF et fine-tunes ({mois})", f"{nom} : dérivés et fine-tunes", f"Dérivés de {nom}", nom)
        base = suivis.get(bid)
        tete = (f'<p>Modèle de base suivi : <a href="../{site.item_page(base)}"><strong>{esc(base["nom"])}</strong></a> {score_badge(base.get("score"))} — {esc(base.get("resume"))}</p>' if base
                else f'<p>Modèle de base : <a href="https://huggingface.co/{esc(bid)}" rel="noopener">{esc(bid)}</a> (non suivi par Radar IA).</p>')
        body = (f'<h1>{esc(t)}</h1><p class="mut" style="max-width:70ch">Les éléments suivis par Radar IA qui déclarent <code>{esc(bid)}</code> comme modèle de base sur Hugging Face, '
                f'avec la nature du lien (quantification, fine-tune, adaptateur, fusion).</p>{note}{tete}{table_faits(site, ders, "../", ("relation", "params", "licence", "dl", "score"))}')
        write(p, page(site, p, t, f"{len(ders)} dérivés de {bid} suivis par Radar IA : quantifications GGUF, fine-tunes, adaptateurs, avec licence et téléchargements.",
                      body, crumbs=[("Accueil", "index.html"), ("Guides", "guides.html"), (nom, None)], nav_key="guides.html",
                      jsonld=[ld_itemlist(site, t, [d for d, _ in ders], p)]))
        guides.append((t, p, f"{len(ders)} dérivés suivis"))

    # Éditeurs : une page par compte qui publie au moins deux éléments suivis, et un annuaire
    eds = site.editeurs()
    lignes = []
    for acc, its in eds.items():
        nom = site.org(its[0])
        if len(its) >= 2:
            p = site.ed_page_url(acc)
            t = titre_court(f"Modèles {nom} suivis par Radar IA ({mois})", f"Modèles {nom} suivis par Radar IA", f"Modèles {nom}", nom)
            body = (f'<h1>{esc(t)}</h1><p class="mut" style="max-width:70ch">{len(its)} éléments publiés par le compte Hugging Face '
                    f'<a href="https://huggingface.co/{esc(acc)}" rel="noopener"><code>{esc(acc)}</code></a> et suivis par Radar IA, classés par Score Radar.</p>{note}'
                    f'{table_faits(site, its, "../", ("params", "licence", "dl", "score"))}'
                    f'<section><div class="sh"><h2>En cartes</h2></div><div class="cards">{"".join(item_card(site, x, "../") for x in its)}</div></section>')
            write(p, page(site, p, t, f"{len(its)} modèles, datasets ou Spaces de {nom} suivis par Radar IA : taille, licence, téléchargements, Score Radar vérifiés sur Hugging Face.",
                          body, crumbs=[("Accueil", "index.html"), ("Éditeurs", "editeurs.html"), (nom, None)], nav_key="guides.html",
                          jsonld=[ld_itemlist(site, t, its, p)]))
            lignes.append(f'<li><a href="{p}"><strong>{esc(nom)}</strong></a> <span class="mut mono sm">{esc(acc)} · {len(its)} éléments</span></li>')
        else:
            lignes.append(f'<li><a href="{site.item_page(its[0])}">{esc(nom)}</a> <span class="mut mono sm">{esc(acc)} · {esc(its[0].get("nom"))}</span></li>')
    t = f"Éditeurs de modèles IA ouverts suivis ({mois})"
    write("editeurs.html", page(site, "editeurs.html", t, f"Les {len(eds)} éditeurs (organisations et comptes Hugging Face) dont Radar IA suit au moins un modèle, dataset ou Space.",
                                f'<h1>{esc(t)}</h1><p class="mut" style="max-width:70ch">Organisations et comptes Hugging Face dont au moins un élément est suivi. Noms vérifiés sur Hugging Face.</p>{note}<ul class="ess">{"".join(lignes)}</ul>',
                                crumbs=[("Accueil", "index.html"), ("Guides", "guides.html"), ("Éditeurs", None)], nav_key="guides.html"))
    guides.append((t, "editeurs.html", f"{len(eds)} éditeurs, {sum(1 for v in eds.values() if len(v) >= 2)} avec une page dédiée"))

    # Comparatifs « X ou Y ? » : faits vérifiés et phrases calculées à partir d'eux, sans verdict de qualité
    cmp_liens = []
    for a, b, dk in site.comparatifs():
        p = site.cmp_page(a, b)
        va, vb = site.v(a), site.v(b)
        t = titre_court(f"{a['nom']} ou {b['nom']} ? Comparatif ({mois})", f"{a['nom']} ou {b['nom']} ? Comparatif", f"{a['nom']} ou {b['nom']} ?")
        def faits_dict(it):
            _, md = fiche_faits(site, it, "../")
            return dict(l[2:].split(" : ", 1) for l in md.strip().split("\n") if " : " in l)
        da, db = faits_dict(a), faits_dict(b)
        cles = list(da) + [k for k in db if k not in da]
        lignes = "".join(f'<tr><th scope="row">{esc(k)}</th><td>{esc(da.get(k, "—"))}</td><td>{esc(db.get(k, "—"))}</td></tr>' for k in cles)
        lignes += f'<tr><th scope="row">Score Radar</th><td>{score_badge(a.get("score"))}</td><td>{score_badge(b.get("score"))}</td></tr>'
        constats = []
        sa, sb = a.get("score"), b.get("score")
        if sa is not None and sb is not None and sa != sb:
            h = a if sa > sb else b
            constats.append(f"Score Radar plus élevé pour {h['nom']} ({max(sa, sb)} contre {min(sa, sb)}).")
        try:
            r = float(va["downloads"]) / float(vb["downloads"])
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            r = None
        if r and (r >= 1.5 or r <= 1 / 1.5):
            h, l, k = (a, b, r) if r > 1 else (b, a, 1 / r)
            constats.append(f"{h['nom']} est {str(round(k, 1)).replace('.', ',')} fois plus téléchargé que {l['nom']} sur les 30 derniers jours, selon Hugging Face.")
        pa, pb = va.get("parametres"), vb.get("parametres")
        if pa and pb and pa != pb:
            le = a if pa < pb else b
            constats.append(f"{le['nom']} est le plus léger : {fmt_params(min(pa, pb))} paramètres contre {fmt_params(max(pa, pb))}.")
        la, lb = site.lic(a), site.lic(b)
        if la and lb:
            constats.append(f"Même licence : {la}." if la == lb else f"Licences différentes : {la} pour {a['nom']}, {lb} pour {b['nom']}.")
        fa, fb = "fr" in (va.get("langues") or []), "fr" in (vb.get("langues") or [])
        if fa != fb:
            constats.append(f"Seul {(a if fa else b)['nom']} déclare le français sur Hugging Face.")
        ga, gb = "GGUF" in (va.get("formats") or []), "GGUF" in (vb.get("formats") or [])
        if ga != gb:
            constats.append(f"Seul {(a if ga else b)['nom']} est publié au format GGUF (llama.cpp, Ollama, LM Studio).")
        body = (f'<div class="eb">Comparatif · {esc(site.dom_name(dk))}</div><h1 style="margin-top:6px">{esc(a["nom"])} ou {esc(b["nom"])} ?</h1>'
                f'<p class="mut" style="max-width:70ch">Deux des modèles les mieux classés du domaine « {esc(site.dom_name(dk))} » sur Radar IA, comparés point par point. '
                f'Les faits viennent des fiches Hugging Face ; aucun jugement de qualité n’est inventé : testez sur vos propres données.</p>{note}'
                + (f'<section><div class="sh"><h2>Ce que disent les chiffres</h2></div><ul class="ess">{"".join(f"<li>{esc(x)}</li>" for x in constats)}</ul></section>' if constats else "")
                + f'<section><div class="sh"><h2>Fiche contre fiche</h2></div><div class="tw"><table style="min-width:520px"><thead><tr><th></th>'
                f'<th><a href="../{site.item_page(a)}">{esc(a["nom"])}</a></th><th><a href="../{site.item_page(b)}">{esc(b["nom"])}</a></th></tr></thead><tbody>{lignes}</tbody></table></div></section>'
                f'<section><div class="sh"><h2>Pourquoi ils comptent</h2></div><div class="cards">{item_card(site, a, "../")}{item_card(site, b, "../")}</div></section>')
        write(p, page(site, p, t, f"{a['nom']} ou {b['nom']} : paramètres, licence, langues, formats, téléchargements et Score Radar comparés, d'après Hugging Face.",
                      body, crumbs=[("Accueil", "index.html"), ("Comparatifs", "comparer.html"), (f"{a['nom']} ou {b['nom']}", None)], nav_key="guides.html",
                      jsonld=[ld_itemlist(site, t, [a, b], p)]))
        cmp_liens.append((dk, a, b, p))
    if cmp_liens:
        par_dom: dict[str, list] = {}
        for dk, a, b, p in cmp_liens:
            par_dom.setdefault(dk, []).append(f'<li><a href="{p}"><strong>{esc(a["nom"])}</strong> ou <strong>{esc(b["nom"])}</strong> ?</a></li>')
        t = f"Comparatifs de modèles IA open source ({mois})"
        write("comparer.html", page(site, "comparer.html", t, f"{len(cmp_liens)} comparatifs entre les modèles open source les mieux classés de chaque domaine : faits vérifiés sur Hugging Face.",
                                    f'<h1>{esc(t)}</h1><p class="mut" style="max-width:70ch">Les modèles les mieux classés de chaque domaine, comparés deux à deux sur des faits vérifiables.</p>'
                                    + "".join(f'<section><div class="sh"><h2>{esc(site.dom_name(dk))}</h2></div><ul class="ess">{"".join(v)}</ul></section>' for dk, v in par_dom.items()),
                                    crumbs=[("Accueil", "index.html"), ("Guides", "guides.html"), ("Comparatifs", None)], nav_key="guides.html"))
        guides.append((t, "comparer.html", f"{len(cmp_liens)} comparatifs"))

    # Glossaire : définitions générales + exemples tirés des faits vérifiés
    def exemples(cle):
        def rel(r): return [i for i in tous if any(b.get("relation") == r for b in site.v(i).get("modeleBase") or [])]
        def fmt(f): return [i for i in tous if f in (site.v(i).get("formats") or [])]
        def tache(*ts): return [i for i in tous if any(t in (site.v(i).get("tache") or "") for t in ts)]
        return {"gguf": fmt("GGUF"), "safetensors": fmt("safetensors"), "mlx": fmt("MLX"), "quantification": rel("quantized"),
                "fine-tune": rel("finetune"), "adaptateur": rel("adapter"), "fusion": rel("merge"),
                "modele-de-base": [i for i in tous if site.v(i).get("modeleBase")],
                "contexte": [i for i in tous if site.v(i).get("contexte")], "acces-restreint": [i for i in tous if site.v(i).get("acces") == "sur demande"],
                "licence-permissive": [i for i in tous if (site.lic(i) or "").lower() in ("apache-2.0", "mit")],
                "embedding": tache("feature-extraction", "sentence-similarity"), "asr": tache("automatic-speech-recognition"),
                "vision-langage": tache("image-text-to-text"), "ocr": site.items_in("documents"),
                "space": [i for i in tous if i.get("type") == "space"], "dataset": [i for i in tous if i.get("type") == "dataset"]}.get(cle, [])
    dts = []
    for cle, terme, definition in GLOSSAIRE:
        ex = exemples(cle)[:5]
        ex_html = (' <span class="sm mut">Exemples suivis : ' + ", ".join(f'<a href="{site.item_page(i)}">{esc(i["nom"])}</a>' for i in ex) + ".</span>") if ex else ""
        dts.append(f'<dt id="{cle}">{esc(terme)}</dt><dd>{esc(definition)}{ex_html}</dd>')
    t = "Glossaire de l'IA ouverte : GGUF, quantification, LoRA, MoE"
    ld_gl = {"@context": "https://schema.org", "@type": "DefinedTermSet", "name": t, "url": site.abs("glossaire.html"), "inLanguage": "fr-FR",
             "hasDefinedTerm": [{"@type": "DefinedTerm", "name": terme, "description": d, "url": site.abs(f"glossaire.html#{cle}")} for cle, terme, d in GLOSSAIRE]}
    write("glossaire.html", page(site, "glossaire.html", t, "Les mots de l'IA open source expliqués simplement : GGUF, quantification, fine-tune, LoRA, MoE, contexte, licences, RAG, OCR, avec des exemples de modèles suivis.",
                                 f'<h1>{esc(t)}</h1><p class="mut" style="max-width:70ch">Les termes qu’on croise sur les fiches de modèles, définis en une ou deux phrases. Les exemples sont tirés des éléments suivis par Radar IA.</p><dl class="faq">{"".join(dts)}</dl>',
                                 crumbs=[("Accueil", "index.html"), ("Guides", "guides.html"), ("Glossaire", None)], nav_key="guides.html", md_path="glossaire.md", jsonld=[ld_gl]))
    write_md("glossaire.md", t, f"# {t}\n\n" + "\n\n".join(f"## {terme}\n\n{d}" for _, terme, d in GLOSSAIRE))
    guides.append((t, "glossaire.html", f"{len(GLOSSAIRE)} termes définis"))

    # Nouveautés : entrées dans le radar (premiereVue) et créations récentes vérifiées sur Hugging Face
    par_jour: dict[str, list] = {}
    for i in tous:
        if i.get("premiereVue"): par_jour.setdefault(i["premiereVue"][:10], []).append(i)
    try:
        ref = date.fromisoformat(site.today)
        recents = sorted([i for i in tous if site.v(i).get("creeLe") and (ref - date.fromisoformat(site.v(i)["creeLe"])).days <= 30],
                         key=lambda i: site.v(i)["creeLe"], reverse=True)
    except ValueError:
        recents = []
    t = f"Nouveaux modèles IA open source repérés ({mois})"
    secs = "".join(f'<section><div class="sh"><h2>Entrés dans le radar le {d_long(j)}</h2><span class="eb">{len(v)} élément(s)</span></div>'
                   f'<div class="cards">{"".join(item_card(site, x, "") for x in v[:8])}</div>'
                   + (f'<p class="sm mut">Et {len(v) - 8} autres : voir l’<a href="modeles-a-z.html">index A-Z</a>.</p>' if len(v) > 8 else "") + '</section>' for j, v in sorted(par_jour.items(), reverse=True)[:5])
    rec = (f'<section><div class="sh"><h2>Créés sur Hugging Face depuis 30 jours</h2><span class="eb">{len(recents)} élément(s)</span></div>'
           f'<div class="tw"><table style="min-width:560px"><thead><tr><th>Élément</th><th>Créé le</th><th>Paramètres</th><th>Licence</th><th class="r">Score</th></tr></thead><tbody>'
           + "".join(f'<tr><td><a href="{site.item_page(i)}"><strong>{esc(i["nom"])}</strong></a><div class="sm mut mono">{esc(site.org(i))}</div></td>'
                     f'<td class="mono sm">{d_short(site.v(i)["creeLe"])}</td><td class="r num">{esc(fmt_params(site.v(i).get("parametres")) or "—")}</td>'
                     f'<td class="sm">{esc(site.lic(i) or "non déclarée")}</td><td class="r">{score_badge(i.get("score"))}</td></tr>' for i in recents[:40])
           + '</tbody></table></div></section>') if recents else ""
    body = (f'<h1>{esc(t)}</h1><p class="mut" style="max-width:70ch">Les éléments entrés dans le radar de Radar IA, jour par jour, et ceux créés sur Hugging Face au cours des 30 derniers jours (date vérifiée). '
            f'<a href="feed.xml">Flux RSS</a> · <a href="domaines.html">flux par domaine</a>.</p>{note}{rec}{secs}')
    write("nouveautes.html", page(site, "nouveautes.html", t, f"Les derniers modèles, datasets et Spaces IA open source repérés par Radar IA : {len(recents)} créés sur Hugging Face depuis 30 jours, avec licence et taille vérifiées.",
                                  body, crumbs=[("Accueil", "index.html"), ("Nouveautés", None)], nav_key="guides.html",
                                  jsonld=[ld_itemlist(site, t, recents[:30], "nouveautes.html")] if recents else None))
    guides.append((t, "nouveautes.html", f"{len(recents)} créés depuis 30 jours"))

    # Index A-Z de tous les éléments suivis
    def lettre(nom):
        c = unicodedata.normalize("NFKD", (nom or "?").strip())[:1].upper()
        return c if c.isalpha() else "#"
    az: dict[str, list] = {}
    for i in sorted(tous, key=lambda i: (i.get("nom") or "").lower()):
        az.setdefault(lettre(i.get("nom")), []).append(i)
    ordre_az = sorted(az, key=lambda c: (c == "#", c))
    nav_az = " ".join(f'<a href="#l-{"0" if c == "#" else c}">{c}</a>' for c in ordre_az)
    secs = "".join(f'<section id="l-{"0" if c == "#" else c}"><div class="sh"><h2>{c}</h2><span class="eb">{len(az[c])}</span></div><ul class="ess">'
                   + "".join(f'<li><a href="{site.item_page(i)}"><strong>{esc(i["nom"])}</strong></a> <span class="mut mono sm">{esc(site.org(i))} · '
                             f'{esc(TYPE_LABEL.get(i.get("type"), ""))}{(" · " + esc(site.taille(i))) if site.taille(i) else ""}</span></li>' for i in az[c])
                   + "</ul></section>" for c in ordre_az)
    t = "Index A-Z des modèles IA open source suivis"
    write("modeles-a-z.html", page(site, "modeles-a-z.html", t, f"Les {len(tous)} modèles, datasets et Spaces Hugging Face suivis par Radar IA, par ordre alphabétique, avec éditeur et taille vérifiés.",
                                   f'<h1>{esc(t)}</h1><p class="mut">{len(tous)} éléments. Voir aussi l’<a href="modeles.html">annuaire par Score Radar</a>.</p>'
                                   f'<p class="mono" style="font-size:1rem;word-spacing:.35em">{nav_az}</p>{secs}',
                                   crumbs=[("Accueil", "index.html"), ("Modèles", "modeles.html"), ("Index A-Z", None)], nav_key="modeles.html"))
    guides.append((t, "modeles-a-z.html", f"{len(tous)} éléments"))

    # Pages par tâche (étiquette pipeline vérifiée sur Hugging Face), avec FAQ calculée
    par_tache: dict[str, list] = {}
    for i in tous:
        tk = site.v(i).get("tache") if i.get("type") == "model" else None
        if tk in TACHES: par_tache.setdefault(tk, []).append(i)
    taches_liens = []
    for tk, its in sorted(par_tache.items(), key=lambda kv: -len(kv[1])):
        if len(its) < 2: continue
        slug, nom_t = TACHES[tk]
        p = f"taches/{slug}.html"
        t = titre_court(f"Modèles open source : {nom_t} ({mois})", f"Modèles open source : {nom_t.split(' (')[0]} ({mois})", f"{nom_t.split(' (')[0]} : modèles open source")
        perm = [i for i in its if (site.lic(i) or "").lower() in ("apache-2.0", "mit")]
        gg = [i for i in its if "GGUF" in (site.v(i).get("formats") or [])]
        fr = [i for i in its if "fr" in (site.v(i).get("langues") or [])]
        leg = sorted([i for i in its if site.v(i).get("parametres")], key=lambda i: site.v(i)["parametres"])
        lien = lambda i: f'<a href="../{site.item_page(i)}">{esc(i["nom"])}</a>'
        qas = [(f"Quel modèle « {nom_t} » open source est le mieux classé ?", f"{lien(its[0])} ({site.org(its[0])}), Score Radar {its[0].get('score')}/100, parmi {len(its)} modèles suivis.")]
        qas.append((f"Lesquels sont sous licence Apache 2.0 ou MIT ?", (", ".join(lien(i) for i in perm[:6]) + ".") if perm else "Aucun des modèles suivis pour cette tâche."))
        if leg: qas.append(("Quel est le plus léger ?", f"{lien(leg[0])} : {fmt_params(site.v(leg[0])['parametres'])} paramètres déclarés."))
        qas.append(("Lesquels existent au format GGUF pour un PC ?", (", ".join(lien(i) for i in gg[:6]) + ".") if gg else "Aucun dépôt GGUF suivi pour cette tâche pour l’instant."))
        qas.append(("Lesquels déclarent le français ?", (", ".join(lien(i) for i in fr[:6]) + ".") if fr else "Aucun ne déclare le français sur Hugging Face ; certains sont multilingues, à vérifier sur leur fiche."))
        body = (f'<div class="eb">Tâche · <code>{esc(tk)}</code></div><h1 style="margin-top:6px">{esc(nom_t)} : modèles open source</h1>'
                f'<p class="mut" style="max-width:70ch">{len(its)} modèles suivis par Radar IA déclarent cette tâche sur Hugging Face. Classés par Score Radar.</p>{note}'
                f'{table_faits(site, its, "../", ("params", "licence", "langues", "dl", "score"))}'
                f'<section><div class="sh"><h2>Questions fréquentes</h2></div><dl class="faq">{"".join(f"<dt>{esc(q)}</dt><dd>{a}</dd>" for q, a in qas)}</dl></section>')
        write(p, page(site, p, t, f"{len(its)} modèles open source de {nom_t.lower()} suivis : licence, taille, langues, GGUF et Score Radar vérifiés sur Hugging Face.",
                      body, crumbs=[("Accueil", "index.html"), ("Guides", "guides.html"), (nom_t, None)], nav_key="guides.html",
                      jsonld=[ld_itemlist(site, t, its, p), ld_faq(qas)]))
        taches_liens.append(f'<li><a href="{p}"><strong>{esc(nom_t)}</strong></a> <span class="mut mono sm">{len(its)} modèles</span></li>')
        guides.append((t, p, f"{len(its)} modèles"))

    # Index des guides
    body = ('<h1>Guides</h1><p class="mut" style="max-width:70ch">Des listes régénérées chaque jour à partir des faits déclarés sur Hugging Face : langues, licences, formats, familles de modèles. Rien n’y est saisi à la main.</p>'
            + '<ul class="ess">' + "".join(f'<li><a href="{gp}"><strong>{esc(gt)}</strong></a> — {esc(gr)}</li>' for gt, gp, gr in guides) + "</ul>")
    write("guides.html", page(site, "guides.html", "Guides : modèles IA open source par langue, licence, format", "Guides Radar IA générés depuis les données Hugging Face : modèles en français, licences, GGUF, familles de modèles.",
                              body, crumbs=[("Accueil", "index.html"), ("Guides", None)]))
    return guides

# ------------------------------------------------------------------ pages

def build(site: Site, out: Path, artifact=False):
    if out.exists(): shutil.rmtree(out)
    (out / "assets").mkdir(parents=True)
    (out / "assets/style.css").write_text(CSS.strip(), encoding="utf-8")
    (out / "assets/favicon.svg").write_text(FAVICON, encoding="utf-8")
    urls: list[tuple[str, str]] = []  # (path, lastmod)
    md_docs: list[tuple[str, str, str]] = []  # (title, path_md, markdown)

    def write(path, content, lastmod=None):
        p = out / path; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content, encoding="utf-8")
        if path.endswith(".html"): urls.append((path, (lastmod or site.today)[:10]))

    def write_md(path_md, title, md):
        (out / path_md).parent.mkdir(parents=True, exist_ok=True); (out / path_md).write_text(md, encoding="utf-8"); md_docs.append((title, path_md, md))

    ed = site.ed_sorted[0] if site.ed_sorted else None

    # --- Une
    r = ""
    if ed:
        ess = "".join(f"<li>{esc(x.get('texte'))}</li>" for x in ed.get("essentiel") or [])
        tester = "".join(f'<li><a href="{site.item_page(site.items[t["itemId"]])}"><strong>{esc(site.items[t["itemId"]]["nom"])}</strong></a> — {esc(t.get("texte"))}</li>'
                         for t in ed.get("aTester") or [] if t.get("itemId") in site.items)
        top = [site.items[i] for i in ed.get("topIds") or [] if i in site.items][:6]
        r = f"""<section class="lead"><div><div class="eb">Édition du {d_long(ed['date'])}</div><h1>{esc(ed.get('titre'))}</h1><ol class="ess">{ess}</ol></div>
<aside>{radar_panel(site)}<div class="box" style="margin-top:16px"><h2 style="font-size:1rem">Tendance de fond</h2><p class="sm" style="margin:6px 0 0">{esc(ed.get('tendance'))}</p></div>
{f'<div style="margin-top:16px"><div class="eb">À tester</div><ul class="sm" style="padding-left:18px">{tester}</ul></div>' if tester else ''}</aside></section>
<section><div class="sh"><h2>Les modèles qui comptent aujourd'hui</h2><a class="mono sm" href="classements.html">classements →</a></div><div class="cards">{''.join(item_card(site, it, '', i+1) for i, it in enumerate(top))}</div></section>"""
    r += f"""<section><div class="sh"><h2>Derniers articles</h2><a class="mono sm" href="articles.html">tous →</a></div><div class="cards">{''.join(art_card(site, a, '') for a in site.art_sorted[:6]) or '<p class="mut">Premiers articles demain matin.</p>'}</div></section>
<section><div class="sh"><h2>Classement du jour — top 10</h2><span class="eb">Score Radar /100</span></div>{ranking_table(site, (site.classements.get('jour') or {}).get('entrees') or [], '', 10)}</section>
<section><div class="sh"><h2>Guides vérifiés</h2><a class="mono sm" href="guides.html">tous →</a></div><p class="sm">Listes régénérées chaque jour depuis les données Hugging Face : <a href="nouveautes.html">nouveautés</a> · <a href="guides/francais.html">modèles qui gèrent le français</a> · <a href="guides/licences.html">licences et usage en entreprise</a> · <a href="guides/gguf.html">modèles GGUF à lancer en local</a>.</p></section>
<section class="box"><p class="sm" style="margin:0"><strong>{SITE_NAME}</strong> — {esc(SITE_DESC)} Données ouvertes : <a href="pour-les-ia.html">API JSON, llms.txt, RSS</a>.</p></section>
{bloc_abonnement(site, '')}{bloc_sponsor(site, '')}"""
    title_home = f"{SITE_NAME} — tendances IA open source du {d_short(site.today)}"
    desc_home = (ed.get("titre") + ". " if ed else "") + SITE_DESC
    write("index.html", page(site, "index.html", title_home, desc_home, r, md_path="index.md", artifact_shell=artifact,
                             jsonld=[ld_itemlist(site, "Top du jour", [site.items[i] for i in (ed or {}).get("topIds", []) if i in site.items], "index.html")]))
    md = f"# {SITE_NAME}\n\n> {SITE_DESC}\n\n"
    if ed:
        md += f"## Édition du {d_long(ed['date'])} — {ed.get('titre')}\n\n" + "\n".join(f"- {x.get('texte')}" for x in ed.get("essentiel") or []) + f"\n\n**Tendance de fond.** {ed.get('tendance')}\n"
    md += "\n## Derniers articles\n\n" + "\n".join(f"- [{a['titre']}]({site.abs(site.art_page(a))}) — {a.get('chapo')}" for a in site.art_sorted[:10])
    write_md("index.md", f"{SITE_NAME} — accueil", md)

    # --- Classements
    r = '<h1>Classements des modèles IA ouverts</h1><p class="mut">Score Radar sur 100 : popularité, diffusion, fraîcheur et pertinence pour l\'IA pratique (local, documents, agents, audio, code, français). <a href="methode.html">Méthode</a>.</p>'
    md = "# Classements Radar IA\n\nScore Radar /100 = 40·popularité + 30·diffusion + 20·fraîcheur + 10·pertinence.\n"
    for per, lab in PERIODES:
        cl = site.classements.get(per) or {}
        ent = cl.get("entrees") or []
        r += (f'<section id="{per}"><div class="sh"><h2>{esc(cl.get("titre") or lab)}</h2><a href="classements/{per}.html">classement complet ({len(ent)}) →</a></div>'
              f'{ranking_table(site, ent, "", 10)}</section>')
        # page complète de la période (allège la page d'ensemble)
        pp = f"classements/{per}.html"
        titre_p = f"Classement {lab.lower()} des modèles IA open source" if per != "jour" else "Classement du jour des modèles IA open source"
        write(pp, page(site, pp, titre_p, f"{len(ent)} modèles, datasets et Spaces Hugging Face classés par Score Radar ({lab.lower()}) : likes, téléchargements, évolution.",
                       f'<h1>{esc(cl.get("titre") or titre_p)}</h1><p class="mut">Période : {esc(lab)} · Score Radar sur 100 (<a href="../methode.html">méthode</a>). '
                       + " · ".join(f'<a href="{q}.html">{esc(l)}</a>' for q, l in PERIODES if q != per) + f'</p>{ranking_table(site, ent, "../")}',
                       crumbs=[("Accueil", "index.html"), ("Classements", "classements.html"), (lab, None)], nav_key="classements.html",
                       jsonld=[ld_itemlist(site, titre_p, ranking_items(site, per), pp)] if ranking_items(site, per) else None))
        md += f"\n## {cl.get('titre') or lab}\n\n| # | Élément | Organisation | Score | Likes | Téléchargements |\n|---|---|---|---|---|---|\n"
        for e in cl.get("entrees") or []:
            it = site.items.get(e.get("itemId"))
            if it: md += f"| {e.get('rang')} | [{it['nom']}]({site.hf_url(it)}) | {site.org(it)} | {e.get('score')} | {it.get('likes')} | {it.get('downloads')} |\n"
    write("classements.html", page(site, "classements.html", "Classements des modèles IA open source (jour, 7 j, 30 j, 3 mois)",
          "Classement quotidien des modèles, datasets et Spaces Hugging Face par Score Radar : popularité, téléchargements, fraîcheur, pertinence.",
          r, md_path="classements.md", artifact_shell=False, crumbs=[("Accueil", "index.html"), ("Classements", None)],
          jsonld=[ld_itemlist(site, f"Classement {lab}", ranking_items(site, per)[:10], f"classements/{per}.html") for per, lab in PERIODES if ranking_items(site, per)]))
    write_md("classements.md", "Classements", md)

    # --- Articles
    r = '<h1>Articles</h1><p class="mut">Analyses rédigées chaque matin à partir des fiches Hugging Face, un article par domaine actif.</p>'
    for dk, dv in site.domaines.items():
        arts = [a for a in site.art_sorted if a.get("domaine") == dk]
        if arts:
            r += f'<section><div class="sh"><h2><a href="{site.dom_page(dk)}">{esc(dv.get("nom"))}</a></h2></div><div class="cards">{"".join(art_card(site, a, "") for a in arts)}</div></section>'
    write("articles.html", page(site, "articles.html", "Articles : analyses de modèles IA open source", "Toutes les analyses Radar IA : LLM en local, OCR et documents, agents, audio, code, multilingue.",
          r, crumbs=[("Accueil", "index.html"), ("Articles", None)]))
    for a in site.art_sorted:
        p = site.art_page(a)
        rel = [site.items[i] for i in a.get("itemIds") or [] if i in site.items]
        src = "".join(f'<li><a href="{esc(safe_url(s.get("url")))}" rel="noopener">{esc(s.get("titre") or s.get("url"))}</a></li>' for s in a.get("sources") or [])
        body = f"""<article class="a"><div class="eb"><a href="../{site.dom_page(a.get('domaine'))}">{esc(site.dom_name(a.get('domaine')))}</a></div><h1 style="margin-top:6px">{esc(a.get('titre'))}</h1>
<p class="chapo">{esc(a.get('chapo'))}</p><div class="by"><time datetime="{esc(a.get('date'))}">{d_long(a.get('date'))}</time><span>{esc(a.get('auteur'))}</span><span>{esc(a.get('tempsLecture'))} min</span><a href="{a['_slug']}.md">version Markdown</a></div>
<div class="body">{sanitize(a.get('corpsHtml'))}</div>{f'<h2 style="margin-top:28px">Sources</h2><ol class="sm">{src}</ol>' if src else ''}{bloc_partage(site, site.abs(p), a.get('titre') or '')}{bloc_sponsor(site, '../')}</article>
{f'<section><div class="sh"><h2>Éléments cités</h2></div><div class="cards">{"".join(item_card(site, it, "../") for it in rel)}</div></section>' if rel else ''}{bloc_abonnement(site, '../')}"""
        write(p, page(site, p, a.get("titre"), a.get("chapo"), body, og_type="article", md_path=f"articles/{a['_slug']}.md",
                      crumbs=[("Accueil", "index.html"), ("Articles", "articles.html"), (site.dom_name(a.get("domaine")), site.dom_page(a.get("domaine"))), (clip(a.get("titre"), 50), None)],
                      jsonld=[ld_article(site, a)], nav_key="articles.html", published=a.get("publieLe") or a.get("date"), modified=a.get("publieLe")), a.get("date"))
        md = (f"# {a.get('titre')}\n\n> {a.get('chapo')}\n\n*{d_long(a.get('date'))} · {site.dom_name(a.get('domaine'))} · {SITE_NAME}* — {site.abs(p)}\n\n"
              + html_to_md(sanitize(a.get("corpsHtml"))) + "\n\n## Sources\n\n" + "\n".join(f"- [{s.get('titre')}]({s.get('url')})" for s in a.get("sources") or []))
        write_md(f"articles/{a['_slug']}.md", a.get("titre"), md)

    # --- Modèles (longue traîne)
    all_items = sorted(site.items.values(), key=lambda i: -(i.get("score") or 0))
    MAX_ANNUAIRE = 60  # au-delà, page > 60 ko : la liste complète est l'index A-Z
    rows = "".join(f"""<tr><td><a href="{site.item_page(it)}"><strong>{esc(it['nom'])}</strong></a>{' <span class="star">★</span>' if it.get('pertinent') else ''}<div class="sm mut mono">{esc(site.org(it))}</div></td><td>{esc(TYPE_LABEL.get(it.get('type'), ''))}</td><td>{esc(it.get('tache'))}</td><td class="mono sm">{esc(site.taille(it) or '—')}</td><td class="mono sm">{esc(site.lic(it) or '—')}</td><td class="r">{score_badge(it.get('score'))}</td></tr>""" for it in all_items[:MAX_ANNUAIRE])
    write("modeles.html", page(site, "modeles.html", "Annuaire des modèles IA suivis : taille, licence, score", f"{len(all_items)} modèles, datasets et Spaces Hugging Face suivis par Radar IA, avec taille, licence, tâche et Score Radar.",
          f'<h1>Modèles, datasets et Spaces suivis</h1><p class="mut">{len(all_items)} éléments suivis{f" ; les {MAX_ANNUAIRE} mieux classés ci-dessous" if len(all_items) > MAX_ANNUAIRE else ""}, triés par Score Radar. Liste complète : <a href="modeles-a-z.html">index A-Z</a>. ★ = utile pour l\'IA pratique (local, documents, agents, audio, code, français).</p><div class="tw"><table><thead><tr><th>Nom</th><th>Type</th><th>Tâche</th><th>Taille</th><th>Licence</th><th class="r">Score</th></tr></thead><tbody>{rows}</tbody></table></div>',
          crumbs=[("Accueil", "index.html"), ("Modèles", None)], jsonld=[ld_itemlist(site, "Modèles suivis par Radar IA", all_items[:MAX_ANNUAIRE], "modeles.html")]))
    for it in all_items:
        p = site.item_page(it)
        arts = [a for a in site.art_sorted if it["_id"] in (a.get("itemIds") or [])]
        hist = it.get("historique") or []
        hist_rows = "".join(f'<tr><td class="num">{d_short(h.get("date"))}</td><td class="r num">{fmt_n(h.get("likes"))}</td><td class="r num">{fmt_n(h.get("downloads"))}</td><td class="r">{score_badge(h.get("score"))}</td></tr>' for h in reversed(hist[-15:]))
        same = [x for x in site.items_in((it.get("domaines") or ["_"])[0]) if x["_id"] != it["_id"]][:4]
        tl = TYPE_LABEL.get(it.get("type"), "Modèle")
        desc = f"{it['nom']} ({site.org(it)}) : {clip(it.get('resume') or '', 110)} Taille {site.taille(it) or 'n.c.'}, licence {site.lic(it) or 'n.c.'}, Score Radar {it.get('score')}/100."
        kv, kv_md = fiche_faits(site, it, "../")
        body = f"""<div class="eb">{esc(tl)} · {esc(site.org(it))}</div><h1 style="margin:6px 0 10px">{esc(it['nom'])} {score_badge(it.get('score'))}</h1>
<p style="max-width:70ch;font-size:1.08rem">{esc(it.get('resume'))}</p>
<div class="lead" style="margin-top:18px"><div><dl class="kv">{kv}<dt>Domaines</dt><dd>{''.join(dom_chip(site, d, '../') for d in it.get('domaines') or [])}</dd>
<dt>Pertinent IA pratique</dt><dd>{'oui ★' if it.get('pertinent') else 'non'}</dd><dt>Fiche officielle</dt><dd><a href="{esc(site.hf_url(it))}" rel="noopener">{esc(site.hf_url(it))}</a></dd></dl>
{f'<p class="sm mut" style="margin-top:8px">Licence, dates, langues, paramètres, formats, modèle de base et compteurs vérifiés sur l’API Hugging Face le {d_short(site.v(it)["verifieLe"])}.</p>' if site.v(it).get("verifieLe") else ''}
<p class="box sm" style="margin-top:16px"><strong>Pourquoi ça compte.</strong> {esc(it.get('pourquoi'))}</p>{bloc_affiliation(site, it)}</div>
<aside>{f'<h2 style="font-size:1rem">Historique des relevés</h2><div class="tw" style="margin-top:8px"><table style="min-width:0"><thead><tr><th>Date</th><th class="r">Likes</th><th class="r">Téléch.</th><th class="r">Score</th></tr></thead><tbody>{hist_rows}</tbody></table></div>' if hist_rows else ''}</aside></div>
{(lambda cs: f'<section><div class="sh"><h2>Comparer</h2></div><ul class="ess">{cs}</ul></section>' if cs else '')("".join(f'<li><a href="../{site.cmp_page(x, y)}">{esc(x["nom"])} ou {esc(y["nom"])} ?</a></li>' for x, y, _ in site.comparatifs() if it["_id"] in (x["_id"], y["_id"])))}
{f'<section><div class="sh"><h2>Articles qui en parlent</h2></div><div class="cards">{"".join(art_card(site, a, "../") for a in arts)}</div></section>' if arts else ''}
{f'<section><div class="sh"><h2>Dans le même domaine</h2></div><div class="cards">{"".join(item_card(site, x, "../") for x in same)}</div></section>' if same else ''}
{bloc_abonnement(site, '../')}"""
        write(p, page(site, p, titre_court(f"{it['nom']} — {tl} {it.get('tache') or ''} : fiche, licence, score", f"{it['nom']} — {tl} : fiche, licence, score",
                                              f"{it['nom']} : fiche, licence, score", f"{it['nom']} : fiche", it["nom"]), desc, body, md_path=p.replace(".html", ".md"),
                      crumbs=[("Accueil", "index.html"), ("Modèles", "modeles.html"), (it["nom"], None)], jsonld=[ld_item(site, it)], nav_key="modeles.html"),
              it.get("derniereVue"))
        md = (f"# {it['nom']}\n\n> {it.get('resume')}\n\n- Identifiant Hugging Face : `{it.get('hfId')}` — {site.hf_url(it)}\n- Type : {tl}\n" + kv_md +
              f"- Score Radar : {it.get('score')}/100 · pertinent IA pratique : {'oui' if it.get('pertinent') else 'non'}\n- Domaines : {', '.join(site.dom_name(d) for d in it.get('domaines') or [])}\n"
              + (f"- Faits vérifiés sur l'API Hugging Face le {d_short(site.v(it)['verifieLe'])}\n" if site.v(it).get("verifieLe") else "")
              + f"\n**Pourquoi ça compte.** {it.get('pourquoi')}\n")
        write_md(p.replace(".html", ".md"), it["nom"], md)

    # --- Domaines
    r = '<h1>Domaines</h1><div class="cards" style="margin-top:16px">'
    for dk, dv in site.domaines.items():
        n = len(site.items_in(dk)); na = len([a for a in site.art_sorted if a.get("domaine") == dk])
        r += f'<div class="card"><h3><a href="{site.dom_page(dk)}">{esc(dv.get("nom"))}</a></h3><p>{esc(dv.get("description"))}</p><div class="meta"><span>{n} éléments</span><span>{na} articles</span></div></div>'
        its = site.items_in(dk); arts = [a for a in site.art_sorted if a.get("domaine") == dk]
        p = site.dom_page(dk)
        mois = d_long(site.today).split(" ", 1)[-1]  # « octobre 2026 » : vise les requêtes « meilleur modèle … »
        (out / "feeds").mkdir(parents=True, exist_ok=True)
        (out / "feeds" / f"{dk}.xml").write_text(rss_domaine(site, dk), encoding="utf-8")
        body = f"""<div class="eb">Mis à jour le {d_long(site.today)}</div><h1 style="margin-top:6px">Meilleurs modèles open source : {esc(dv.get('nom'))}</h1><p class="mut" style="max-width:70ch">{esc(dv.get('description'))} Sélection {esc(mois)} classée par Score Radar.</p>
<p class="sm mono"><a href="../feeds/{dk}.xml">Flux RSS de ce domaine</a> · <a href="https://feedly.com/i/subscription/feed/{quote(site.abs(f'feeds/{dk}.xml'), safe='')}" rel="noopener">Suivre sur Feedly</a></p>
{f'<section><div class="sh"><h2>Articles</h2></div><div class="cards">{"".join(art_card(site, a, "../") for a in arts)}</div></section>' if arts else ''}
<section><div class="sh"><h2>Meilleurs scores du domaine</h2></div>{f'<div class="cards">{"".join(item_card(site, it, "../", i+1) for i, it in enumerate(its[:12]))}</div>' if its else '<p class="mut">Aucun élément pour le moment.</p>'}</section>"""
        write(p, page(site, p, f"Meilleurs modèles {dv.get('nom')} open source ({mois})", f"Les meilleurs modèles IA open source pour {dv.get('nom')} en {mois} : {dv.get('description')} Classement par Score Radar et analyses en français.",
                      body, crumbs=[("Accueil", "index.html"), ("Domaines", "domaines.html"), (dv.get("nom"), None)], nav_key="domaines.html",
                      feed=(f"feeds/{dk}.xml", f"{SITE_NAME} — {dv.get('nom')} (RSS)"),
                      jsonld=[ld_itemlist(site, dv.get("nom"), its[:20], p)] if its else None))
    write("domaines.html", page(site, "domaines.html", "Domaines de l'IA open source suivis", "LLM en local, documents et OCR, agents, audio, code, multilingue, image et vidéo, données : les rubriques de Radar IA.",
                                r + "</div>", crumbs=[("Accueil", "index.html"), ("Domaines", None)]))

    # --- Guides (faits vérifiés sur Hugging Face)
    guides = build_guides(site, write, write_md)

    # --- Éditions
    r = '<h1>Éditions</h1><ul class="ess">' + "".join(f'<li><a href="{site.ed_page(e)}"><strong>{d_long(e["date"])}</strong></a> — {esc(e.get("titre"))}</li>' for e in site.ed_sorted) + "</ul>"
    write("editions.html", page(site, "editions.html", "Archives des éditions quotidiennes", "Toutes les éditions quotidiennes de Radar IA : l'essentiel, la tendance de fond et le top des modèles.",
                                r, crumbs=[("Accueil", "index.html"), ("Éditions", None)]))
    for e in site.ed_sorted:
        p = site.ed_page(e)
        top = [site.items[i] for i in e.get("topIds") or [] if i in site.items]
        nouv = [site.items[i] for i in e.get("nouveauxIds") or [] if i in site.items]
        body = f"""<div class="eb">Édition du {d_long(e['date'])}</div><h1 style="margin-top:6px">{esc(e.get('titre'))}</h1><ol class="ess">{''.join(f"<li>{esc(x.get('texte'))}</li>" for x in e.get('essentiel') or [])}</ol>
<div class="box" style="margin-top:16px"><strong>Tendance de fond.</strong> {esc(e.get('tendance'))}</div>
{f'<section><div class="sh"><h2>Top du jour</h2></div><div class="cards">{"".join(item_card(site, it, "../", i+1) for i, it in enumerate(top))}</div></section>' if top else ''}
{f'<section><div class="sh"><h2>Nouveautés 48 h</h2></div><div class="cards">{"".join(item_card(site, it, "../") for it in nouv)}</div></section>' if nouv else ''}
{bloc_sponsor(site, '../')}{bloc_abonnement(site, '../')}"""
        write(p, page(site, p, f"Édition du {d_short(e['date'])} : {e.get('titre')}", " ".join(x.get("texte", "") for x in e.get("essentiel") or []),
                      body, og_type="article", crumbs=[("Accueil", "index.html"), ("Éditions", "editions.html"), (d_short(e["date"]), None)], nav_key="editions.html",
                      jsonld=[{"@context": "https://schema.org", "@type": "NewsArticle", "headline": clip(e.get("titre", ""), 110), "datePublished": iso_dt(e.get("creeLe") or e["date"]),
                               "inLanguage": "fr-FR", "publisher": {"@id": site.abs("#org")}, "author": {"@type": "Organization", "name": SITE_NAME}, "mainEntityOfPage": site.abs(p)}],
                      published=e.get("creeLe") or e["date"]), e["date"])

    # --- FAQ générée depuis les données (format réponse directe)
    def top_names(lst, n=5):
        return ", ".join(f'<a href="{site.item_page(i)}">{esc(i["nom"])}</a> ({i.get("score")})' for i in lst[:n])
    r7 = ranking_items(site, "7j") or all_items
    qas = [
        ("Quels sont les modèles IA open source les plus populaires cette semaine ?",
         f"D'après le Score Radar du {d_short(site.today)}, les éléments créés depuis 7 jours les mieux classés sont : {top_names(r7)}."),
        ("Quels modèles IA peut-on faire tourner en local sur un PC ?",
         f"Parmi les éléments suivis, les meilleurs scores du domaine « LLM en local » sont : {top_names([i for i in site.items_in('local') if i.get('pertinent')])}. Les versions GGUF se lancent avec llama.cpp, Ollama ou LM Studio."),
        ("Quel modèle utiliser pour l'OCR et le traitement de documents ?",
         f"Pour les documents (OCR, classification, extraction) : {top_names(site.items_in('documents'))}."),
        ("Quels modèles pour bâtir des agents IA avec appel d'outils ?",
         f"Domaine agents et décision : {top_names(site.items_in('agents'))}."),
        ("Quel modèle de transcription audio fonctionne en français ?",
         f"Domaine voix et audio : {top_names(site.items_in('audio'))}. Vérifier le taux d'erreur en français sur chaque fiche."),
        ("Qu'est-ce que le Score Radar ?",
         "Une note de 0 à 100 : 40 % popularité (likes, échelle log), 30 % diffusion (téléchargements, échelle log), 20 % fraîcheur (date de création), 10 % pertinence pour l'IA pratique. Détail sur la page Méthode."),
        ("D'où viennent les données de Radar IA ?",
         "Des pages publiques de huggingface.co (tendances, likes sur 30 jours, fiches des modèles), relevées chaque matin par des agents IA. Licences, dates, langues, paramètres et formats sont ensuite revérifiés sur l'API Hugging Face à chaque publication. Chaque article cite ses sources."),
        *([("Quels modèles IA open source gèrent le français ?",
            f"Parmi les éléments suivis, ceux dont les auteurs déclarent le français sur Hugging Face sont : {top_names(fr_items)}. Liste complète : "
            f'<a href="guides/francais.html">modèles qui gèrent le français</a>.')] if (fr_items := [i for i in all_items if "fr" in (site.v(i).get("langues") or [])]) else []),
        *([("Quels modèles GGUF lancer avec Ollama ou LM Studio ?",
            f"Dépôts GGUF suivis les mieux classés : {top_names(gg_items)}. Voir le <a href=\"guides/gguf.html\">guide GGUF</a> (paramètres, contexte, licence).")]
          if (gg_items := [i for i in all_items if "GGUF" in (site.v(i).get("formats") or [])]) else []),
        *([("Quels modèles IA open source sont sous licence Apache 2.0 ou MIT ?",
            f"Les mieux classés sous licence Apache 2.0 ou MIT d'après Hugging Face : {top_names(perm)}. Détail par licence : "
            f'<a href="guides/licences.html">licences des modèles suivis</a>.')]
          if (perm := [i for i in all_items if (site.lic(i) or "").lower() in ("apache-2.0", "mit")]) else []),
        ("Comment un agent IA peut-il réutiliser ces données ?",
         'Via l\'API JSON statique (<a href="api/v1/index.json">api/v1/index.json</a>, décrite par <a href="openapi.json">openapi.json</a>), le fichier <a href="llms.txt">llms.txt</a> ou le flux <a href="feed.xml">RSS</a>. Licence CC BY 4.0.'),
    ]
    body = '<h1>Questions fréquentes</h1><p class="mut">Réponses régénérées chaque matin à partir des données du jour.</p><dl class="faq">' + "".join(f"<dt>{esc(q)}</dt><dd>{a}</dd>" for q, a in qas) + "</dl>"
    write("faq.html", page(site, "faq.html", "FAQ : quels modèles IA open source utiliser ?", "Réponses directes mises à jour chaque jour : modèles IA les plus populaires, IA en local, OCR, agents, transcription en français.",
                           body, md_path="faq.md", crumbs=[("Accueil", "index.html"), ("FAQ", None)], jsonld=[ld_faq(qas)]))
    write_md("faq.md", "FAQ", "# FAQ Radar IA\n\n" + "\n\n".join(f"## {q}\n\n{html_to_md(a)}" for q, a in qas))

    # --- Méthode
    meth_q = [("Comment est calculé le Score Radar ?", "score = 40·popularité + 30·diffusion + 20·fraîcheur + 10·pertinence, arrondi à l'entier."),
              ("Qui écrit les articles ?", "Une chaîne de quatre agents IA (veille, classements, rédaction, rédaction en chef) relancée chaque matin ; la rédaction en chef vérifie liens et chiffres avant publication.")]
    body = f"""<h1>Méthode</h1><article class="a body"><p>Chaque matin, une chaîne d'agents IA relève les pages publiques de Hugging Face, lit les fiches des éléments marquants, calcule les scores, rédige un article par domaine actif puis vérifie liens et chiffres avant publication. Le site est ensuite régénéré en pages statiques.</p>
<h2>Score Radar (0 à 100)</h2><pre class="code">score = 40 × popularité + 30 × diffusion + 20 × fraîcheur + 10 × pertinence
popularité = min(1, log10(1 + likes) / log10(20 001))
diffusion  = min(1, log10(1 + téléchargements) / log10(10 000 001))
fraîcheur  = 1 si créé ≤ 7 j · 0,7 ≤ 30 j · 0,4 ≤ 90 j · 0,15 au-delà · 0,4 si inconnu
pertinence = 1 si utile à l'IA pratique (local, documents, agents, audio, code, français)</pre>
<h2>Vérification des faits</h2><p>À chaque publication, la licence, les dates de création et de mise à jour, les langues déclarées, le nombre de paramètres, les formats (GGUF, safetensors…), le modèle de base, les likes et les téléchargements sur 30 jours de chaque élément sont relus sur l'API publique de Hugging Face. Ces valeurs remplacent celles saisies par les agents sur les fiches et dans les <a href="guides.html">guides</a>, avec la date de vérification. Les guides (français, licences, GGUF, familles de modèles) sont produits uniquement à partir de ces faits.</p>
<h2>Limites</h2><p>Les chiffres des classements proviennent des pages de liste de Hugging Face au moment du relevé et sont arrondis ; les faits vérifiés sont ceux que déclarent les auteurs des modèles. Les benchmarks cités sont ceux des fiches, souvent auto-déclarés : les articles le signalent.</p>
<h2>Licence</h2><p>Textes et données sous <a href="{LICENSE_URL}">CC BY 4.0</a> : réutilisation libre avec mention « Radar IA » et lien.</p></article>"""
    write("methode.html", page(site, "methode.html", "Méthode et Score Radar", "Comment Radar IA relève Hugging Face, calcule le Score Radar et vérifie ses articles.",
                               body, crumbs=[("Accueil", "index.html"), ("Méthode", None)], jsonld=[ld_faq(meth_q)]))

    # --- S'abonner
    feed = site.abs("feed.xml")
    res = "".join(f'<li><a href="{esc(r["url"])}" rel="me noopener">{esc(r.get("nom") or r["url"])}</a></li>' for r in site.cfg.get("reseaux") or [] if has_url(r.get("url")))
    body = f"""<h1>Suivre Radar IA</h1><p class="mut" style="max-width:70ch">Une édition chaque matin vers 9 h : les modèles IA ouverts qui comptent, ceux à tester en local, les scores et les analyses. Gratuit.</p>
{bloc_abonnement(site, '')}
<section><div class="sh"><h2>Lecteurs de flux</h2></div><ul class="ess"><li><a href="feed.xml">Flux RSS 2.0</a> (contenu complet des articles)</li><li><a href="feed.json">JSON Feed 1.1</a></li>
<li><a href="https://feedly.com/i/subscription/feed/{quote(feed, safe='')}" rel="noopener">Ajouter à Feedly</a></li>{"".join(f'<li><a href="feeds/{dk}.xml">Flux « {esc(dv.get("nom"))} »</a></li>' for dk, dv in site.domaines.items())}<li><a href="https://www.inoreader.com/?add_feed={quote(feed, safe='')}" rel="noopener">Ajouter à Inoreader</a></li></ul></section>
{f'<section><div class="sh"><h2>Réseaux</h2></div><ul class="ess">{res}</ul></section>' if res else ''}
<section><div class="sh"><h2>Pour les agents IA</h2></div><p class="sm"><a href="llms.txt">llms.txt</a>, <a href="api/v1/index.json">API JSON</a> et <a href="openapi.json">OpenAPI</a> : voir <a href="pour-les-ia.html">API &amp; IA</a>.</p></section>"""
    write("abonnement.html", page(site, "abonnement.html", "S'abonner à Radar IA : newsletter, RSS, réseaux", "Recevez chaque matin l'essentiel des modèles IA open source en français : newsletter gratuite, flux RSS, JSON Feed, réseaux.",
                                  body, crumbs=[("Accueil", "index.html"), ("S'abonner", None)]))

    # --- Soutenir et devenir partenaire
    dons = "".join(f'<a class="btn" href="{esc(s["url"])}" rel="noopener">{esc(s.get("nom") or "Soutenir")}</a>' for s in site.cfg.get("soutien") or [] if has_url(s.get("url")))
    offres = "".join(f'<div class="card"><h3>{esc(o.get("nom"))}</h3><p>{esc(o.get("detail"))}</p><div class="meta"><strong class="prix">{esc(o.get("prix") or "sur devis")}</strong></div></div>'
                     for o in site.cfg.get("offres") or [] if o.get("nom") and o.get("actif", True))
    cu = contact_url(site)
    body = f"""<h1>Soutenir Radar IA</h1><p class="mut" style="max-width:70ch">Radar IA est gratuit, sans traceur publicitaire, et ses données sont ouvertes (CC BY 4.0). Trois façons de l'aider à durer.</p>
<section id="soutien"><div class="sh"><h2>1. Partager et s'abonner</h2></div><p class="sm">Le soutien le plus utile : <a href="abonnement.html">s'abonner</a> et transmettre une édition à un collègue qui travaille avec l'IA.</p>{bloc_partage(site, site.abs(''), SITE_NAME + ' — ' + SITE_TAGLINE)}</section>
{f'<section><div class="sh"><h2>2. Faire un don</h2></div><p class="sm">Un café par mois finance l’hébergement, le nom de domaine et le temps de relecture.</p><div class="btns">{dons}</div></section>' if dons else ''}
<section id="annoncer"><div class="sh"><h2>{'3' if dons else '2'}. Devenir partenaire</h2></div>
<p style="max-width:70ch">Radar IA est lu par des développeurs, data scientists, DSI et chefs de projet francophones qui choisissent et déploient des modèles IA ouverts : en local, sur des documents, pour des agents. Un public rare, et difficile à toucher en français.</p>
{f'<div class="offres">{offres}</div>' if offres else ''}
<h3 style="margin-top:20px">Règles</h3><ul class="sm"><li>Les partenaires sont toujours signalés (« Partenaire », « contenu sponsorisé ») et leurs liens portent <code>rel="sponsored"</code>.</li>
<li>Le Score Radar et les classements sont calculés automatiquement à partir des données Hugging Face : aucun partenaire ne peut les modifier.</li><li>Pas de partenaire dont le produit contredit nos analyses publiées.</li></ul>
{f'<p class="btns"><a class="btn" href="{esc(cu)}" rel="noopener">Proposer un partenariat</a></p>' if cu else ''}</section>"""
    write("soutenir.html", page(site, "soutenir.html", "Soutenir Radar IA et devenir partenaire", "Soutenez Radar IA, la veille francophone des modèles IA open source : partage, don, partenariat signalé auprès d'un public technique francophone.",
                                body, crumbs=[("Accueil", "index.html"), ("Soutenir", None)]))

    # --- Pour les IA
    base = site.abs("")
    body = f"""<h1>Pour les assistants et agents IA</h1><p class="mut" style="max-width:70ch">Tout le contenu de Radar IA est lisible par les machines, sans JavaScript ni authentification, sous licence CC BY 4.0.</p>
<div class="tw"><table><thead><tr><th>Ressource</th><th>Usage</th></tr></thead><tbody>
<tr><td><a href="llms.txt"><code>/llms.txt</code></a></td><td>Index pour LLM (format llmstxt.org)</td></tr>
<tr><td><a href="llms-full.txt"><code>/llms-full.txt</code></a></td><td>Tout le contenu en Markdown, un seul fichier</td></tr>
<tr><td><code>/…/page.md</code></td><td>Version Markdown de chaque page (balise <code>rel="alternate" type="text/markdown"</code>)</td></tr>
<tr><td><a href="api/v1/index.json"><code>/api/v1/index.json</code></a></td><td>Catalogue de l'API JSON statique</td></tr>
<tr><td><a href="openapi.json"><code>/openapi.json</code></a></td><td>Description OpenAPI 3.1 (outil importable par un agent)</td></tr>
<tr><td><a href="feed.xml"><code>/feed.xml</code></a> · <a href="feed.json"><code>/feed.json</code></a></td><td>Flux RSS 2.0 et JSON Feed 1.1, contenu complet</td></tr>
<tr><td><a href="sitemap.xml"><code>/sitemap.xml</code></a></td><td>Toutes les URL avec date de mise à jour</td></tr></tbody></table></div>
<h2 style="margin-top:24px">Exemple</h2><pre class="code">curl {esc(base)}api/v1/classements.json | jq '.classements["7j"].entrees[:5]'</pre>
<p class="sm mut">Citation recommandée : « Radar IA, {d_short(site.today)} » avec lien vers la page source.</p>"""
    write("pour-les-ia.html", page(site, "pour-les-ia.html", "API ouverte, llms.txt et flux pour agents IA", "Données Radar IA pour les machines : llms.txt, Markdown, API JSON avec OpenAPI, RSS, JSON Feed, sitemap. Licence CC BY 4.0.",
                                   body, crumbs=[("Accueil", "index.html"), ("API & IA", None)], jsonld=[ld_dataset(site)]))

    # --- API JSON
    def clean(d):
        return {k: v for k, v in d.items() if not k.startswith("_")}
    api_items = [dict(clean(it), id=it["_id"], page=site.abs(site.item_page(it)), **({"verifieHuggingFace": site.v(it)} if site.v(it) else {})) for it in all_items]
    api_arts = [dict(clean(a), id=a["_id"], page=site.abs(site.art_page(a)), markdown=site.abs(f"articles/{a['_slug']}.md")) for a in site.art_sorted]
    meta = {"source": SITE_NAME, "site": base, "licence": "CC-BY-4.0", "genereLe": site.built_at, "dateDonnees": site.today}
    api = {"items.json": {**meta, "items": api_items}, "articles.json": {**meta, "articles": api_arts},
           "editions.json": {**meta, "editions": site.ed_sorted}, "classements.json": {**meta, "classements": site.classements},
           "domaines.json": {**meta, "domaines": site.domaines}}
    for n, d in api.items():
        (out / "api/v1").mkdir(parents=True, exist_ok=True)
        (out / "api/v1" / n).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "api/v1/index.json").write_text(json.dumps({**meta, "description": SITE_DESC, "endpoints": {n[:-5]: site.abs("api/v1/" + n) for n in api},
                                                        "openapi": site.abs("openapi.json"), "llms": site.abs("llms.txt")}, ensure_ascii=False, indent=1), encoding="utf-8")
    paths = {}
    for n, key in [("items", "items"), ("articles", "articles"), ("editions", "editions"), ("classements", "classements"), ("domaines", "domaines")]:
        paths[f"/api/v1/{n}.json"] = {"get": {"operationId": f"get_{n}", "summary": {
            "items": "Tous les modèles, datasets et Spaces suivis, avec likes, téléchargements, domaines, licence, Score Radar et historique",
            "articles": "Articles publiés (titre, chapo, HTML, sources, éléments cités)",
            "editions": "Éditions quotidiennes (essentiel, tendance de fond, top, nouveautés)",
            "classements": "Classements par période : jour, 7j, 30j, 90j (rang, score, delta)",
            "domaines": "Rubriques thématiques"}[n], "responses": {"200": {"description": "OK", "content": {"application/json": {"schema": {"type": "object", "properties": {key: {}}}}}}}}}
    openapi = {"openapi": "3.1.0", "info": {"title": f"{SITE_NAME} — API ouverte", "version": "1.0", "description": SITE_DESC, "license": {"name": "CC BY 4.0", "url": LICENSE_URL}},
               "servers": [{"url": base.rstrip("/") or "."}], "paths": paths}
    (out / "openapi.json").write_text(json.dumps(openapi, ensure_ascii=False, indent=1), encoding="utf-8")

    # --- llms.txt / llms-full.txt
    llms = [f"# {SITE_NAME}", "", f"> {SITE_DESC} Site en français, mis à jour chaque matin, données sous licence CC BY 4.0.", "",
            f"Dernière édition : {d_long(site.today)}. Le Score Radar (0-100) combine popularité, téléchargements, fraîcheur et pertinence pour l'IA pratique.", "",
            "## Pages principales", "",
            f"- [Accueil, édition du jour]({site.abs('index.md')}): l'essentiel, la tendance de fond, les derniers articles",
            f"- [Classements]({site.abs('classements.md')}): top jour, 7 jours, 30 jours, 3 mois avec scores",
            f"- [FAQ]({site.abs('faq.md')}): réponses directes (modèles populaires, IA locale, OCR, agents, transcription)", "",
            "## Guides (faits vérifiés sur Hugging Face)", ""] + [f"- [{gt}]({site.abs(gp.replace('.html', '.md') if gp.startswith('guides/') else gp)}): {gr}" for gt, gp, gr in guides] + [
            "", "## Articles", ""] + [f"- [{a['titre']}]({site.abs('articles/' + a['_slug'] + '.md')}): {clip(a.get('chapo', ''), 160)}" for a in site.art_sorted] + [
            "", "## Fiches modèles", ""] + [f"- [{it['nom']}]({site.abs(site.item_page(it).replace('.html', '.md'))}): {site.org(it)}, {it.get('tache')}, score {it.get('score')}" for it in all_items[:60]] + [
            "", "## Données", "", f"- [API JSON]({site.abs('api/v1/index.json')}): items, articles, éditions, classements, domaines",
            f"- [OpenAPI]({site.abs('openapi.json')}): description des points d'accès", "", "## Optional", "",
            f"- [Tout le contenu]({site.abs('llms-full.txt')}): toutes les pages en Markdown", f"- [Méthode]({site.abs('methode.html')}): calcul du score et limites"]
    (out / "llms.txt").write_text("\n".join(llms) + "\n", encoding="utf-8")
    (out / "llms-full.txt").write_text(f"# {SITE_NAME} — contenu complet ({d_long(site.today)})\n\n> {SITE_DESC}\n\n" +
                                       "\n\n---\n\n".join(md for _, _, md in md_docs), encoding="utf-8")

    # --- flux
    rss_items = "".join(f"""<item><title>{esc(a['titre'])}</title><link>{esc(site.abs(site.art_page(a)))}</link><guid isPermaLink="true">{esc(site.abs(site.art_page(a)))}</guid>
<pubDate>{rfc822(a.get('publieLe') or a.get('date'))}</pubDate><category>{esc(site.dom_name(a.get('domaine')))}</category><description>{esc(a.get('chapo'))}</description>
<content:encoded><![CDATA[{sanitize(a.get('corpsHtml')).replace(']]>', ']]&gt;')}]]></content:encoded></item>""" for a in site.art_sorted[:50])
    (out / "feed.xml").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:atom="http://www.w3.org/2005/Atom"><channel>
<title>{SITE_NAME}</title><link>{esc(base)}</link><description>{esc(SITE_DESC)}</description><language>fr-fr</language>
<lastBuildDate>{rfc822(site.built_at)}</lastBuildDate><atom:link href="{esc(site.abs('feed.xml'))}" rel="self" type="application/rss+xml"/>{rss_items}</channel></rss>""", encoding="utf-8")
    (out / "feed.json").write_text(json.dumps({"version": "https://jsonfeed.org/version/1.1", "title": SITE_NAME, "home_page_url": base, "feed_url": site.abs("feed.json"),
        "description": SITE_DESC, "language": "fr", "items": [{"id": site.abs(site.art_page(a)), "url": site.abs(site.art_page(a)), "title": a["titre"], "summary": a.get("chapo"),
        "content_html": sanitize(a.get("corpsHtml")), "date_published": iso_dt(a.get("publieLe") or a.get("date")), "tags": a.get("motsCles") or []} for a in site.art_sorted[:50]]},
        ensure_ascii=False, indent=1), encoding="utf-8")

    # --- sitemap + robots
    sm = "".join(f"<url><loc>{esc(site.abs(p if p != 'index.html' else ''))}</loc><lastmod>{lm}</lastmod></url>" for p, lm in urls)
    (out / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>\n', encoding="utf-8")
    bots = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-User", "Claude-SearchBot", "anthropic-ai", "PerplexityBot", "Perplexity-User",
            "Google-Extended", "Googlebot", "Bingbot", "Applebot", "Applebot-Extended", "meta-externalagent", "Amazonbot", "DuckAssistBot", "MistralAI-User", "CCBot", "cohere-ai"]
    (out / "robots.txt").write_text("# Radar IA : contenu ouvert (CC BY 4.0), robots de recherche et d'IA bienvenus.\n" +
        "".join(f"User-agent: {b}\nAllow: /\n\n" for b in bots) + "User-agent: *\nAllow: /\n\n" + (f"Sitemap: {site.abs('sitemap.xml')}\n" if site.url else ""), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    if site.static:  # fichiers fixes (image de partage…) copiés tels quels
        for f in site.static.iterdir():
            if f.is_file(): shutil.copy2(f, out / "assets" / f.name)
    cle = str((site.cfg.get("indexnow") or {}).get("cle") or "")
    if re.fullmatch(r"[a-zA-Z0-9-]{8,128}", cle):  # fichier de clé IndexNow (Bing, Yandex, Seznam, Naver)
        (out / f"{cle}.txt").write_text(cle, encoding="utf-8")
    # 404 : servie à n'importe quelle profondeur, donc liens absolus (ou relatifs à la racine sans URL de site)
    b4 = site.url
    doms = "".join(f'<li><a href="{b4}{site.dom_page(dk)}">{esc(dv.get("nom"))}</a></li>' for dk, dv in site.domaines.items())
    top = "".join(f'<li><a href="{b4}{site.item_page(it)}">{esc(it["nom"])}</a> {score_badge(it.get("score"))}</li>' for it in all_items[:5])
    body404 = (f'<div class="lead"><div><div class="eb">Erreur 404</div><h1 style="margin-top:6px">Hors du radar</h1>'
               f'<p class="mut" style="max-width:60ch">Cette page n’existe pas ou plus : un modèle peut avoir quitté le suivi, ou l’adresse a changé. Voici où reprendre.</p>'
               f'<p class="btns"><a class="btn" href="{b4}index.html">Édition du jour</a><a class="btn" href="{b4}modeles.html" style="background:var(--fg2)">Annuaire des modèles</a></p>'
               f'<section><div class="sh"><h2>Domaines</h2></div><ul class="ess">{doms}</ul></section></div>'
               f'<aside><div class="radar"><h2>Les mieux classés</h2><ul class="ess" style="margin-top:6px">{top}</ul></div>'
               f'<div class="box" style="margin-top:16px"><h2 style="font-size:1rem">Guides</h2><ul class="sm" style="padding-left:18px;margin:8px 0 0">'
               f'<li><a href="{b4}nouveautes.html">Nouveautés</a></li><li><a href="{b4}guides/francais.html">Modèles en français</a></li>'
               f'<li><a href="{b4}guides/gguf.html">Modèles GGUF</a></li><li><a href="{b4}comparer.html">Comparatifs</a></li><li><a href="{b4}glossaire.html">Glossaire</a></li></ul></div></aside></div>')
    (out / "404.html").write_text(page(site, "404.html", "Page introuvable", "Cette page n'existe pas ou plus sur Radar IA.", body404), encoding="utf-8")
    return urls

def main():
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(errors="replace")  # consoles Windows (cp1252)
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--site-url", default=os.environ.get("SITE_URL", ""))
    ap.add_argument("--artifact", action="store_true", help="page racine sans doctype (publication en artefact Claude)")
    ap.add_argument("--config", default=str(RACINE_DEPOT / "config" / "site.json"), help="leviers d'audience et de revenus (facultatif)")
    ap.add_argument("--static", default=str(RACINE_DEPOT / "static"), help="fichiers fixes copiés dans assets/ (facultatif)")
    a = ap.parse_args()
    site = Site(Path(a.data), a.site_url, load_config(Path(a.config)), Path(a.static))
    urls = build(site, Path(a.out), artifact=a.artifact)
    print(f"{len(urls)} pages HTML, {len(site.items)} items, {len(site.articles)} articles, {len(site.editions)} éditions → {a.out}")

if __name__ == "__main__":
    main()
