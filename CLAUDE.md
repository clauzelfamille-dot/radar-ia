# Radar IA — contexte projet pour Claude Code

Langue : français uniquement (code commenté en français, messages de commit en français).
Propriétaire : Guillaume, compte GitHub `clauzelfamille-dot`.

## Ce qu'est le projet
Site statique de veille sur les modèles IA ouverts (Hugging Face), optimisé SEO + GEO (moteurs et assistants IA).
- `build/build.py` : générateur Python sans dépendance → `dist/` (HTML statique, .md jumeaux, JSON-LD, sitemap, RSS,
  JSON Feed, llms.txt, llms-full.txt, API `api/v1/*.json`, openapi.json, robots.txt).
- `data/<collection>/<id>.json` : export de la base (items, articles, editions, classements, domaines).
- `.github/workflows/pages.yml` : à chaque push sur main, génère et déploie sur GitHub Pages.
- `SEO-GEO.md` : cahier des charges de référencement à respecter.

## Commandes
- Générer : `python3 build/build.py --data data --out dist --site-url https://clauzelfamille-dot.github.io/radar-ia/`
- Prévisualiser : `python3 -m http.server -d dist 8000`
- Avant tout commit, vérifier : JSON-LD parsable, aucun lien interne cassé, sitemap.xml et feed.xml valides,
  pas de débordement horizontal à 390 px.

## Chaîne d'agents (tâches planifiées claude.ai, heure de Paris)
1/4 Veille 06:57 · 2/4 Classements 07:23 · 3/4 Rédacteur 07:43 · 4/4 Rédaction en chef 08:13 · 5/5 Publication web 08:37.
Ils écrivent dans la base de l'artefact back-office https://claude.ai/artifact/EDEgpcyd31Eh6YooaD2L2w ;
le site public miroir est https://claude.ai/artifact/FiYty6LrpA8fpC6WMEyVgd. L'agent 5 pousse `data/` ici si le dépôt
lui est attaché.

## Règles
- Ne jamais inventer de chiffres : les données viennent de `data/`.
- Score Radar = 40·popularité + 30·diffusion + 20·fraîcheur + 10·pertinence (voir build.py et SEO-GEO.md).
- Garder le site sans JavaScript côté lecteur ; tout le texte doit être dans le HTML.
