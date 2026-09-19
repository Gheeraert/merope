# Référence de configuration MÉROPE

Cette page décrit le modèle de configuration actuel de MÉROPE. Elle complète le guide utilisateur (`docs/GUIDE_UI.md`) en recensant aussi les paramètres **non affichés dans l’interface**, conservés pour compatibilité et pour les projets qui éditent directement `site.json`.

Les valeurs indiquées sont les valeurs par défaut du modèle Python de la branche courante.

## Légende

- **UI** : réglage visible dans la fenêtre principale ;
- **dialogue** : visible dans une fenêtre spécialisée (menus ou publication FTP) ;
- **masqué** : conservé dans le modèle et dans les anciens JSON, mais retiré de l’interface principale ; la ligne précise séparément si le paramètre agit encore sur le logiciel ;
- **interne** : champ technique ou structure de données, généralement manipulé par l’interface plutôt qu’à la main.

Les clés inconnues appartenant à d’anciens JSON sont ignorées au chargement et disparaissent lors d’une sauvegarde si elles ne font plus partie du modèle. Les clés encore valides mais masquées sont au contraire préservées par l’interface.

## Racine

| Clé | Défaut | Statut | Rôle |
|---|---:|---|---|
| `version` | `"1.0"` | interne | Version du format de configuration. |
| `site` | objet | UI | Identité générale. |
| `top_banner` | objet | UI | Bandeau institutionnel supérieur. |
| `banner` | objet | UI | Bannière éditoriale principale. |
| `paths` | objet | UI | Chemins du projet. |
| `content` | objet | UI | Lecture des sources. |
| `home` | objet | UI | Page d’accueil. |
| `blog` | objet | UI | Blog, archive et RSS. |
| `menus` | objet | UI/dialogue | Navigation. |
| `render` | objet | UI | Rendu HTML/TEI. |
| `media_handling` | objet | UI | Images et médias. |
| `notes_rendering` | objet | UI/masqué | Notes. |
| `footer` | objet | UI | Pied de page. |
| `build` | objet | UI/masqué | Génération et contrôles. |
| `search` | objet | UI | Recherche statique, exposée dans l’onglet Génération. |
| `ftp` | objet | dialogue | Publication FTP/FTPS. |

Le validateur exige actuellement les sections racine principales sauf `top_banner` et `ftp`, qui peuvent être absentes d’un ancien fichier et reprendre leurs valeurs par défaut.

## `site`

| Clé | Défaut | Statut | Rôle |
|---|---|---|---|
| `title` | `"MEROPE"` | UI | Titre du site. Obligatoire et non vide. |
| `subtitle` | `""` | UI | Sous-titre facultatif. |
| `base_url` | `""` | UI | URL publique HTTP(S), sans slash final de préférence ; nécessaire au RSS et au sitemap. |
| `language` | `"fr"` | UI | Langue du site ; obligatoire et non vide. |
| `author` | `""` | UI | Auteur par défaut des métadonnées. |
| `description` | `""` | UI | Description générale/SEO de repli. |
| `license_spdx_id` | `""` | UI | Identifiant SPDX d’une licence Creative Commons reconnue. |
| `license_name` | `""` | UI | Nom libre de licence si aucun SPDX reconnu n’est utilisé. |
| `license_url` | `""` | UI | URL associée au nom libre de licence. |

Les champs de licence alimentent le `teiHeader`. Ils ne provoquent pas actuellement l’ajout automatique d’une mention de licence dans le HTML.

## `top_banner`

| Clé | Défaut | Statut | Rôle |
|---|---:|---|---|
| `enabled` | `false` | UI | Active le bandeau institutionnel tout en haut du site. |
| `image` | `""` | UI | Chemin de l’image, copiée sans redimensionnement. |
| `alt` | `""` | UI | Texte alternatif. |
| `link` | `""` | UI | Cible facultative du clic. |

## `banner`

| Clé | Défaut | Statut | Rôle |
|---|---:|---|---|
| `enabled` | `false` | UI | Active la bannière principale. |
| `image` | `""` | UI | Chemin de l’image par rapport au projet. |
| `link` | `"/index.html"` | UI | Cible du clic. |
| `alt` | `""` | UI | Texte alternatif. |
| `show_title_overlay` | `false` | UI | Superpose titre et sous-titre à la bannière. |
| `height_px` | `220` | UI | Hauteur d’affichage, entier ≥ 1. |

## `paths`

`project_root` établit la racine logique et peut lui-même être absolu. Les autres chemins peuvent être relatifs à cette racine ou syntaxiquement absolus, mais le builder exige qu’ils se résolvent à l’intérieur de `project_root`. Un chemin absolu extérieur au projet est refusé : ces réglages ne permettent pas de lire ou d’écrire dans un dossier quelconque du disque.

