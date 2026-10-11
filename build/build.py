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
import argparse, html, json, math, os, re, shutil, sys
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

# ------------------------------------------------------------------ gabarit

CSS = r"""
:root{--bg:#f7f7f5;--bg2:#fff;--bg3:#ecece6;--fg:#16181d;--fg2:#4a505b;--fg3:#7a808a;--line:#dcdcd4;--acc:#5b3fd9;--acc2:#c2410c;--soft:#ebe6ff;--star:#a16207;
--mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;--sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;--r:6px;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#101116;--bg2:#171922;--bg3:#20232e;--fg:#e9e9ef;--fg2:#a9adbb;--fg3:#7c8191;--line:#2a2e3b;--acc:#a593ff;--acc2:#fb923c;--soft:#25204a;--star:#eab308;color-scheme:dark}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 var(--sans)}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}:focus-visible{outline:2px solid var(--acc2);outline-offset:2px}
.w{max-width:1120px;margin:0 auto;padding-inline:16px}
h1,h2,h3{line-height:1.2;text-wrap:balance;margin:0}h1{font-size:clamp(1.6rem,3.6vw,2.4rem);letter-spacing:-.02em}h2{font-size:1.3rem}h3{font-size:1.05rem}
.mono,.num{font-family:var(--mono);font-variant-numeric:tabular-nums}
.eb{font-family:var(--mono);font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:var(--fg3)}
.mut{color:var(--fg2)}.sm{font-size:.88rem}
header.top{border-bottom:1px solid var(--line);background:var(--bg)}
.bar{display:flex;align-items:center;justify-content:space-between;gap:12px;padding-block:14px;flex-wrap:wrap}
.logo{font-family:var(--mono);font-weight:700;font-size:1.15rem;color:var(--fg)}.logo b{color:var(--acc)}
nav.m{display:flex;gap:2px;flex-wrap:wrap}nav.m a{font-family:var(--mono);font-size:.84rem;padding:6px 10px;border-radius:var(--r);color:var(--fg2)}
nav.m a[aria-current=page]{background:var(--fg);color:var(--bg)}
main{padding-block:28px 56px}section{margin-top:36px}section:first-child{margin-top:0}
.sh{display:flex;align-items:baseline;justify-content:space-between;gap:12px;border-bottom:1px solid var(--line);padding-bottom:8px;margin-bottom:14px}
.crumb{font-family:var(--mono);font-size:.78rem;color:var(--fg3);margin-bottom:12px}.crumb a{color:var(--fg3)}
.lead{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);gap:28px}@media(max-width:820px){.lead{grid-template-columns:1fr}}
.ess{list-style:none;margin:16px 0 0;padding:0}.ess li{padding:10px 0;border-top:1px solid var(--line)}.ess li:first-child{border-top:0}
.ess li::before{content:"> ";font-family:var(--mono);color:var(--acc2);font-weight:700}
.box{background:var(--bg3);border-radius:var(--r);padding:14px 16px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}
.card{background:var(--bg2);border:1px solid var(--line);border-radius:var(--r);padding:14px;display:flex;flex-direction:column;gap:6px;min-width:0}
.card h3{overflow-wrap:anywhere}.card p{margin:0;font-size:.92rem;color:var(--fg2)}
.meta{display:flex;gap:12px;flex-wrap:wrap;font-family:var(--mono);font-size:.76rem;color:var(--fg2);margin-top:auto}
.sc{display:inline-block;min-width:38px;text-align:center;padding:2px 8px;border-radius:12px;font-family:var(--mono);font-size:.82rem;background:var(--soft);color:var(--acc)}
.sc.hot{background:var(--acc);color:var(--bg)}
.chip{display:inline-block;font-family:var(--mono);font-size:.7rem;padding:1px 7px;border-radius:3px;background:var(--bg3);color:var(--fg2);margin:0 4px 4px 0}
.star{color:var(--star)}
.tw{overflow-x:auto;border:1px solid var(--line);border-radius:var(--r);background:var(--bg2)}
table{border-collapse:collapse;width:100%;font-size:.9rem}th{font-family:var(--mono);font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;color:var(--fg3);text-align:left;padding:9px 10px;border-bottom:2px solid var(--line);white-space:nowrap}
td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}tr:last-child td{border-bottom:0}.r{text-align:right}
.tw table{min-width:680px}
.up{color:#15803d}.dn{color:var(--acc2)}
article.a{max-width:70ch}article.a .chapo{font-size:1.12rem;color:var(--fg2)}
.by{font-family:var(--mono);font-size:.78rem;color:var(--fg3);border-block:1px solid var(--line);padding-block:8px;margin:14px 0 20px;display:flex;gap:14px;flex-wrap:wrap}
.body h2{margin:26px 0 8px}.body h3{margin:18px 0 6px}.body p{margin:0 0 14px}.body ul,.body ol{padding-left:22px;margin:0 0 14px}
.body table{margin-bottom:14px;display:block;overflow-x:auto;max-width:100%}main{overflow-wrap:anywhere}.body blockquote{margin:0 0 14px;padding-left:14px;border-left:3px solid var(--acc);color:var(--fg2)}
.body code,code{font-family:var(--mono);font-size:.86em;background:var(--bg3);padding:1px 5px;border-radius:3px}
dl.kv{display:grid;grid-template-columns:max-content 1fr;gap:6px 16px;margin:0}dl.kv dt{font-family:var(--mono);font-size:.8rem;color:var(--fg3)}dl.kv dd{margin:0}
.faq dt{font-weight:600;margin-top:16px}.faq dd{margin:4px 0 0}
pre.code{font-family:var(--mono);font-size:.82rem;background:var(--bg3);padding:12px 14px;border-radius:var(--r);overflow-x:auto}
footer{border-top:1px solid var(--line);padding-block:20px 32px;font-size:.85rem;color:var(--fg2)}
footer .w{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}footer nav{display:flex;gap:12px;flex-wrap:wrap;font-family:var(--mono);font-size:.8rem}
nav.m a.sub{color:var(--acc);font-weight:600}
.spon{margin-top:28px;padding:10px 14px;border:1px dashed var(--line);border-radius:var(--r);font-size:.88rem;color:var(--fg2)}.spon .eb{margin-right:6px}
.cta{margin-top:36px;border-left:3px solid var(--acc)}.cta h2{font-size:1.1rem}.cta p{margin:6px 0}
form.nl{margin:10px 0 4px}form.nl div{display:flex;gap:8px;flex-wrap:wrap}form.nl label{display:block;margin-bottom:4px}
form.nl input[type=email]{flex:1 1 220px;min-width:0;font:inherit;padding:8px 10px;border:1px solid var(--line);border-radius:var(--r);background:var(--bg2);color:var(--fg)}
form.nl button,a.btn{font:600 .9rem var(--sans);padding:8px 14px;border:0;border-radius:var(--r);background:var(--acc);color:var(--bg);cursor:pointer;display:inline-block}
a.btn:hover{text-decoration:none;opacity:.9}.btns{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}
.offres{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px;margin-top:12px}.offres .card strong.prix{font-family:var(--mono);color:var(--acc)}
"""

