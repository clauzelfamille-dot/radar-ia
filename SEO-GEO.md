# Radar IA — cahier des charges de référencement (SEO + GEO)

Rôle tenu : expert référencement. « GEO » (Generative Engine Optimization) = être trouvé, lu et cité par les assistants IA
(ChatGPT, Claude, Perplexity, Gemini, Copilot, Mistral Le Chat) et par les agents qui naviguent ou appellent des API.

## Diagnostic de départ
La page Claude actuelle est une application qui charge ses données en JavaScript après connexion. Un robot (Googlebot,
GPTBot, ClaudeBot, PerplexityBot) n'y voit qu'une coquille vide : référencement nul. Il faut un site **statique**, dont tout
le texte est dans le HTML, sur un domaine public.

## Exigences retenues
1. **Contenu dans le HTML** : chaque page lisible sans JavaScript ; une URL stable par article, édition, domaine, modèle.
2. **Pages longue traîne** : une fiche par modèle / dataset / Space suivi (« GLiNER2.5-Decide : taille, licence, score »),
   c'est ce que tapent les geeks et ce que les IA cherchent.
3. **Données structurées JSON-LD** : WebSite + Organization (toutes pages), NewsArticle (articles), ItemList (classements),
   SoftwareApplication (fiches modèles), Dataset (données ouvertes, éligible Google Dataset Search), FAQPage (méthode et FAQ),
   BreadcrumbList partout.
4. **Fichiers pour les IA** : `llms.txt` (format llmstxt.org), `llms-full.txt` (tout le contenu en Markdown), une version
   `.md` de chaque page annoncée par `<link rel="alternate" type="text/markdown">`.
5. **API ouverte pour les agents** : `api/v1/*.json` (articles, classements, items, éditions, domaines) décrite par
   `openapi.json` ; licence CC BY 4.0 affichée.
6. **Découverte** : `sitemap.xml` (avec lastmod), `robots.txt` qui autorise explicitement les robots IA et de recherche,
   flux `feed.xml` (RSS 2.0 avec contenu complet) et `feed.json` (JSON Feed 1.1).
7. **Balises** : title ≤ 60 caractères, meta description ≤ 155, canonical, Open Graph, Twitter Card, `lang="fr"`.
8. **Réponses directes** : page FAQ générée chaque jour à partir des données (« Quels modèles IA sont les plus populaires
   cette semaine ? », « Quel modèle OCR tourne en local ? »…) : format question → réponse courte → lien. C'est le format
   que les moteurs de réponse reprennent.
9. **Fraîcheur** : régénération quotidienne après la chaîne d'agents ; dates visibles et dans le JSON-LD.
10. **Performance** : zéro dépendance JS, une feuille CSS, polices système + une police mono ; pages < 60 ko.

## Après mise en ligne sur un domaine public (actions à faire une fois, hors de portée de cette session)
- Déclarer le site dans Google Search Console et Bing Webmaster Tools, soumettre `sitemap.xml`
  (Bing alimente aussi ChatGPT Search et Copilot).
- Proposer le flux RSS à Feedly / Inoreader ; poster le lien `llms.txt` dans les annuaires llms.txt (llmstxt.site, directory.llmstxt.cloud).
- Lier le site depuis le profil GitHub et un profil Hugging Face (lien sortant d'autorité dans la niche).
