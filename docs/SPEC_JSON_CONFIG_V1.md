# Spécification JSON de configuration V1

Ce document fixe le **contrat technique** du fichier `site.json`. Pour la description exhaustive de chaque clé, sa valeur par défaut et son statut dans l’interface, voir `docs/REFERENCE_CONFIGURATION.md`. Pour l’usage courant, voir `docs/GUIDE_UI.md`.

## Structure générale

Le modèle courant peut contenir les sections suivantes :

```json
{
  "version": "1.0",
  "site": {},
  "top_banner": {},
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

Le validateur exige les sections racine historiques `version`, `site`, `banner`, `paths`, `content`, `home`, `blog`, `menus`, `render`, `media_handling`, `notes_rendering`, `footer`, `build` et `search`. `top_banner` et `ftp` peuvent manquer dans un ancien fichier et reprennent alors leurs valeurs par défaut au chargement.

Les clés inconnues d’une section sont ignorées lors de la construction du modèle. Une sauvegarde ultérieure sérialise le modèle courant : une ancienne clé qui n’existe plus est donc supprimée. À l’inverse, les clés encore valides mais masquées dans l’interface sont préservées lors d’un aller-retour JSON → interface → JSON.

## Invariants de validation

La configuration doit respecter au minimum les règles suivantes :

- `version` est une chaîne non vide ;
- `site.title` et `site.language` sont non vides ;
- `site.base_url` et `ftp.site_url`, lorsqu’ils sont renseignés, commencent par `http://` ou `https://` ;
- les chemins requis `pages_dir`, `posts_dir`, `assets_dir`, `theme_dir`, `templates_dir`, `xslt_dir`, `output_dir` et `tei_dir` sont non vides ; les différents rôles doivent viser des dossiers distincts ;
- `home.mode` vaut `page` ou `recent_posts` ;
- les champs booléens sont de vrais booléens JSON ;
- les tailles et compteurs numériques sont des entiers dans leurs bornes ;
- `blog.archive_path` est formé de segments de slug sûrs, sans `..` ni chemin absolu ;
- `menus.top` et `menus.side` sont des listes valides ;
- les cibles externes de menu sont des URL HTTP(S) ;
- le menu latéral ne dépasse pas section → sous-section → lien.

L’interface graphique et la CLI exécutent cette validation avant la génération. Le champ historique `build.fail_on_invalid_config` est encore conservé dans le modèle pour compatibilité, mais ne désactive pas cette validation dans ces deux parcours.

La détection des collisions de chemins est lexicale et ne consulte pas le disque : le validateur uniformise les séparateurs et réduit les composants redondants `.` et `..`. Il ne résout pas les liens symboliques ni les autres équivalences dépendant du système de fichiers. Indépendamment de cette validation, le builder résout chaque chemin configuré et refuse ceux qui sortent de `project_root`. Une syntaxe absolue n’autorise donc pas l’accès à un dossier extérieur au projet.

## Front matter des contenus

Chaque fichier Markdown publié doit commencer par un front matter YAML. Les champs obligatoires sont :

- `title` ;
- `slug` ;
- `type`, égal à `page` ou `post` ;
- `date` au format `YYYY-MM-DD` pour un billet.

`draft: true` exclut le contenu de la génération.

Exemple page :

```yaml
---
title: "Page de référence"
slug: "page-reference"
type: "page"
---
```

Exemple billet :

```yaml
---
title: "Billet de référence"
slug: "billet-reference"
type: "post"
date: "2026-09-18"
---
```

Le paramètre historique `content.use_front_matter` reste présent pour compatibilité, mais le pipeline courant exige toujours ce front matter.

## Accueil

`home.mode = "page"` utilise `home.source` comme contenu de `index.html`.

`home.mode = "recent_posts"` construit l’accueil à partir des derniers billets publiés. `home.recent_posts_count` règle leur nombre ; `home.recent_posts_excerpt_length` règle la longueur approximative de l’extrait affiché avant le lien vers le billet complet.

`home.layout` est conservé pour compatibilité mais ne choisit plus le gabarit HTML : celui-ci est `render.home_template`.

## RSS, sitemap, robots et SEO

Si `site.base_url` est renseigné :

- `blog.generate_rss_feed` peut produire `feed.xml` lorsque le blog est actif ;
- `build.generate_sitemap` peut produire `sitemap.xml`.

`build.generate_robots_txt` peut produire `robots.txt` même sans Base URL. La référence au sitemap n’y est ajoutée que si le sitemap est effectivement générable.

Les pages générées utilisent les métadonnées disponibles pour la description, la balise canonique, Open Graph/Twitter et le JSON-LD. `build.check_broken_links` vérifie notamment les liens et médias internes, les pages orphelines, les canoniques et JSON-LD déjà présents, la meta description et l’unicité du `<h1>`.

## TEI Commons Publishing

Lorsque `render.validate_commons_publishing` est actif, le TEI produit est vérifié avec le profil Commons Publishing au moyen des règles RelaxNG et Schematron embarquées.

Par défaut, une non-conformité est un avertissement. `build.fail_on_invalid_commons_publishing = true` la transforme en échec de génération. Les blocs de code et règles horizontales peuvent encore produire un TEI hors profil.

## Personnalisation du thème

- **CSS/JS** : les ressources placées sous `paths.theme_dir` peuvent surcharger les ressources intégrées correspondantes.
- **Structure HTML** : `render.html_template`, `render.post_template` et `render.home_template` sont recherchés dans `paths.templates_dir`.
- **TEI → HTML** : `render.tei_to_html_xslt` est recherché dans `paths.xslt_dir`.

Les gabarits HTML personnalisés utilisent `string.Template` de Python. Les variables disponibles sont notamment `lang`, `title`, `site_title`, `seo_meta`, `css_href`, `lightbox_enabled`, `banner`, `top_menu`, `side_menu`, `side_class`, `content`, `footer` et `scripts`.

## Publication FTP/FTPS et mot de passe

La section `ftp` contient les paramètres de connexion et de destination.

Le champ `password` a un traitement particulier : MÉROPE tente de le persister dans le gestionnaire d’identifiants du système. Si ce stockage réussit, le mot de passe est retiré du JSON enregistré. S’il échoue, il peut être conservé en clair dans `site.json` pour ne pas être perdu, avec avertissement au moment de la sauvegarde. Le JSON ne doit donc pas être supposé systématiquement exempt de secret.

## Exemple complet

La manière la plus fiable d’obtenir un fichier complet et à jour est de créer un projet depuis l’interface avec **Nouveau projet...**, puis d’examiner `config/site.json`. L’exemple minimal du dépôt reste utile pour les tests et démonstrations : `examples/minimal_project/config/site.json`.
