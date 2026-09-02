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
  "build": {},
  "search": {}
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

### `blog`
Réglages billets :
- activation
- archive
- tri
- pagination minimale
- `generate_rss_feed` : génère `feed.xml` (RSS 2.0) si `site.base_url` est renseigné

### `menus`
- `top`
- `side`

### `render`
- thème
- templates (`html_template`, `post_template`, `home_template` : noms de fichiers optionnels
  recherchés dans `paths.templates_dir` ; s'ils sont absents, le document HTML intégré par
  défaut est utilisé — voir « Personnalisation du thème » plus bas)
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
- `generate_sitemap` : génère `sitemap.xml` si `site.base_url` est renseigné

### `search`
Recherche statique côté client (index JSON généré au build, filtrage en
sous-chaîne dans le navigateur, sans serveur) :
- activation
- longueur de l'extrait de recherche

## Exemple minimal

Voir `examples/minimal_project/config/site.json`.

## RSS, sitemap et SEO

Si `site.base_url` est renseigné, le build génère automatiquement, à la racine du site :
- `feed.xml` (flux RSS 2.0 des billets), si `blog.generate_rss_feed` est actif ;
- `sitemap.xml` (pages, billets, accueil, archive), si `build.generate_sitemap` est actif.

Sans `site.base_url`, ces fichiers ne sont pas générés (les URLs RSS/sitemap doivent être
absolues) et un avertissement apparaît dans le rapport de build.

Chaque page générée reçoit aussi une balise `<meta name="description">` (à partir du champ
`description` du front matter, ou de `site.description` à défaut), une balise
`<link rel="canonical">` et des balises Open Graph de base (`og:title`, `og:description`,
`og:url`, `og:image` si une bannière est configurée), dès que `site.base_url` est renseigné.

## Personnalisation du thème

- **CSS/JS** : déposer `theme/css/site.css` et/ou `theme/js/app.js` /
  `theme/js/lightbox.js` (chemin défini par `paths.theme_dir`) surcharge les fichiers
  intégrés correspondants ; les fichiers non fournis restent ceux du thème par défaut.
- **Structure HTML** : déposer un fichier nommé comme `render.html_template`,
  `render.post_template` ou `render.home_template` dans `paths.templates_dir` remplace le
  document HTML généré par défaut pour ce type de contenu. Le fichier est un gabarit texte
  utilisant la syntaxe `string.Template` de Python (`$variable`), avec les variables
  disponibles : `lang`, `title`, `site_title`, `seo_meta`, `css_href`, `lightbox_enabled`,
  `banner`, `top_menu`, `side_menu`, `side_class`, `content`, `footer`, `scripts`.
  En l'absence de fichier, le document par défaut (menus, bannière, pied de page) est utilisé.

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
