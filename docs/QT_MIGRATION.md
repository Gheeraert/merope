# Migration de l’éditeur de contenu vers Qt

## Statut actuel

MÉROPE propose deux éditeurs de contenu WYSIWYG pour les pages et billets, lisant et écrivant le même modèle et les mêmes fichiers Markdown :

- **l’éditeur Tkinter** (`ui/content_editor/`) — éditeur historique, officiel, lancé dans le processus principal ;
- **l’éditeur Qt** (`ui/qt_editor/`) — prototype expérimental, lancé dans un processus séparé, qualifié comme tel dans l’interface elle-même (bouton « Éditeur Qt (expérimental)... », tooltip explicite).

Tkinter reste l’éditeur principal et le repli (fallback) officiel. La parité fonctionnelle *automatisée* (couverture de tests) entre les deux éditeurs est atteinte sur le gros œuvre et les outils quotidiens ; l’étape suivante est une recette humaine, notamment sur le collage Word/Google Docs, suivie d’un inventaire des écarts réellement observés. **Aucune bascule de l’éditeur principal vers Qt n’est planifiée à ce stade.**

Pour choisir entre les deux éditeurs au quotidien, voir `docs/GUIDE_UI.md`.

## Architecture

```text
Markdown
   ↕
Block / InlineRun
   ↕
adaptateur GUI
   ├── adaptateur Tkinter
   └── adaptateur Qt
```

`Block` et `InlineRun` restent le pivot canonique de l’éditeur, partagé par les deux toolkits. Qt n’est ni un parseur ni un sérialiseur Markdown pour MÉROPE : les fonctions natives `toMarkdown`/`setMarkdown`/`toHtml`/`setHtml` de Qt ne font pas partie du chemin de données. Le pipeline de publication reste inchangé et n’utilise ni l’un ni l’autre éditeur : Markdown → Pandoc → TEI Commons Publishing → XSLT → HTML.

Le round-trip Qt est exclusivement :

```text
Markdown → rich_text_import → Block / InlineRun → QTextDocument
QTextDocument → Block / InlineRun → rich_text_export → Markdown
```

## Parité fonctionnelle

Fonctionnalités couvertes par l’adaptateur Qt, avec tests automatisés :

- paragraphes, titres H1–H4, citations, listes à puces/numérotées simples, alignements ;
- formats inline : gras, italique, souligné (persisté en `[texte]{.underline}` Pandoc), barré, exposant, liens, y compris combinés ;
- préservation exacte des espaces insécables U+00A0 ;
- tableaux simples comme `QTextTable` graphique éditable ; tableaux non éligibles et blocs `VERBATIM` conservés en source brute monospacée, sans perte ;
- images statiques (`QTextImageFormat`), insertion, remplacement, recadrage, redimensionnement, réglages luminosité/contraste, légendes tapées sous l’image ;
- notes de bas de page structurées, avec panneau dédié, renumérotation canonique à la sauvegarde ;
- raccourci `((note))` conservé comme texte éditable, converti en note Pandoc uniquement à la normalisation d’aperçu/génération ;
- typographie française à la frappe et sur sélection (guillemets, espaces insécables, ligatures, ordinaux de siècles) via le module pur partagé `markdown/typography.py` ;
- collage riche Word/Google Docs (HTML, image native, fichiers locaux) via le même importeur partagé que Tkinter ;
- recherche/remplacement, collage en texte brut, insertion manuelle de U+00A0, zoom visuel, correcteur orthographique visuel (soulignement) avec suggestions de correction dans le menu contextuel du mot souligné ;
- workflow projet complet : navigateur de contenus, création, import, métadonnées, conversion page ↔ billet, suppression.

Ce qui reste **explicitement refusé** par l’adaptateur Qt (erreur avant toute mutation du document, fichier ni réécrit ni archivé) :