Les huit chemins requis doivent être non vides et les différents rôles doivent être configurés vers des dossiers distincts. Le validateur détecte lexicalement les collisions après uniformisation des séparateurs et réduction des composants redondants `.` et `..`, sans consulter le disque. Il ne résout donc pas les liens symboliques ni les autres équivalences dépendant du système de fichiers.

| Clé | Défaut | Statut | Rôle |
|---|---|---|---|
| `project_root` | `"."` | UI | Racine logique du projet. |
| `content_dir` | `"content"` | UI | Dossier englobant les contenus. |
| `pages_dir` | `"content/pages"` | UI | Pages statiques. |
| `posts_dir` | `"content/posts"` | UI | Billets. |
| `assets_dir` | `"assets"` | UI | Assets copiés tels quels. |
| `theme_dir` | `"theme"` | UI | Thème graphique et ressources associées. |
| `templates_dir` | `"theme/templates"` | UI | Gabarits HTML. |
| `xslt_dir` | `"theme/xslt"` | UI | Feuilles XSLT. |
| `output_dir` | `"site"` | UI | Sortie du site généré. |
| `tei_dir` | `"build/tei"` | UI | TEI intermédiaire conservé lorsque l’option correspondante est active. |

Les huit chemins explicitement requis par validation sont `pages_dir`, `posts_dir`, `assets_dir`, `theme_dir`, `templates_dir`, `xslt_dir`, `output_dir` et `tei_dir`.

## `content`

| Clé | Défaut | Statut | Rôle |
|---|---|---|---|
| `source_format` | `"markdown"` | masqué, inerte | Champ historique conservé pour compatibilité ; sa valeur n’est pas lue par le pipeline et seul Markdown est pris en charge. |
| `markdown_origin` | `"google_docs_export"` | UI | Origine des Markdown, utilisée pour adapter le nettoyage. |
| `use_front_matter` | `true` | masqué, inerte | Conservé pour compatibilité ; sa valeur ne permet pas de désactiver le front matter, toujours exigé par le pipeline. |
| `default_page_layout` | `"page"` | UI | Valeur `layout` par défaut dans les métadonnées d’une page ; ne choisit pas le gabarit HTML. |
| `default_post_layout` | `"post"` | UI | Valeur `layout` par défaut dans les métadonnées d’un billet ; ne choisit pas le gabarit HTML. |
| `slugify_mode` | `"ascii"` | UI | Fabrication des slugs ; `ascii` translittère notamment les accents. |
| `copy_linked_assets` | `true` | UI | Copie les fichiers référencés depuis les contenus. |

## `home`

| Clé | Défaut | Statut | Rôle |
|---|---|---|---|
| `mode` | `"page"` | UI | `page` ou `recent_posts`. |
| `source` | `"content/pages/accueil.md"` | UI | Fichier Markdown de l’accueil en mode `page`. |
| `layout` | `"home"` | masqué, inerte | Ancien réglage conservé pour compatibilité ; il n’est pas lu par le builder. Le gabarit HTML réel est `render.home_template`. |
| `recent_posts_count` | `5` | UI | Nombre de billets en mode `recent_posts`, entier ≥ 0. |
| `recent_posts_excerpt_length` | `2000` | UI | Longueur approximative de l’extrait de chaque billet, entier ≥ 0. |

## `blog`

| Clé | Défaut | Statut | Rôle |
|---|---:|---|---|
| `enabled` | `true` | UI | Active le blog. |
| `posts_per_page` | `10` | UI | Nombre de billets par page d’archive, entier ≥ 0. |
| `generate_archive_page` | `true` | UI | Génère la page d’archive. |
| `archive_title` | `"Billets"` | UI | Titre de l’archive. |
| `archive_path` | `"billets"` | UI | Chemin de l’archive. Chaque segment doit être un slug sûr ; `..` et chemins absolus sont interdits. |
| `sort_descending_by_date` | `true` | UI | Tri du plus récent au plus ancien. |
| `generate_rss_feed` | `true` | UI | Génère `feed.xml` si le blog est actif et `site.base_url` renseigné. |

## `menus`

### `menus.top` : liste de `MenuLink`

| Clé | Défaut | Rôle |
|---|---:|---|
| `label` | requis | Texte du lien. |
| `target` | requis | Destination. |
| `target_type` | `"internal"` | `internal` ou `external`. |
| `enabled` | `true` | Affiche ou masque l’entrée. |
| `new_tab` | `false` | Ouvre dans un nouvel onglet ; les attributs de sécurité adaptés sont ajoutés au lien généré. |

Une cible `external` doit être une URL HTTP(S).

### `menus.side` : liste de sections

Une `SideMenuSection` contient :

