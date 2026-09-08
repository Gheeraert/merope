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
  "search": {},
  "ftp": {}
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
Réglages page d’accueil (toujours générée) :
- mode (page fixe ou derniers billets, texte intégral)
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
- `validate_commons_publishing` : vérifie le TEI généré contre le schéma normatif TEI Commons
  Publishing (grammaire RelaxNG et règles Schematron embarquées), purement diagnostique par
  défaut (voir `build.fail_on_invalid_commons_publishing` ci-dessous)

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
- comportement sur erreurs (`fail_on_missing_assets`, `fail_on_invalid_config`,
  `fail_on_broken_links`, `fail_on_invalid_commons_publishing` : chacune, décochée, transforme
  le problème correspondant en simple avertissement plutôt qu'en échec de génération)
- `check_broken_links` : vérifie liens/médias internes, pages orphelines, balises canoniques et
  données structurées (JSON-LD) déjà présentes, meta description et `<h1>` unique
- commande Pandoc
- `generate_sitemap` : génère `sitemap.xml` si `site.base_url` est renseigné
- `generate_redirects` : page de redirection automatique à l'ancienne adresse d'un contenu dont
  le slug change

### `search`
Recherche statique côté client (index JSON généré au build, filtrage en
sous-chaîne dans le navigateur, sans serveur) :
- activation
- longueur de l'extrait de recherche

### `ftp`
Réglages de publication FTP/FTPS (fenêtre « Publier (FTP)... », voir `docs/GUIDE_UI.md`) :
- hôte, port, utilisateur, dossier distant, URL du site publié une fois en ligne
- `use_tls` (FTPS), `passive_mode`
- `password` : jamais persisté ici — chargé/écrit dans le gestionnaire d'identifiants du
  système via la dépendance optionnelle `keyring` (`ftp_credentials.py`), présent uniquement en
  mémoire le temps d'une session tant que `keyring` n'est pas installé

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
`<link rel="canonical">`, des balises Open Graph (`og:title`, `og:description`, `og:url`,
`og:image` si une bannière est configurée) et Twitter Card, ainsi qu'un bloc de données
structurées JSON-LD (`BlogPosting` pour un billet, avec date de publication/modification et
auteur ; `WebSite` pour l'accueil), dès que `site.base_url` est renseigné. `check_broken_links`
(voir `build` ci-dessus) vérifie ce qui est déjà présent (JSON valide, champs attendus, balise
canonique cohérente) mais ne détecte pas une balise ou un bloc totalement absent d'une page qui
en attendrait un.

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
