# Architecture du projet

## Vue d’ensemble

Le système est organisé en modules correspondant au pipeline réel :

1. configuration
2. chargement du contenu
3. normalisation Markdown
4. conversion Markdown → TEI
5. post-traitement TEI
6. transformation TEI → HTML
7. assemblage du site
8. interface graphique

## Modules

### `config/`
- modèles
- lecture / écriture JSON
- validation
- valeurs par défaut

### `ui/`
- fenêtre principale
- dialogues
- éditeur de menus
- panneaux bannière / médias / notes
- éditeur de contenu WYSIWYG (pages/billets)

### `content/`
- chargement des fichiers
- métadonnées
- slugification
- copie des assets

### `markdown/`
- nettoyage des exports Google Docs
- front matter
- normalisation avant Pandoc

### `tei/`
- appel à Pandoc
- enrichissement du `teiHeader`
- post-traitement
- validation TEI légère

### `render/`
- XSLT runner
- navigation
- lightbox
- marge des notes

### `build/`
- copie des ressources
- écriture des pages
- rapports
- prévisualisation locale

## Règles d’architecture
- pas de logique métier dans l’UI
- pas de parseur Markdown maison
- Pandoc reste la brique de conversion
- HTML final produit à partir de la TEI

### Exception bornée : éditeur de contenu WYSIWYG

L’éditeur de contenu intégré (`ui/content_editor.py`) permet de rouvrir en
WYSIWYG un fichier qu’il a lui-même écrit. Cela suppose un import Markdown
limité (`markdown/rich_text_import.py`), ce qui touche en apparence à la
règle « pas de parseur Markdown maison ». Portée de l’exception :
- cet importeur ne comprend que le sous-ensemble Markdown produit par
  `markdown/rich_text_export.py` (titres ATX, gras/italique/barré, liens,
  images, notes, listes simples, citations, tableaux pipe) ;
- tout ce qu’il ne reconnaît pas avec confiance devient un bloc « verbatim »
  reproduit tel quel, jamais deviné ni perdu ;
- il ne remplace en rien Pandoc : la chaîne de génération du site
  (Markdown → TEI → HTML) reste exclusivement basée sur Pandoc et n’utilise
  jamais cet importeur.

Le collage riche depuis Word/Google Docs (`ui/clipboard_html.py` +
`markdown/html_paste_import.py`) est une seconde exception du même esprit,
mais pour du HTML plutôt que du Markdown : lecture du format presse-papiers
« HTML Format » (via `ctypes`, sans dépendance supplémentaire) puis import
borné (`html.parser.HTMLParser`) vers le même modèle de blocs. Portée
identique : reconnaît un sous-ensemble pratique (paragraphes, titres,
gras/italique/barré, liens, listes à un niveau, citations, images), et tout
élément non reconnu conserve son texte visible plutôt que d’afficher du
HTML brut ou de planter. Ne touche pas non plus au pipeline Pandoc.