| Clé | Défaut | Rôle |
|---|---:|---|
| `label` | requis | Titre de section. |
| `enabled` | `true` | Affiche ou masque la section. |
| `target` | `""` | Cible facultative du titre de section. |
| `target_type` | `"internal"` | `internal` ou `external`. |
| `numbered` | `false` | Active la numérotation I., II., III. et A., B., C. pour ses sous-sections. |
| `children` | `[]` | Liens directs de la section. |
| `subsections` | `[]` | Sous-sections. |

Une `SideMenuSubSection` contient `label`, `enabled`, `target`, `target_type` et `children`. Les `children` sont des `MenuLink`. Le modèle s’arrête à ces trois niveaux.

## `render`

| Clé | Défaut | Statut | Rôle |
|---|---:|---|---|
| `theme_name` | `"default"` | masqué, inerte | Nom historique conservé pour compatibilité ; il n’est pas lu par le rendu. Les chemins réels sont dans `paths`. |
| `html_template` | `"page.html"` | UI | Gabarit des pages. |
| `post_template` | `"post.html"` | UI | Gabarit des billets. |
| `home_template` | `"home.html"` | UI | Gabarit de l’accueil. |
| `tei_to_html_xslt` | `"tei_to_html.xsl"` | UI | Feuille XSLT TEI → HTML. |
| `pretty_print_html` | `true` | masqué, inerte | Conservé pour compatibilité ; il n’est actuellement pas lu par le pipeline et ne commande aucune indentation du HTML. |
| `generate_tei_files` | `true` | UI | Conserve les TEI intermédiaires dans `paths.tei_dir`. |
| `enable_lightbox` | `true` | UI | Active la visionneuse d’images. |
| `lightbox_engine` | `"fancybox"` | masqué, inerte | Nom de moteur historique conservé pour compatibilité ; sa valeur n’est pas lue et le moteur livré est fixe. |
| `validate_commons_publishing` | `true` | UI | Vérifie le TEI avec le profil Commons Publishing ; avertissement par défaut. |

## `media_handling`

| Clé | Défaut | Statut | Rôle |
|---|---:|---|---|
| `strategy` | `"copy_local_assets"` | masqué, inerte | Stratégie historique conservée pour compatibilité ; aucune branche du moteur ne lit actuellement sa valeur. |
| `images_dir` | `"assets/images"` | UI | Dossier où les éditeurs enregistrent les images insérées/collées. |
| `copy_media_to_output` | `true` | UI | Copie les médias dans la sortie. |
| `generate_clickable_figures` | `true` | UI | Rend les figures cliquables. |
| `fancybox_group_posts` | `true` | UI | Regroupe les figures d’un même article dans la lightbox. |
| `use_captions_as_fancybox_caption` | `true` | UI | Réutilise les légendes comme légendes de lightbox. |

## `notes_rendering`

Seul `enable_footnotes` reste visible dans l’interface. Les autres clés sont gardées pour compatibilité avec les projets existants.

| Clé | Défaut | Statut | Rôle actuel |
|---|---:|---|---|
| `mode` | `"margin_excerpt_plus_footnote"` | masqué, inerte | Ancien mode global conservé pour compatibilité ; il n’est pas lu par le rendu. |
| `enable_margin_notes` | `false` | masqué, neutralisé | La valeur est transmise au post-traitement, qui force actuellement les notes marginales à être désactivées quel que soit ce booléen. |
| `enable_footnotes` | `true` | UI | Conserve la liste complète des notes dans le HTML. |
| `margin_excerpt_words` | `8` | masqué, neutralisé | La valeur est transmise à la branche des notes marginales, actuellement désactivée ; elle n’a donc aucun effet sur la sortie. |
| `margin_excerpt_chars` | `80` | masqué, neutralisé | La valeur est transmise à la branche des notes marginales, actuellement désactivée ; elle n’a donc aucun effet sur la sortie. |
| `prefer_words_over_chars` | `true` | masqué, neutralisé | La valeur est transmise à la branche des notes marginales, actuellement désactivée ; elle n’a donc aucun effet sur la sortie. |
| `footnotes_location` | `"end_of_article"` | masqué, inerte | Emplacement historique conservé pour compatibilité ; il n’est pas lu par le rendu. |

Les notes restent dans le TEI même si leur liste complète est retirée du HTML.

## `footer`

| Clé | Défaut | Statut | Rôle |
|---|---:|---|---|
| `text` | `""` | UI | Texte libre du pied de page. |
| `show_generation_info` | `true` | UI | Affiche la mention « généré avec MÉROPE ». |
| `show_last_build_date` | `true` | UI | Affiche la valeur la plus récente parmi `updated` explicite, sinon le mtime du fichier source, sinon la date de publication. Ce n’est pas la date du build ; le mtime est un indicateur technique qui peut changer sans modification éditoriale. |

