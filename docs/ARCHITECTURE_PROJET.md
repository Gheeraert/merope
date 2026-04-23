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
