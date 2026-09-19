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

### Compatibilité ascendante et clés inconnues (contrat lossless)

Une version de MÉROPE peut ignorer *fonctionnellement* une clé JSON qu’elle ne connaît pas — elle ne l’interprète pas, ne l’affiche pas dans l’interface — mais elle **la préserve** lors d’un cycle chargement → modification → sauvegarde. Aucune clé encore présente dans un `site.json` n’est supprimée silencieusement au seul motif que la version courante ne la reconnaît pas.

Le mécanisme repose sur un champ `unknown_data` porté par chaque dataclass de section du modèle Python (`config/models.py`). Ce n’est pas une clé du format JSON disque : c’est un détail d’implémentation qui capture, à la construction du modèle, toute clé d’un objet JSON qui ne correspond à aucun champ connu de cette section.

Comportement précis :

- **Racine** : une section ou clé inconnue au niveau racine de `site.json` est conservée par le modèle (`ProjectConfig.unknown_data`).
- **Section connue** : une clé inconnue à l’intérieur d’une section reconnue (`site`, `render`, etc.) est conservée à ce niveau, associée au modèle de cette section.
- **Structures opaques** : les valeurs inconnues gardent leur type JSON d’origine (objet, liste, nombre, booléen, chaîne) — elles ne sont ni aplaties ni converties.
- **Objets de menu** : chaque entrée de menu (`MenuLink`, `SideMenuSection`, `SideMenuSubSection`) porte ses propres données inconnues, attachées à cet objet précis et non à sa position dans la liste.
  - **Réordonner** un menu déplace les données inconnues avec l’objet auquel elles appartiennent.
  - **Supprimer** une entrée supprime ses données inconnues avec elle ; les entrées voisines ne sont jamais affectées.
  - **Modifier** une entrée conserve ses données inconnues associées.
- **`Enregistrer sous...`** préserve les données inconnues du projet en cours.
- **`Nouveau`** ne réutilise jamais les données inconnues d’un projet précédemment ouvert : chaque chargement construit un modèle indépendant à partir de son propre JSON, sans état partagé entre projets.
- **Ouvrir un projet A, puis un projet B** ne mélange jamais leurs données inconnues respectives, pour la même raison.
- **Priorité aux champs connus** : si un champ devient reconnu dans une future version de MÉROPE alors qu’une valeur opaque du même nom existait déjà, le champ nouvellement connu prend priorité à la sauvegarde. Une valeur opaque ne peut jamais masquer ou entrer en conflit avec un champ que le modèle sait désormais interpréter.

Ce contrat ne s’applique pas à `ftp.password`, qui fait l’objet d’une exception de sécurité décrite plus bas.

Le champ `version`, bien qu’il ne soit pas éditable dans l’interface, est préservé lors d’un aller-retour d’une configuration acceptée.

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

Le champ `password` fait exception au contrat lossless décrit plus haut :

> Le contrat lossless ne s’applique jamais à la persistance en clair d’un secret.

`ftp.password` est un champ déclaré du modèle (jamais capturé par `unknown_data`, y compris s’il apparaissait déjà sous une forme inattendue). Avant toute sauvegarde de `site.json`, MÉROPE retire systématiquement ce champ du JSON écrit sur disque — que la tentative de stockage dans le gestionnaire d’identifiants du système ait réussi ou non. Le mot de passe n’est donc **jamais** écrit en clair dans `site.json` par le code de sauvegarde courant :

- si le stockage sécurisé (`keyring`) réussit, le mot de passe est retrouvé automatiquement à la prochaine ouverture ;
- s’il échoue, le mot de passe reste utilisable en mémoire pour la session courante, avec un avertissement, mais devra être ressaisi à la prochaine ouverture, puisqu’il n’a été conservé nulle part sur disque.

Un fichier `site.json` legacy contenant encore un mot de passe en clair peut être lu ; MÉROPE tente alors immédiatement de le migrer vers le trousseau du système. La sauvegarde suivante retire ce mot de passe du JSON, dans tous les cas.

## Chargement et sauvegarde

### Chargement

- Le JSON est parsé puis validé (voir « Invariants de validation »).
- Les sections optionnelles historiques (`top_banner`, `ftp`) absentes reprennent leurs valeurs par défaut.
- Les clés inconnues, à tous les niveaux concernés, sont conservées dans `unknown_data` plutôt qu’ignorées (voir « Compatibilité ascendante » ci-dessus).

### Sauvegarde

- Le modèle est sérialisé de façon canonique : l’ordre et la forme exacte d’un JSON écrit à la main ne sont pas garantis à l’identique, mais son contenu sémantique l’est (valeurs connues + valeurs opaques préservées).
- Les champs connus sont toujours prioritaires sur une valeur opaque homonyme (voir plus haut).
- `ftp.password` est retiré avant écriture, sans exception (voir « Publication FTP/FTPS et mot de passe »).
- L’écriture sur disque passe par `atomic_write_text` (`content/atomic_write.py`) : un fichier temporaire est créé à côté du fichier cible (même volume), le contenu y est écrit puis synchronisé sur le disque (`flush` + `fsync`), et le remplacement final du fichier cible se fait par une opération atomique du système d’exploitation (`os.replace`). L’ancien `site.json` reste intact tant que le nouveau n’est pas complètement écrit et synchronisé ; un échec avant cette dernière étape ne produit donc pas de fichier tronqué.

## Exemple complet

La manière la plus fiable d’obtenir un fichier complet et à jour est de créer un projet depuis l’interface avec **Nouveau projet...**, puis d’examiner `config/site.json`. L’exemple minimal du dépôt reste utile pour les tests et démonstrations : `examples/minimal_project/config/site.json`.