NAV = [("index.html", "Une"), ("classements.html", "Classements"), ("articles.html", "Articles"), ("modeles.html", "Modèles"),
       ("domaines.html", "Domaines"), ("editions.html", "Éditions"), ("faq.html", "FAQ"), ("pour-les-ia.html", "API & IA"),
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
         published: str | None = None, modified: str | None = None) -> str:
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
    full_title = title if title.endswith(SITE_NAME) else f"{title} · {SITE_NAME}"
    ld = [ld_website(site), ld_org(site)] + (jsonld or [])
    if crumbs:
        ld.append(ld_breadcrumb(site, crumbs))
    nav = "".join(f'<a href="{root}{h}"{" class=sub" if h == "abonnement.html" else ""}{" aria-current=page" if (nav_key or path)==h else ""}>{esc(l)}</a>' for h, l in NAV)
    crumb_html = ""
    if crumbs:
        parts = [f'<a href="{root}{h}">{esc(l)}</a>' if h else esc(l) for l, h in crumbs]
        crumb_html = f'<div class="crumb">{" / ".join(parts)}</div>'
    head = f"""<title>{esc(clip(full_title, 70))}</title>
<meta name="description" content="{esc(clip(desc, 158))}">
<meta name="robots" content="{'noindex' if path == '404.html' else 'index,follow,max-snippet:-1,max-image-preview:large'}">{verif_meta}
{f'<link rel="canonical" href="{esc(canonical)}">' if site.url and path != '404.html' else ''}
<link rel="stylesheet" href="{root}assets/style.css">
<link rel="alternate" type="application/rss+xml" title="{SITE_NAME} — RSS" href="{root}feed.xml">
<link rel="alternate" type="application/feed+json" title="{SITE_NAME} — JSON Feed" href="{root}feed.json">
<link rel="alternate" type="text/plain" title="llms.txt" href="{root}llms.txt">
{f'<link rel="alternate" type="text/markdown" href="{root}{md_path}">' if md_path else ''}
<link rel="sitemap" type="application/xml" href="{root}sitemap.xml">
<meta property="og:site_name" content="{SITE_NAME}"><meta property="og:locale" content="fr_FR">
<meta property="og:type" content="{og_type}"><meta property="og:title" content="{esc(clip(title, 90))}">
<meta property="og:description" content="{esc(clip(desc, 200))}">{f'<meta property="og:url" content="{esc(canonical)}">' if site.url else ''}
{f'<meta property="article:published_time" content="{esc(iso_dt(published))}">' if published else ''}{f'<meta property="article:modified_time" content="{esc(iso_dt(modified))}">' if modified else ''}
{og_img}<meta name="theme-color" content="#5b3fd9">
<script type="application/ld+json">{json.dumps(ld if len(ld) > 1 else ld[0], ensure_ascii=False).replace("</", "<\\/")}</script>"""
    shell_top = f"""<header class="top"><div class="w bar"><a class="logo" href="{root}index.html">radar<b>_ia</b></a><nav class="m" aria-label="Rubriques">{nav}</nav></div></header>
<main class="w">{crumb_html}{body}</main>
<footer><div class="w"><div>{SITE_NAME} — {esc(SITE_TAGLINE)}.<br>Données sous licence <a href="{LICENSE_URL}" rel="license">CC BY 4.0</a> · mise à jour {d_short(site.today)} · rédigé par des agents IA, sources liées sur chaque page.</div>
<nav><a href="{root}abonnement.html">S'abonner</a><a href="{root}soutenir.html">Soutenir</a><a href="{root}soutenir.html#annoncer">Devenir partenaire</a><a href="{root}feed.xml">RSS</a><a href="{root}llms.txt">llms.txt</a><a href="{root}api/v1/index.json">API</a><a href="{root}sitemap.xml">Sitemap</a><a href="{root}methode.html">Méthode</a></nav></div></footer>{pixel(site, path)}"""
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
    d = {"@context": "https://schema.org", "@type": typ, "name": it.get("nom"), "url": site.hf_url(it),
         "description": it.get("resume") or it.get("pourquoi"), "sameAs": site.hf_url(it),
         "creator": {"@type": "Organization", "name": it.get("org")}, "dateModified": it.get("majLe")}
    if it.get("creeLe"): d["datePublished"] = it["creeLe"]
    if it.get("licence"): d["license"] = it["licence"]
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
    s = round(float(s)); return f'<span class="sc{" hot" if s >= 70 else ""}" title="Score Radar /100">{s}</span>'

