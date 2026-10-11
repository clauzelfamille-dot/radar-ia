# Radar IA — contexte projet pour Claude Code

Langue : français uniquement (code commenté en français, messages de commit en français).
Propriétaire : Guillaume, compte GitHub `clauzelfamille-dot`.

## Ce qu'est le projet
Site statique de veille sur les modèles IA ouverts (Hugging Face), optimisé SEO + GEO (moteurs et assistants IA).
- `build/build.py` : générateur Python sans dépendance → `dist/` (HTML statique, .md jumeaux, JSON-LD, sitemap, RSS,
  JSON Feed, llms.txt, llms-full.txt, API `api/v1/*.json`, openapi.json, robots.txt).
- `data/<collection>/<id>.json` : export de la base (items, articles, editions, classements, domaines).
- `.github/workflows/pages.yml` : à chaque push sur main, génère, déploie sur GitHub Pages, signale les pages
  (IndexNow) et diffuse les nouveaux articles (Bluesky/Mastodon si les secrets existent).
- `config/site.json` : leviers d'audience et de revenus (vérification moteurs, mesure, newsletter, sponsor, dons,
  affiliation, IndexNow, réseaux). Champ vide = bloc masqué. Mode d'emploi : `MONETISATION.md`.
- `static/` : fichiers fixes copiés dans `assets/` (image de partage `og.png`).
- `build/verifier.py` : contrôles avant publication ; `build/indexnow.py` ; `build/diffusion.py`.
- `SEO-GEO.md` : cahier des charges de référencement à respecter.

## Commandes
- Générer : `python3 build/build.py --data data --out dist --site-url https://clauzelfamille-dot.github.io/radar-ia/`
- Prévisualiser : `python3 -m http.server -d dist 8000`
- Contrôler : `python3 build/verifier.py dist` (JSON-LD, liens internes, XML, JSON) ; vérifier aussi l'absence de
  débordement horizontal à 390 px.

## Chaîne d'agents (tâches planifiées claude.ai, heure de Paris)
1/4 Veille 06:57 · 2/4 Classements 07:23 · 3/4 Rédacteur 07:43 · 4/4 Rédaction en chef 08:13 · 5/5 Publication web 08:37.
Ils écrivent dans la base de l'artefact back-office https://claude.ai/artifact/EDEgpcyd31Eh6YooaD2L2w ;
le site public miroir est https://claude.ai/artifact/FiYty6LrpA8fpC6WMEyVgd. L'agent 5 pousse `data/` ici si le dépôt
lui est attaché.
Tâches planifiées locales (application Claude, une conversation par passage) : Synchro GitHub 08:55 (exporte la base
vers `data/`, contrôle, pousse), Diffusion 09:20 (posts prêts à publier dans `../diffusion/`), Croissance SEO/GEO
le lundi 10:00, Revenus & pilotage le lundi 10:30 (rapport dans `../pilotage/`).

## Règles
- Ne jamais inventer de chiffres : les données viennent de `data/`.
- Score Radar = 40·popularité + 30·diffusion + 20·fraîcheur + 10·pertinence (voir build.py et SEO-GEO.md).
- Garder le site sans JavaScript côté lecteur ; tout le texte doit être dans le HTML.
- Monétisation : tout contenu payant est signalé et en `rel="sponsored"` ; aucun partenaire n'influence le Score Radar ;
  aucun message envoyé à un tiers sans validation de Guillaume (brouillons seulement).
