# Radar IA — audience et revenus

Objectif fixé le 11/10/2026 : être rentable au 10/11/2026 (revenus ≥ coûts directs).
Coûts directs actuels : 0 € (GitHub Pages gratuit ; les agents tournent sur l'abonnement Claude existant).

## Ce qui est déjà en place (automatique)
| Levier | Fonctionnement |
|---|---|
| Référencement Google/Bing | Pages statiques, JSON-LD, sitemap, titres « Meilleurs modèles … (mois année) » sur les domaines |
| Contenu vérifié | Faits relus sur l'API Hugging Face à chaque publication ; guides français, licences, GGUF, familles de modèles |
| Assistants IA (GEO) | `llms.txt`, `.md` jumeaux, API JSON + OpenAPI, robots IA autorisés |
| IndexNow | Chaque déploiement signale toutes les pages à Bing (→ ChatGPT Search, Copilot), Yandex, Seznam, Naver |
| Partage | Image `og.png` 1200×630, liens de partage sans traceur sous chaque article |
| Abonnement | Page `abonnement.html` + encart sur la une, les articles, les éditions et les fiches (RSS tant que la newsletter n'est pas branchée) |
| Partenaires | Page `soutenir.html#annoncer` (offres, règles, contact) + encart « Espace partenaire » sur la une, les éditions, les articles |
| Réseaux | Après chaque déploiement, les nouveaux articles partent sur Bluesky et Mastodon dès que les secrets existent |
| Agents | Synchro GitHub (quotidien), Diffusion (quotidien), Croissance SEO/GEO (hebdo), Revenus & pilotage (hebdo) |

## Ce que seul le propriétaire peut faire (comptes, signatures, paiements)
Par ordre d'impact. Chaque ligne active un bloc déjà prêt : remplir le champ dans `config/site.json`, commit, push.

1. **Google Search Console** (10 min) — propriété « préfixe d'URL » `https://clauzelfamille-dot.github.io/radar-ia/`,
   méthode « balise HTML » → copier le code dans `verification.google`, puis soumettre `sitemap.xml`.
2. **Bing Webmaster Tools** (5 min) — importer depuis Search Console, ou balise → `verification.bing`.
3. **Newsletter** (15 min) — Buttondown (le plus simple) ou Brevo (français, gratuit jusqu'à 300 envois/jour) →
   `newsletter.action` (+ `champEmail`, `champsCaches`). C'est l'actif principal : une audience qui revient et qui se sponsorise.
4. **Profil LinkedIn** — publier chaque matin le post préparé par l'agent Diffusion (dossier `diffusion/` du projet).
   Le réseau personnel est la source de visiteurs la plus rapide les 30 premiers jours.
5. **Bluesky + Mastodon** (10 min) — créer « Radar IA », puis dans GitHub → Settings → Secrets → Actions :
   `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` (mot de passe d'application), `MASTODON_URL`, `MASTODON_TOKEN`.
   Ajouter les URL des profils dans `reseaux`.
6. **Mesure d'audience** — GoatCounter (sans cookie, sans bandeau) → `mesure.pixel` = `https://CODE.goatcounter.com/count?p={path}`.
7. **Dons** — Ko-fi, Liberapay ou GitHub Sponsors → `soutien[].url`.
8. **Affiliation GPU** — programme de parrainage d'un loueur de GPU → `affiliation.gpu` (mention « lien affilié » automatique).
9. **Adresse du site** — créer une boîte dédiée (ex. Gmail ou Proton « radar.ia… », ou contact@ d'un futur nom de domaine)
   → `contact.email`. Sans elle : ticket GitHub public. Les messages de prospection préparés (`pilotage/prospection-*.md`)
   l'utilisent comme adresse de réponse.
10. **Statut** — pour facturer un sponsor, il faut une structure (micro-entreprise par exemple) ; vérifier aussi la clause
    d'exclusivité du contrat de travail. Les prix des offres sont dans `offres` (tarifs de lancement modifiables).
11. **Facultatif** — nom de domaine (~10 €/an) : marque plus forte, éligibilité aux régies publicitaires ; GitHub redirige
    automatiquement l'ancienne adresse.

## Règles (non négociables)
- Tout contenu payant est signalé (« Partenaire », « contenu sponsorisé », « lien affilié ») et ses liens portent `rel="sponsored"`.
- Le Score Radar et les classements ne dépendent jamais d'un partenaire.
- Aucune publication automatique ailleurs que sur les comptes Radar IA ; aucun message envoyé à un tiers sans validation humaine.
- Pas de faux avis, faux abonnés, achat de liens, ni contenu copié.

## Indicateurs suivis par l'agent « Revenus & pilotage »
Pages indexées · visites (si GoatCounter) · abonnés · posts publiés · prospects contactés · revenus encaissés ·
coûts · solde. Saisie manuelle des revenus et abonnés : `pilotage/revenus.csv` dans le dossier du projet (hors dépôt).