## `build`

| Clé | Défaut | Statut | Rôle |
|---|---:|---|---|
| `clean_output_dir` | `true` | UI | Vide la sortie avant génération. |
| `copy_assets` | `true` | UI | Copie le dossier d’assets dans la sortie. |
| `fail_on_missing_assets` | `false` | UI | Rend les assets manquants bloquants. |
| `fail_on_invalid_config` | `true` | masqué, inerte | Paramètre historique conservé pour compatibilité ; il n’est pas lu par le builder et l’interface comme la CLI valident toujours avant le build. |
| `pandoc_command` | `"pandoc"` | UI | Commande ou chemin de l’exécutable Pandoc. |
| `generate_sitemap` | `true` | UI | Génère `sitemap.xml` si `site.base_url` existe. |
| `generate_robots_txt` | `true` | UI | Génère `robots.txt`; la ligne Sitemap dépend de la Base URL et du sitemap. |
| `check_broken_links` | `true` | UI | Lance les contrôles post-build : liens/médias, pages orphelines, canoniques, JSON-LD, description et `<h1>`. |
| `fail_on_broken_links` | `false` | UI | Transforme les problèmes détectés par ces contrôles en échec du build. |
| `generate_redirects` | `true` | UI | Génère des redirections lors d’un changement de slug. |
| `fail_on_invalid_commons_publishing` | `false` | UI | Rend bloquante la validation Commons Publishing si `render.validate_commons_publishing` est active. |

## `search`

Ces réglages sont affichés dans l’onglet **Génération**.

| Clé | Défaut | Statut | Rôle |
|---|---:|---|---|
| `enabled` | `true` | UI | Génère l’index et affiche la recherche côté navigateur. |
| `excerpt_length` | `160` | UI | Longueur des extraits de résultats, entier ≥ 0. |

La recherche est une recherche statique par sous-chaîne, insensible à la casse et aux accents, exécutée dans le navigateur.

## `ftp`

Ces champs sont édités dans **Publier (FTP)...**.

| Clé | Défaut | Statut | Rôle |
|---|---:|---|---|
| `host` | `""` | dialogue | Hôte FTP/FTPS. |
| `port` | `21` | dialogue | Port, entier de 1 à 65535. |
| `username` | `""` | dialogue | Identifiant. |
| `password` | `""` | dialogue | Mot de passe en mémoire ; voir ci-dessous. |
| `remote_dir` | `"/"` | dialogue | Dossier distant. |
| `use_tls` | `true` | dialogue | Utilise FTPS. |
| `passive_mode` | `true` | dialogue | Utilise le mode passif. |
| `site_url` | `""` | dialogue | URL HTTP(S) publique proposée à l’ouverture après publication. |

MÉROPE tente de stocker `password` dans le gestionnaire d’identifiants du système. Si cette opération réussit, le mot de passe est retiré du JSON sauvegardé. Si elle échoue, il peut rester en clair dans `site.json` afin d’éviter sa perte ; le code de sauvegarde émet alors un avertissement. Un fichier de configuration ayant subi ce repli doit donc être considéré comme sensible.

## Validation du JSON

Le validateur impose notamment :

- `version`, `site.title` et `site.language` non vides ;
- `site.base_url` et `ftp.site_url`, lorsqu’ils sont renseignés, en HTTP(S) ;
- les huit chemins requis de `paths` non vides, avec détection lexicale des collisions après normalisation des séparateurs et des composants `.` et `..` ; les rôles doivent viser des dossiers réellement distincts, y compris lorsque des équivalences dépendant du système de fichiers ne peuvent pas être détectées ;
- `home.mode` égal à `page` ou `recent_posts` ;
- les booléens réellement booléens et les champs numériques dans leurs bornes ;
- `blog.archive_path` composé de segments de slug sûrs ;
- les liens de menu complets et les cibles externes en HTTP(S) ;
- trois niveaux maximum dans le menu latéral.

## Exemple de squelette

```json
{
  "version": "1.0",
  "site": {
    "title": "Carnet de recherche",
    "language": "fr",
    "base_url": "https://exemple.org"
  },
  "banner": {
    "enabled": false
  },
  "paths": {
    "pages_dir": "content/pages",
    "posts_dir": "content/posts",
    "assets_dir": "assets",
    "theme_dir": "theme",
    "templates_dir": "theme/templates",
    "xslt_dir": "theme/xslt",
    "output_dir": "site",
    "tei_dir": "build/tei"
  }
}
```

Pour créer un vrai projet, il vaut mieux laisser **Nouveau projet...** produire un `site.json` complet plutôt que partir de ce squelette minimal.