def item_card(site, it, root, rank=None):
    star = '<span class="star" title="Pertinent : local, documents, agents, audio, code, français">★</span> ' if it.get("pertinent") else ""
    doms = "".join(f'<span class="chip">{esc(site.dom_name(d))}</span>' for d in it.get("domaines") or [])
    return f"""<div class="card"><div style="display:flex;justify-content:space-between;gap:8px"><div class="eb">{f"#{rank} · " if rank else ""}{esc(it.get('org'))}</div>{score_badge(it.get('score'))}</div>
<h3>{star}<a href="{root}{site.item_page(it)}">{esc(it.get('nom'))}</a></h3><div>{doms}<span class="chip">{esc(TYPE_LABEL.get(it.get('type'), ''))}</span></div>
<p>{esc(it.get('pourquoi') or it.get('resume'))}</p><div class="meta"><span>♥ {fmt_n(it.get('likes'))}</span><span>↓ {fmt_n(it.get('downloads'))}</span>{f"<span>{esc(it['taille'])}</span>" if it.get('taille') else ''}</div></div>"""

def art_card(site, a, root):
    return f"""<div class="card"><div><span class="chip">{esc(site.dom_name(a.get('domaine')))}</span></div><h3><a href="{root}{site.art_page(a)}">{esc(a.get('titre'))}</a></h3>
<p>{esc(a.get('chapo'))}</p><div class="meta"><span>{d_short(a.get('date'))}</span><span>{esc(a.get('tempsLecture') or '')} min</span></div></div>"""