- titres hors H1–H4, listes complexes, listes vides ou imbriquées, éléments de liste contenant des blocs ;
- alignement d’une sélection mêlant paragraphes et éléments de liste ;
- tout objet Qt étranger (cadre, `QTextTable`) que l’adaptateur ne sait pas retranscrire ;
- collage HTML `<table>` et `<pre>` (distinct du support natif d’un bloc TABLE/VERBATIM déjà présent dans le document).

## Fonctions spécifiques Qt

- **Aperçu HTML ponctuel** à la demande (pas de live preview), décrit en détail plus bas.
- **Audit presse-papiers** (`python -m bloggen.ui.qt_editor.clipboard_probe`) : outil diagnostique autonome qui inspecte les formats MIME du presse-papiers (tailles, SHA-256, aperçus tronqués) sans jamais importer de contenu ni télécharger une ressource ; sert à préparer la recette humaine Word/Google Docs.
- **Correcteur orthographique visuel** : soulignement des mots inconnus (français, hors ligne) sans toucher au modèle canonique.
- **Recadrage et ajustement d’image** dans un dialogue dédié, avec dérivés (`-cropN`, `-adjustN`) écrits à côté de l’original, jamais en écrasement.

## IPC Tk ↔ Qt

```text
processus principal = Tkinter
processus enfant    = PySide6, lancé par ui/qt_editor_launcher.py
transport           = subprocess + JSON Lines sur stdout/stdin
document            = lu et écrit directement par Qt
Block / InlineRun   = jamais sérialisé sur l’IPC
```

Le processus Tk lance le même interpréteur Python (`sys.executable -m bloggen.ui.qt_editor --ipc ...`). Aucun pickle, aucun `eval` : le protocole est strictement du JSON Lines versionné (`qt_editor_protocol.py`), avec les événements `ready`, `opened`, `saved`, `open_refused`, `error`, `closed`, et `config_requested`. Le démarrage a un délai maximal de 10 secondes ; un enfant qui n’émet jamais `ready` est terminé et le fallback Tkinter est proposé. Fermer MÉROPE ne tue jamais le processus Qt.

**Configuration vivante pour l’aperçu Qt** : Tk reste seul propriétaire du `ProjectConfig` vivant (y compris les champs de formulaire non enregistrés) ; Qt reste seul propriétaire du document éditorial. À chaque `config_requested(request_id)`, Tk construit un instantané à la demande (aucun cache poussé périodiquement, aucun rechargement de `site.json`). La section `ftp` est systématiquement retirée de cet instantané avant transmission — il ne passe jamais par le credential store ni par la sérialisation disque.

## Sauvegarde et recovery

- **Sauvegarde** : `extract_blocks` → `blocks_to_markdown` → `write_content_file`, avec archivage préalable dans `.versions` par le service partagé avec Tkinter.
- **Autosauvegarde de sécurité** : `QTimer` de 30 secondes, actif seulement si le document est modifié (corps, notes, métadonnées ou session importée). Écrit `.merope-recovery/draft.json` au même format que Tkinter. **Autosave ≠ save** : ce chemin n’appelle jamais `write_content_file` ni le service de versionnement.
- **Dette connue** : `.merope-recovery/draft.json` est un fichier **partagé** entre Tk et Qt, sans verrou par éditeur (le code Tk documente lui-même l’intention : « Offer one shared Tk/Qt draft »). Si les deux éditeurs sont ouverts simultanément sur le même projet et que l’un des deux plante, le brouillon proposé au redémarrage peut être celui de l’autre éditeur. Écriture atomique, donc aucune corruption possible — seulement un mauvais candidat de restauration dans ce scénario rare.

## Aperçu

```text
clic « Aperçu HTML »
  → snapshot canonique QTextDocument + FootnoteStore
  → config_requested → ProjectConfig vivant fourni par Tk
  → Markdown temporaire voisin du fichier source
  → scratch neuf (tempfile.mkdtemp)
  → normalisation + Pandoc + TEI + XSLT (vrai pipeline de publication)
  → index.html
  → python -m bloggen.ui.preview_process (pywebview, sous-processus séparé)
```

