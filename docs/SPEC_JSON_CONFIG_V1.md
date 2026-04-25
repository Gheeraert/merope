# Spécification JSON de configuration V1

## Structure générale

```json
{
  "version": "1.0",
  "site": {},
  "banner": {},
  "paths": {},
  "content": {},
  "home": {},
  "blog": {},
  "menus": {},
  "render": {},
  "media_handling": {},
  "notes_rendering": {},
  "footer": {},
  "build": {}
}
```

## Sections

### `site`
Identité générale du site :
- titre
- sous-titre
- URL de base
- langue
- auteur
- description

### `banner`
Bannière supérieure :
- activation
- image
- lien
- alt
- hauteur
- overlay éventuel

### `paths`
Chemins de projet :
- `pages_dir`
- `posts_dir`
- `assets_dir`
- `theme_dir`
- `templates_dir`
- `xslt_dir`
- `output_dir`
- `tei_dir`

### `content`
Réglages du contenu source :
- format source
- origine Google Docs
- front matter
- slugification
- copie des assets liés

### `home`
Réglages page d’accueil :
- activation
- source
- layout
- billets récents

### `blog`
Réglages billets :
- activation
- archive
- tri
- pagination minimale

### `menus`
- `top`
- `side`

### `render`
- thème
- templates
- XSLT
- pretty print
- conservation de la TEI
- activation de la lightbox

### `media_handling`
- stratégie de récupération des médias
- dossier images
- copie vers la sortie
- figures cliquables
- regroupement par article

### `notes_rendering`
- mode de rendu
- activation des notes marginales
- activation des notes complètes
- longueur de l’amorce marginale
- emplacement des notes finales

### `footer`
Texte et options de pied de page.

### `build`
Options techniques :
- nettoyage du dossier de sortie
- copie des assets
- comportement sur erreurs
- commande Pandoc

## Exemple minimal

Voir `examples/minimal_project/config/site.json`.

## Format Obligatoire Des Fichiers Markdown

Le front matter YAML est obligatoire pour chaque document publié.

Champs obligatoires (tous contenus):
- `title`
- `slug`
- `type` (`page` ou `post`)

Règles supplémentaires:
- si `type: post`, alors `date` est obligatoire au format `YYYY-MM-DD`;
- si `draft: true`, le contenu est ignoré pendant le build;
- aucun fallback implicite ne doit publier un document incomplet.

Exemple page:

```yaml
---
title: "Page de référence"
slug: "page-reference"
type: "page"
---
```

Exemple billet:

```yaml
---
title: "Billet de référence"
slug: "billet-reference"
type: "post"
date: "2026-04-25"
---
```