def ranking_table(site, entries, root, limit=None):
    rows = []
    for i, e in enumerate(entries[:limit] if limit else entries):
        it = site.items.get(e.get("itemId"))
        if not it: continue
        d = e.get("delta")
        dl = '<span class="star">nouveau</span>' if d is None else (f'<span class="up">▲ {d}</span>' if d > 0 else (f'<span class="dn">▼ {-d}</span>' if d < 0 else "="))
        rows.append(f"""<tr><td class="num">{e.get('rank') or e.get('rang') or i+1}</td><td><a href="{root}{site.item_page(it)}"><strong>{esc(it.get('nom'))}</strong></a>{' <span class="star">★</span>' if it.get('pertinent') else ''}<div class="sm mut mono">{esc(it.get('org'))} · {esc(TYPE_LABEL.get(it.get('type'), ''))}{(' · ' + esc(it['tache'])) if it.get('tache') else ''}</div></td>
<td>{''.join(f'<span class="chip">{esc(site.dom_name(x))}</span>' for x in it.get('domaines') or [])}</td><td class="r num">{fmt_n(e.get('likes', it.get('likes')))}</td><td class="r num">{fmt_n(e.get('downloads', it.get('downloads')))}</td><td class="r">{score_badge(e.get('score', it.get('score')))}</td><td class="mono sm">{dl}</td></tr>""")
    if not rows: return '<p class="mut">Classement en cours de calcul.</p>'
    return f'<div class="tw"><table><thead><tr><th>#</th><th>Élément</th><th>Domaines</th><th class="r">Likes</th><th class="r">Téléch.</th><th class="r">Score</th><th>Évol.</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'

def ranking_items(site, per):
    cl = site.classements.get(per) or {}
    return [site.items[e["itemId"]] for e in cl.get("entrees") or [] if e.get("itemId") in site.items]

# ------------------------------------------------------------------ pages