Strictement une lecture : **preview ≠ save**, **preview ≠ renumber**, **preview ≠ lecture de `site.json`**. Un nouveau build doit réussir entièrement et son processus d’affichage atteindre l’état prêt avant que l’ancien aperçu soit remplacé ; un échec conserve l’ancien aperçu. Chaque clic crée un nouveau scratch isolé, supprimé à la fermeture ; rien n’est repris du vrai dossier `site/`.

## Points encore non migrés / limites

Volontairement différés (aucun de ces points ne bloque l’usage courant) :

- édition riche des légendes au-delà du texte simple ; suppression physique des assets lors d’un undo ;
- conversion interactive automatique des `((note))` en notes structurées ;
- tableaux Markdown complexes hors du sous-ensemble graphique (sélection rectangulaire, fusion de cellules, largeurs persistantes entre sessions, import HTML Word/Excel) ;
- aperçu live automatique et « Enregistrer sous... » général côté Qt ;
- toute commande IPC au-delà des réponses de configuration.

Restent également propres à l’ancien adaptateur Tkinter (non partagés) : construction du widget `Text`, tags et marques, undo compensatoire, bindings spécifiques.

Prochaines étapes identifiées : recette humaine ciblée (notamment Word/Google Docs via le clipboard probe), vérification manuelle des formats MIME réellement exposés par Word/Google Docs sous Windows, épreuve du redimensionnement sous différents facteurs d’échelle d’écran, épreuve du lancement/timeout sur les plateformes distribuées.

## Décisions d’architecture importantes

- **JSON Lines plutôt que pickle/eval** pour l’IPC : protocole texte inspectable, pas d’exécution de code arbitraire reçu d’un sous-processus.
- **Aucun import PySide6 côté Tkinter** : Qt est lancé en sous-processus, jamais chargé dans le processus principal — un crash ou une dépendance manquante côté Qt n’affecte pas Tk.
- **`Block`/`InlineRun` comme unique pivot**, jamais sérialisé sur l’IPC : le document Qt n’est connu que de Qt ; seuls des événements et une configuration de rendu transitent.
- **Fermer MÉROPE ne tue jamais le processus Qt** : l’éditeur Qt possède son propre `closeEvent`, sa propre confirmation de modifications non enregistrées et son propre autosave/recovery — un arrêt forcé risquerait une perte de données sans bénéfice net (voir `AUDIT.md`).
- **Recovery partagé Tk/Qt** : choix assumé de réutiliser le même fichier plutôt que d’introduire un mécanisme de verrouillage complémentaire, la dette résiduelle (mauvais brouillon proposé) étant jugée mineure face à la complexité d’un verrou inter-processus.
- **Aperçu Qt isolé dans un scratch dédié** : jamais de réutilisation du dossier de sortie réel, pour qu’un aperçu ne puisse jamais corrompre un build ou un aperçu précédent.

## Historique synthétique

La migration a procédé par phases incrémentales : extraction des services sans GUI (images, versionnement, notes) réutilisables par les deux éditeurs ; prototype autonome Qt ouvrant/enregistrant un sous-ensemble documentaire validé ; adaptateur `Block`/`InlineRun ↔ QTextDocument` pour la structure de base puis pour les formats inline ; typographie française partagée ; images statiques puis outils d’édition d’image (recadrage, ajustement, redimensionnement à la souris) ; notes de bas de page structurées avec panneau dédié ; tableaux graphiques avec fallback source brute pour les cas non représentables ; outils quotidiens (recherche/remplacement, presse-papiers, zoom) ; lancement en sous-processus avec protocole IPC JSON Lines et configuration vivante à la demande ; aperçu HTML ponctuel via le vrai pipeline de publication ; audit presse-papiers diagnostique en préparation de la recette Word/Google Docs ; correcteur orthographique visuel.

Chaque lot a été accompagné d’une couverture de tests automatisés visant la parité avec l’adaptateur Tkinter existant. L’état résultant de cette histoire est résumé dans les sections « Statut actuel » et « Parité fonctionnelle » ci-dessus, qui font foi sur l’état présent du code.
