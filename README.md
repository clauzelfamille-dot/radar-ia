# Radar IA — site public (GitHub Pages)

Site statique en français sur les modèles IA ouverts (Hugging Face) : édition du jour, classements avec Score Radar,
articles, fiches modèles, FAQ, `llms.txt`, API JSON + OpenAPI, RSS. Pensé pour Google/Bing **et** pour les assistants IA
(voir `SEO-GEO.md`).

**En ligne : https://clauzelfamille-dot.github.io/radar-ia/** — audience et revenus : voir `MONETISATION.md`.

## Mise en ligne (fait le 11/10/2026)
1. Sur github.com, créer un dépôt public **`radar-ia`** (compte `clauzelfamille-dot`), sans README.
2. « Add file » → « Upload files » : déposer **tout le contenu** de ce dossier (y compris le dossier caché `.github`).
   Ou en ligne de commande :
   `git init && git add . && git commit -m "Radar IA" && git branch -M main && git remote add origin https://github.com/clauzelfamille-dot/radar-ia.git && git push -u origin main`
3. Settings → Pages → Source : **GitHub Actions**.
4. Le workflow publie le site sur `https://clauzelfamille-dot.github.io/radar-ia/` (onglet Actions pour suivre).
5. Référencement : Google Search Console et Bing Webmaster Tools → ajouter le site → soumettre `sitemap.xml`.

## Mise à jour quotidienne
L'agent « Radar IA 5/5 — Publication web » exporte la base chaque matin vers `data/` et pousse sur `main` si le dépôt est
attaché à son environnement (claude.ai/code → environnement → dépôts). Le workflow régénère alors le site.
Sans ce branchement, il met à jour la version hébergée sur claude.ai et vous prévient.

## Générer en local
`python3 build/build.py --data data --out dist --site-url https://clauzelfamille-dot.github.io/radar-ia/`