def build(site: Site, out: Path, artifact=False):
    if out.exists(): shutil.rmtree(out)
    (out / "assets").mkdir(parents=True)
    (out / "assets/style.css").write_text(CSS.strip(), encoding="utf-8")
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
<aside><div class="box"><h2 style="font-size:1rem">Tendance de fond</h2><p class="sm" style="margin:6px 0 0">{esc(ed.get('tendance'))}</p></div>
{f'<div style="margin-top:16px"><div class="eb">À tester</div><ul class="sm" style="padding-left:18px">{tester}</ul></div>' if tester else ''}</aside></section>
<section><div class="sh"><h2>Les modèles qui comptent aujourd'hui</h2><a class="mono sm" href="classements.html">classements →</a></div><div class="cards">{''.join(item_card(site, it, '', i+1) for i, it in enumerate(top))}</div></section>"""
    r += f"""<section><div class="sh"><h2>Derniers articles</h2><a class="mono sm" href="articles.html">tous →</a></div><div class="cards">{''.join(art_card(site, a, '') for a in site.art_sorted[:6]) or '<p class="mut">Premiers articles demain matin.</p>'}</div></section>
<section><div class="sh"><h2>Classement du jour — top 10</h2><span class="eb">Score Radar /100</span></div>{ranking_table(site, (site.classements.get('jour') or {}).get('entrees') or [], '', 10)}</section>
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
        r += f'<section id="{per}"><div class="sh"><h2>{esc(cl.get("titre") or lab)}</h2><span class="eb">{lab}</span></div>{ranking_table(site, cl.get("entrees") or [], "")}</section>'
        md += f"\n## {cl.get('titre') or lab}\n\n| # | Élément | Organisation | Score | Likes | Téléchargements |\n|---|---|---|---|---|---|\n"
        for e in cl.get("entrees") or []:
            it = site.items.get(e.get("itemId"))
            if it: md += f"| {e.get('rang')} | [{it['nom']}]({site.hf_url(it)}) | {it.get('org')} | {e.get('score')} | {it.get('likes')} | {it.get('downloads')} |\n"
    write("classements.html", page(site, "classements.html", "Classements des modèles IA open source (jour, 7 j, 30 j, 3 mois)",
          "Classement quotidien des modèles, datasets et Spaces Hugging Face par Score Radar : popularité, téléchargements, fraîcheur, pertinence.",
          r, md_path="classements.md", artifact_shell=False, crumbs=[("Accueil", "index.html"), ("Classements", None)],
          jsonld=[ld_itemlist(site, f"Classement {lab}", ranking_items(site, per), f"classements.html#{per}") for per, lab in PERIODES if ranking_items(site, per)]))
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
    rows = "".join(f"""<tr><td><a href="{site.item_page(it)}"><strong>{esc(it['nom'])}</strong></a>{' <span class="star">★</span>' if it.get('pertinent') else ''}<div class="sm mut mono">{esc(it.get('org'))}</div></td><td>{esc(TYPE_LABEL.get(it.get('type'), ''))}</td><td>{esc(it.get('tache'))}</td><td class="mono sm">{esc(it.get('taille') or '—')}</td><td class="mono sm">{esc(it.get('licence') or '—')}</td><td class="r">{score_badge(it.get('score'))}</td></tr>""" for it in all_items)
    write("modeles.html", page(site, "modeles.html", "Annuaire des modèles IA suivis : taille, licence, score", f"{len(all_items)} modèles, datasets et Spaces Hugging Face suivis par Radar IA, avec taille, licence, tâche et Score Radar.",
          f'<h1>Modèles, datasets et Spaces suivis</h1><p class="mut">{len(all_items)} éléments, triés par Score Radar. ★ = utile pour l\'IA pratique (local, documents, agents, audio, code, français).</p><div class="tw"><table><thead><tr><th>Nom</th><th>Type</th><th>Tâche</th><th>Taille</th><th>Licence</th><th class="r">Score</th></tr></thead><tbody>{rows}</tbody></table></div>',
          crumbs=[("Accueil", "index.html"), ("Modèles", None)], jsonld=[ld_itemlist(site, "Modèles suivis par Radar IA", all_items[:100], "modeles.html")]))
    for it in all_items:
        p = site.item_page(it)
        arts = [a for a in site.art_sorted if it["_id"] in (a.get("itemIds") or [])]
        hist = it.get("historique") or []
        hist_rows = "".join(f'<tr><td class="num">{d_short(h.get("date"))}</td><td class="r num">{fmt_n(h.get("likes"))}</td><td class="r num">{fmt_n(h.get("downloads"))}</td><td class="r">{score_badge(h.get("score"))}</td></tr>' for h in reversed(hist[-15:]))
        same = [x for x in site.items_in((it.get("domaines") or ["_"])[0]) if x["_id"] != it["_id"]][:4]
        tl = TYPE_LABEL.get(it.get("type"), "Modèle")
        desc = f"{it['nom']} ({it.get('org')}) : {clip(it.get('resume') or '', 110)} Taille {it.get('taille') or 'n.c.'}, licence {it.get('licence') or 'n.c.'}, Score Radar {it.get('score')}/100."
        body = f"""<div class="eb">{esc(tl)} · {esc(it.get('org'))}</div><h1 style="margin:6px 0 10px">{esc(it['nom'])} {score_badge(it.get('score'))}</h1>
