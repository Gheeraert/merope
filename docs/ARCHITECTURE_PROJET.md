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

Tous les modules listés ci-dessous vivent sous `src/bloggen/` (par exemple `src/bloggen/config/`, `src/bloggen/ui/qt_editor/`).

## Flux de publication

```text
site.json
+ Markdown
+ thème
     ↓
validation de la configuration
     ↓
normalisation Markdown
     ↓
Pandoc
     ↓
XML-TEI
     ↓
post-traitement TEI (sécurisé)
     ↓
validation (TEI Commons Publishing, liens/médias, etc.)
     ↓
XSLT
     ↓
HTML
     ↓
assemblage transactionnel du site
```

L’assemblage final est transactionnel : le site est construit dans un dossier de préparation (« staging »), puis ce dossier remplace l’ancien site de sortie par une opération atomique avec repli automatique en cas d’échec (`_replace_directory` / `_restore_backup` dans `build/site_builder.py`). Le TEI intermédiaire suit le même remplacement que le site, comme une seule unité.

## Flux d’édition

```text
Markdown
  ↕
Block / InlineRun
  ↕
adaptateur Tkinter ou adaptateur Qt
```

Les deux éditeurs de contenu (Tkinter historique, Qt expérimental) partagent le même modèle `Block`/`InlineRun`, les mêmes importeurs/exporteurs et les mêmes services métier ; ils ne dupliquent que l’adaptateur vers leur toolkit graphique respectif. Ce chemin d’édition n’intervient jamais dans le pipeline de publication ci-dessus, qui reste exclusivement basé sur Pandoc.

## Frontières de sécurité

- **`link_safety`** (`markdown/link_safety.py`) : allowlist stricte de schémas de liens (`http`, `https`, `mailto`, `tel`) ; toute autre destination est retirée du lien publié, texte visible conservé.
- **`xml_safety`** (`tei/xml_safety.py`) : parseur XML durci pour le TEI (aucun accès réseau, aucune DTD chargée, tout `DOCTYPE` rejeté explicitement), en cohérence avec le durcissement déjà appliqué dans `render/xslt_runner.py` et `tei/commons_publishing.py`.
- **Timeout des sous-processus** (`utils/subprocesses.py`) : tout appel externe (Pandoc notamment) est borné par un délai par défaut de 120 secondes, converti en échec de build propre plutôt qu’en blocage indéfini.
- **`atomic_write`** (`content/atomic_write.py`) : écriture par fichier temporaire voisin + `flush`/`fsync` + remplacement atomique (`os.replace`), utilisée pour la configuration comme pour les contenus.
- **Confinement des chemins** : chaque chemin configuré dans `paths` est résolu puis vérifié comme restant à l’intérieur de `project_root` ; un chemin qui en sortirait est refusé par le builder, indépendamment de la détection lexicale de collisions faite par le validateur.
- **Gestionnaire d’identifiants FTP** (`publish/ftp_credentials.py`) : le mot de passe FTP est stocké via `keyring` (trousseau du système) et n’est jamais écrit en clair dans `site.json` par le code de sauvegarde courant.

## Sauvegarde et fidélité des données

- **Versioning** (`content/versioning.py`) : archivage horodaté dans `.versions` avant écrasement d’un contenu déjà enregistré ; purge uniquement après confirmation utilisateur.
- **`VERBATIM`** : toute construction Markdown que l’éditeur ne reconnaît pas avec confiance est conservée telle quelle plutôt que devinée ou perdue (détail dans `docs/CONTRATS_DONNEES.md`).
- **Configuration lossless** : les clés JSON inconnues d’une version de MÉROPE sont préservées lors d’un cycle chargement → modification → sauvegarde (détail dans `docs/SPEC_JSON_CONFIG_V1.md`).

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
- deux éditeurs de contenu WYSIWYG (pages/billets) au-dessus du même modèle :
  Tkinter historique dans `ui/content_editor/` et Qt expérimental dans
  `ui/qt_editor/`, lancé en processus séparé par `ui/qt_editor_launcher.py`
- aperçu HTML optionnel des éditeurs (`ui/content_editor/preview.py`,
  `ui/qt_editor/preview.py` + `ui/preview_process.py`,
  fenêtre `pywebview` lancée en sous-processus séparé — pywebview exige que sa propre boucle
  d'événements tourne sur le vrai thread principal de son processus, séparément
  des boucles Tkinter et Qt)
- publication FTP (`ui/ftp_publish_dialog.py`), au-dessus de `publish/` ci-dessous

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
- écriture des pages (site + copie TEI, remplacés ensemble en fin de build — voir
  `_replace_directory`/`_restore_backup` dans `site_builder.py`)
- rapports
- prévisualisation locale du site généré

### `publish/`
- publication FTP/FTPS (`ftp_publisher.py`), manifeste des fichiers déployés par MEROPE pour
  détecter les fichiers distants devenus obsolètes
- mot de passe FTP dans le trousseau du système, jamais dans `site.json`
  (`ftp_credentials.py`, dépendance optionnelle `keyring`)

### `resources/`
- schéma TEI Commons Publishing embarqué (RelaxNG + règles Schematron), copié depuis le projet
  compagnon Mini-Métopes — voir `tei/commons_publishing.py` et `resources/schemas/commons-publishing/PROVENANCE.json`

### `utils/`
- utilitaires transverses (ex. appel à des sous-processus externes)

## Règles d’architecture
- pas de logique métier dans l’UI
- pas de parseur Markdown maison
- Pandoc reste la brique de conversion
- HTML final produit à partir de la TEI

### Exception bornée : éditeur de contenu WYSIWYG

Les deux éditeurs de contenu — Tkinter historique (`ui/content_editor/`) et Qt
expérimental (`ui/qt_editor/`) — permettent de rouvrir en saisie visuelle un
fichier produit par Mérope. Ils partagent le modèle `Block` / `InlineRun`, les
importeurs/exporteurs et les services métier ; chaque toolkit ne fournit qu’un
adaptateur de document et ses interactions propres. Cela suppose un import
Markdown limité (`markdown/rich_text_import.py`), ce qui touche en apparence à la
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
borné (`html.parser.HTMLParser`) vers le même modèle de blocs. Il reconnaît un
sous-ensemble pratique (paragraphes, titres, gras/italique/barré, liens,
listes à un niveau, citations, images). L’adaptateur Tkinter conserve son
fallback historique tolérant ; l’adaptateur Qt refuse atomiquement un collage
dont une structure ou une image annoncée ne peut pas être préservée. Aucun des
deux chemins ne touche au pipeline Pandoc.
