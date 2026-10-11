# Radar IA — charte graphique v2 (octobre 2026)

**Concept : l'instrument de bord éditorial.** Un quotidien du matin (titres à empattement, filets, numérotation)
croisé avec un écran radar (vert phosphore, jauges, points de signal). Sobre, lisible, fiable : on vient chercher
des faits vérifiés, pas du spectacle.

## Logo
- Symbole : cercle extérieur, cercle intérieur à 50 %, secteur de balayage (vert à 30 %), aiguille verte, un point
  ambre (le signal détecté), centre plein. SVG en ligne (`LOGO` dans `build/build.py`), `currentColor` pour s'adapter
  au fond ; favicon `assets/favicon.svg` (fond encre, traits verts).
- Logotype : « Radar IA » en serif gras ; signature en capitales mono : « LE QUOTIDIEN DES MODÈLES IA OUVERTS ».
- Zone de protection : la hauteur du symbole. Ne pas déformer, ne pas changer les couleurs du symbole.

## Couleurs
| Rôle | Clair | Sombre |
|---|---|---|
| Papier (fond) | `#f6f4ee` | `#0b0f12` |
| Surface (cartes) | `#fffefa` | `#11171b` |
| Encre (texte) | `#12161a` | `#e7ece8` |
| Texte secondaire | `#4a525c` | `#a6b0aa` |
| Filets | `#ddd8cc` | `#24302c` |
| **Signal** (accent, liens, jauges ≥ 70) | `#0a7155` | `#3fd69b` |
| Signal sombre (liens au survol) | `#065240` | `#7be8bd` |
| **Ambre** (alerte, point du logo, ★) | `#a8530a` | `#f0a64a` |
| Bandeau et pied de page | `#12161a` | `#050709` |

Couleurs de domaine (pastilles, liseré haut des cartes ; jamais seules porteuses d'information, toujours avec le nom) :
local `#2463d6` · documents `#a8530a` · agents `#7a3fd6` · audio `#c42a72` · code `#08799a` · multilingue `#178a3e` ·
image-vidéo `#d2501a` · données `#5b7a12` · tendances `#5f6b78` (versions éclaircies en mode sombre).

## Typographie (aucune police téléchargée)
- Titres : serif système — Iowan Old Style, Charter, Sitka, Cambria, Georgia.
- Texte : sans-serif système — system-ui, Segoe UI, Roboto.
- Données, étiquettes, navigation : mono système — ui-monospace, Cascadia Code, JetBrains Mono, Consolas.
- Sur-titres (`.eb`) : mono, capitales, interlettrage 0,12 em.

## Composants
- **Bandeau d'édition** (haut de page) : date de l'édition, liens S'abonner · RSS · llms.txt.
- **En-tête** : logo, navigation mono, bouton « S'abonner » plein ; double filet sous l'en-tête (code du quotidien).
- **Titres de section** : filet épais au-dessus, titre serif, lien mono à droite.
- **L'essentiel** : liste numérotée 01, 02, 03 en mono vert.
- **Jauge Score Radar** : anneau (conic-gradient) proportionnel au score ; vert si ≥ 70, gris sinon.
- **Le radar du jour** : top du jour en barres horizontales.
- **Cartes** : liseré haut à la couleur du domaine, titre serif, méta mono.
- **Tableaux** : en-têtes mono capitales, filet épais, survol de ligne.
- **Encarts** : abonnement (fond vert pâle, filet gauche), espace partenaire (pointillés), toujours signalés.

## Ton
Phrases courtes, chiffres sourcés, pas de superlatifs, pas d'émojis. On dit ce qu'on ne sait pas.