<p style="max-width:70ch;font-size:1.08rem">{esc(it.get('resume'))}</p>
<div class="lead" style="margin-top:18px"><div><dl class="kv"><dt>Identifiant</dt><dd><code>{esc(it.get('hfId'))}</code></dd><dt>Organisation</dt><dd>{esc(it.get('org'))}</dd><dt>Tâche</dt><dd>{esc(it.get('tache'))}</dd>
<dt>Taille</dt><dd>{esc(it.get('taille') or 'non communiquée')}</dd><dt>Licence</dt><dd>{esc(it.get('licence') or 'à vérifier sur la fiche')}</dd><dt>Créé le</dt><dd>{d_long(it.get('creeLe'))}</dd>
<dt>Likes</dt><dd class="num">{fmt_n(it.get('likes'))}</dd><dt>Téléchargements</dt><dd class="num">{fmt_n(it.get('downloads'))}</dd><dt>Domaines</dt><dd>{''.join(f'<a class="chip" href="../{site.dom_page(d)}">{esc(site.dom_name(d))}</a>' for d in it.get('domaines') or [])}</dd>
<dt>Pertinent IA pratique</dt><dd>{'oui ★' if it.get('pertinent') else 'non'}</dd><dt>Fiche officielle</dt><dd><a href="{esc(site.hf_url(it))}" rel="noopener">{esc(site.hf_url(it))}</a></dd></dl>
<p class="box sm" style="margin-top:16px"><strong>Pourquoi ça compte.</strong> {esc(it.get('pourquoi'))}</p>{bloc_affiliation(site, it)}</div>
<aside>{f'<h2 style="font-size:1rem">Historique des relevés</h2><div class="tw" style="margin-top:8px"><table style="min-width:0"><thead><tr><th>Date</th><th class="r">Likes</th><th class="r">Téléch.</th><th class="r">Score</th></tr></thead><tbody>{hist_rows}</tbody></table></div>' if hist_rows else ''}</aside></div>
{f'<section><div class="sh"><h2>Articles qui en parlent</h2></div><div class="cards">{"".join(art_card(site, a, "../") for a in arts)}</div></section>' if arts else ''}
{f'<section><div class="sh"><h2>Dans le même domaine</h2></div><div class="cards">{"".join(item_card(site, x, "../") for x in same)}</div></section>' if same else ''}
{bloc_abonnement(site, '../')}"""
        write(p, page(site, p, f"{it['nom']} — {tl} {it.get('tache') or ''} : fiche, licence, score", desc, body, md_path=p.replace(".html", ".md"),
                      crumbs=[("Accueil", "index.html"), ("Modèles", "modeles.html"), (it["nom"], None)], jsonld=[ld_item(site, it)], nav_key="modeles.html"),
              it.get("derniereVue"))
        md = (f"# {it['nom']}\n\n> {it.get('resume')}\n\n- Identifiant Hugging Face : `{it.get('hfId')}` — {site.hf_url(it)}\n- Organisation : {it.get('org')}\n- Type : {tl} · tâche : {it.get('tache')}\n"
              f"- Taille : {it.get('taille') or 'n.c.'} · licence : {it.get('licence') or 'n.c.'}\n- Créé le : {it.get('creeLe') or 'n.c.'}\n- Likes : {it.get('likes')} · téléchargements : {it.get('downloads')}\n"
              f"- Score Radar : {it.get('score')}/100 · pertinent IA pratique : {'oui' if it.get('pertinent') else 'non'}\n- Domaines : {', '.join(site.dom_name(d) for d in it.get('domaines') or [])}\n\n**Pourquoi ça compte.** {it.get('pourquoi')}\n")
        write_md(p.replace(".html", ".md"), it["nom"], md)

    # --- Domaines
    r = '<h1>Domaines</h1><div class="cards" style="margin-top:16px">'
    for dk, dv in site.domaines.items():
        n = len(site.items_in(dk)); na = len([a for a in site.art_sorted if a.get("domaine") == dk])
        r += f'<div class="card"><h3><a href="{site.dom_page(dk)}">{esc(dv.get("nom"))}</a></h3><p>{esc(dv.get("description"))}</p><div class="meta"><span>{n} éléments</span><span>{na} articles</span></div></div>'
        its = site.items_in(dk); arts = [a for a in site.art_sorted if a.get("domaine") == dk]
        p = site.dom_page(dk)
        mois = d_long(site.today).split(" ", 1)[-1]  # « octobre 2026 » : vise les requêtes « meilleur modèle … »
        body = f"""<div class="eb">Mis à jour le {d_long(site.today)}</div><h1 style="margin-top:6px">Meilleurs modèles open source : {esc(dv.get('nom'))}</h1><p class="mut" style="max-width:70ch">{esc(dv.get('description'))} Sélection {esc(mois)} classée par Score Radar.</p>
{f'<section><div class="sh"><h2>Articles</h2></div><div class="cards">{"".join(art_card(site, a, "../") for a in arts)}</div></section>' if arts else ''}
<section><div class="sh"><h2>Meilleurs scores du domaine</h2></div>{f'<div class="cards">{"".join(item_card(site, it, "../", i+1) for i, it in enumerate(its[:12]))}</div>' if its else '<p class="mut">Aucun élément pour le moment.</p>'}</section>"""
        write(p, page(site, p, f"Meilleurs modèles {dv.get('nom')} open source ({mois})", f"Les meilleurs modèles IA open source pour {dv.get('nom')} en {mois} : {dv.get('description')} Classement par Score Radar et analyses en français.",
                      body, crumbs=[("Accueil", "index.html"), ("Domaines", "domaines.html"), (dv.get("nom"), None)], nav_key="domaines.html",
                      jsonld=[ld_itemlist(site, dv.get("nom"), its[:20], p)] if its else None))
    write("domaines.html", page(site, "domaines.html", "Domaines de l'IA open source suivis", "LLM en local, documents et OCR, agents, audio, code, multilingue, image et vidéo, données : les rubriques de Radar IA.",
                                r + "</div>", crumbs=[("Accueil", "index.html"), ("Domaines", None)]))

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
         "Des pages publiques de huggingface.co (tendances, likes sur 30 jours, fiches des modèles), relevées chaque matin par des agents IA. Chaque article cite ses sources."),
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
<h2>Limites</h2><p>Les chiffres proviennent des pages de liste de Hugging Face et sont arrondis. Les benchmarks cités sont ceux des fiches, souvent auto-déclarés : les articles le signalent.</p>
<h2>Licence</h2><p>Textes et données sous <a href="{LICENSE_URL}">CC BY 4.0</a> : réutilisation libre avec mention « Radar IA » et lien.</p></article>"""
    write("methode.html", page(site, "methode.html", "Méthode et Score Radar", "Comment Radar IA relève Hugging Face, calcule le Score Radar et vérifie ses articles.",
                               body, crumbs=[("Accueil", "index.html"), ("Méthode", None)], jsonld=[ld_faq(meth_q)]))

    # --- S'abonner
    feed = site.abs("feed.xml")
    res = "".join(f'<li><a href="{esc(r["url"])}" rel="me noopener">{esc(r.get("nom") or r["url"])}</a></li>' for r in site.cfg.get("reseaux") or [] if has_url(r.get("url")))
    body = f"""<h1>Suivre Radar IA</h1><p class="mut" style="max-width:70ch">Une édition chaque matin vers 9 h : les modèles IA ouverts qui comptent, ceux à tester en local, les scores et les analyses. Gratuit.</p>
{bloc_abonnement(site, '')}
<section><div class="sh"><h2>Lecteurs de flux</h2></div><ul class="ess"><li><a href="feed.xml">Flux RSS 2.0</a> (contenu complet des articles)</li><li><a href="feed.json">JSON Feed 1.1</a></li>
<li><a href="https://feedly.com/i/subscription/feed/{quote(feed, safe='')}" rel="noopener">Ajouter à Feedly</a></li><li><a href="https://www.inoreader.com/?add_feed={quote(feed, safe='')}" rel="noopener">Ajouter à Inoreader</a></li></ul></section>
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
    api_items = [dict(clean(it), id=it["_id"], page=site.abs(site.item_page(it))) for it in all_items]
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
            "## Articles", ""] + [f"- [{a['titre']}]({site.abs('articles/' + a['_slug'] + '.md')}): {clip(a.get('chapo', ''), 160)}" for a in site.art_sorted] + [
            "", "## Fiches modèles", ""] + [f"- [{it['nom']}]({site.abs(site.item_page(it).replace('.html', '.md'))}): {it.get('org')}, {it.get('tache')}, score {it.get('score')}" for it in all_items[:60]] + [
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
    (out / "404.html").write_text(page(site, "404.html", "Page introuvable", "Cette page n'existe pas ou plus.", '<h1>Page introuvable</h1><p><a href="index.html">Retour à la une</a> · <a href="llms.txt">llms.txt</a></p>'), encoding="utf-8")
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
