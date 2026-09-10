# Migration de l’éditeur de contenu vers Qt

## Architecture cible

```text
Markdown
   ↕
Block / InlineRun
   ↕
adaptateur GUI
   ├── adaptateur Tkinter
   └── adaptateur Qt
```

`Block` et `InlineRun` restent le pivot canonique de l’éditeur. Qt n’est ni
un parseur ni un sérialiseur Markdown pour Mérope. Le pipeline de publication
reste inchangé : Markdown → Pandoc → TEI Commons Publishing → XSLT → HTML.

## Isolation des processus

```text
processus principal = Tkinter
processus enfant    = PySide6
transport           = subprocess + JSON Lines sur stdout
document            = lu et écrit directement par Qt
Block / InlineRun   = jamais sérialisé sur IPC
```

Le processus Tk lance exactement le même interpréteur Python avec une commande
de la forme :

```text
sys.executable -m bloggen.ui.qt_editor --ipc
  --project-root ... --pages-dir ... --posts-dir ...
  --images-dir ... --slugify-mode ...
```

Le launcher n’importe que la bibliothèque standard et le module de protocole.
Il lit stdout et stderr dans des threads daemon, place les résultats dans une
file, puis `MainWindow` les traite sur le thread Tk avec `after()`. Fermer
Mérope ne tue jamais le processus Qt.

Le démarrage possède un délai maximal centralisé de 10 secondes, mesuré avec
`time.monotonic()`. Le polling `after()` contrôle ce délai sans bloquer Tk. Si
un enfant vivant n’émet jamais `ready`, le launcher le termine (il ne possède
encore aucun document éditable), libère l’instance expérimentale et propose le
fallback Tkinter.

En mode IPC, stdout est réservé à une ligne JSON UTF-8 par événement, flushée
immédiatement. Le protocole version 1 autorise seulement `ready`, `opened`,
`saved`, `open_refused`, `error` et `closed`, avec `path` ou `message` lorsque
le type l’exige. stderr reste réservé aux diagnostics humains.

Le protocole est volontairement unidirectionnel : Qt publie son état vers Tk,
mais Tk ne lui envoie aucune commande après le lancement.

## Fonctionne maintenant

- les services sans GUI extraits lors de la première phase : images,
  versionnement et sémantique des notes ;
- un prototype autonome lancé par `python -m bloggen.ui.qt_editor`, avec un
  chemin Markdown facultatif en argument, ouverture et enregistrement du
  sous-ensemble documentaire validé ;
- `MeropeTextEdit`, sous-classe de `QTextEdit` dédiée aux interactions de
  Mérope, sans devenir un modèle documentaire ni remplacer l’adaptateur
  `Block` / `InlineRun ↔ QTextDocument` ;
- l’adaptateur explicite `Block`/`InlineRun ↔ QTextDocument` pour les
  paragraphes, titres H1 à H4, citations, listes simples à puces ou numérotées
  et alignements ;
- les formats inline gras, italique, barré, exposant et lien, y compris leurs
  combinaisons ;
- la préservation exacte des espaces insécables U+00A0 par parcours des
  `QTextBlock` et `QTextFragment`, sans `QTextDocument.toPlainText()` ;
- les listes, ancres, alignements, curseurs et piles undo/redo natifs de Qt ;
- le contrat vide exact `[] ↔ QTextDocument` et l’export Markdown vide `""` ;
- les changements de type paragraphe/titre/citation/liste avec nettoyage des
  propriétés et styles devenus incompatibles ;
- les commandes inline déterministes sur sélection mixte : retrait si toute
  la sélection porte le format, application dans tous les autres cas ;
- l’ouverture sûre d’un fichier Mérope, avec validation complète avant que le
  document courant et son chemin puissent être remplacés ;
- l’enregistrement par `extract_blocks`, `blocks_to_markdown`, puis
  `write_content_file`, avec conservation des métadonnées et archivage
  préalable dans `.versions` par le service partagé avec Tkinter ;
- l’état modifié natif `QTextDocument.isModified()` et les choix Enregistrer,
  Ne pas enregistrer ou Annuler avant ouverture et fermeture ;
- le lancement expérimental depuis la fenêtre principale dans un processus
  séparé, sans aucun import PySide6 côté Tkinter ;
- une seule instance Qt expérimentale à la fois, avec détection des erreurs
  avant `ready`, des crashs et de la fermeture, puis possibilité de relance ;
- la conservation du bouton « Éditeur de contenu... » pour l’éditeur Tkinter
  historique et un bouton distinct « Éditeur Qt (expérimental)... » ;
- des propriétés Mérope centralisées fondées sur `QTextFormat.UserProperty`
  pour lever les ambiguïtés sémantiques ;
- une erreur explicite avant toute modification du document pour les blocs ou
  feuilles inline que ce prototype ne sait pas conserver.

### Typographie française dans `MeropeTextEdit`

Les règles restent définies dans le module pur `markdown/typography.py`. Les
adaptateurs Tk et Qt réutilisent les mêmes constantes, expressions régulières
et transformations pour les guillemets, la ponctuation, les numéros de page,
les espaces avant le point, les ligatures `œ` et les ordinaux de siècles.

À la frappe, Qt prend maintenant en charge :

- les guillemets droits convertis en `«` / `»` et leurs espaces insécables
  intérieures U+00A0, ainsi que la normalisation des guillemets français saisis
  directement ;
- un U+00A0 unique avant `; : ! ?`, qu’une espace ordinaire ait été saisie ou non ;
- `p. 12` et `pp. 123` avec U+00A0, et la suppression des espaces avant `.` ;
- les ligatures des mots reconnus par la règle commune (`oeuvre`, `soeur`, etc.) ;
- les suffixes d’ordinaux de siècles comme un vrai format Mérope
  `superscript=True`, jamais comme un caractère Unicode de remplacement.

Le choix ouvrant/fermant d’un guillemet est calculé depuis le contenu situé
avant le curseur. Il reste donc cohérent après un déplacement, un undo ou un
redo, sans état de parité global susceptible de se désynchroniser. Une frappe
de `"` sur une sélection l’entoure d’une paire de guillemets français sans
aplatir ses formats.

La commande « Typographie » travaille sur toute la sélection, y compris quand
une paire de guillemets traverse plusieurs fragments formatés. Elle calcule le
texte avec les fonctions pures, puis applique seulement les différences, de
droite à gauche, en conservant les formats Qt des caractères inchangés.

Les frappes nécessitant une correction sont insérées dans un bloc d’édition Qt
explicite ; les changements typographiques sont rattachés avec
`QTextCursor.joinPreviousEditBlock()`. La commande sur sélection utilise un
seul `beginEditBlock()` / `endEditBlock()`. L’undo/redo reste exclusivement
celui de Qt.

### Collage riche Word / Google Docs

Le chemin Qt est désormais explicite et ne délègue jamais l’interprétation du
HTML à `QTextEdit` :

```text
QMimeData
  → HTML
  → html_to_blocks
  → Block / InlineRun
  → insert_blocks
  → QTextDocument
```

`MeropeTextEdit.canInsertFromMimeData()` accepte un HTML non vide ou un texte
brut non vide et refuse les formats MIME seuls qu’il ne sait pas interpréter.
Le vrai chemin `QApplication.clipboard() → QTextEdit.paste()` aboutit ainsi à
`MeropeTextEdit.insertFromMimeData()`, qui préfère le HTML disponible dans le
MIME Qt natif. `acceptRichText` reste désactivé : Qt n’interprète jamais ce
HTML lui-même. Le parseur partagé conserve ses traitements Word, Google Docs,
styles inline, liens, listes, citations et typographie française. Aucune
réintroduction du contournement Win32 propre à Tk n’a été nécessaire à ce
stade.

La primitive `insert_blocks(cursor, blocks)` valide d’abord tout le modèle. Un
paragraphe unique s’insère inline au milieu du bloc courant. Pour plusieurs
blocs ou une structure comme un titre, une citation ou une liste, le préfixe
et le suffixe autour du curseur restent dans leurs propres blocs et conservent
leur sémantique ; les blocs collés sont insérés entre eux. Une sélection est
supprimée seulement après validation complète.

Le collage complet utilise un seul bloc d’édition natif Qt : undo restaure la
sélection, les formats et les structures antérieures, et redo réapplique tout
le collage.

Le texte brut est inséré littéralement, sans normalisation typographique
globale immédiate, comme le fallback historique Tk. La typographie à la frappe
et la commande explicite sur sélection restent disponibles ensuite.

Les balises `<img>`, `<table>`, `<pre>` ainsi que les images VML Word
`<v:imagedata>` et leur conteneur `<v:shape>` refusent intégralement le collage
riche, même si le MIME fournit aussi un texte alternatif. La fenêtre explique
que rien n’a été inséré afin d’éviter une perte de données. L’option stricte
`reject_tags` a été ajoutée au parseur HTML canonique ; sa valeur par défaut
reste vide, donc le comportement de l’éditeur Tk n’est pas modifié.

Le round-trip expérimenté est exclusivement :

```text
Markdown → rich_text_import → Block / InlineRun
         → QTextDocument
         → Block / InlineRun → rich_text_export → Markdown
```

Les fonctions Qt `toMarkdown`, `setMarkdown`, `toHtml` et `setHtml` ne font
pas partie de ce chemin.

## Explicitement refusé

- l’ouverture éditable et l’enregistrement de fichiers contenant images,
  notes, tableaux, blocs `verbatim`, titres hors H1–H4 ou listes complexes ;
- les listes vides ou imbriquées et les éléments de liste contenant des blocs ;
- l’alignement d’une sélection mêlant paragraphes et éléments de liste ;
- tout objet, cadre ou tableau Qt que l’adaptateur ne sait pas retranscrire.

Ces cas lèvent une erreur avant le remplacement du document courant. Un fichier
refusé n’est ni réécrit ni archivé.

## À faire dans le prochain lot

- vérifier manuellement les formats MIME réellement exposés par Word et Google
  Docs sous Windows ;
- préparer un lot séparé pour la représentation et le round-trip des images
  Qt, avant d’autoriser leur collage riche ;
- éprouver le lancement et le timeout sur les plateformes distribuées ainsi
  que le conditionnement de l’extra PySide6 ;
- conserver Tkinter comme éditeur principal et fallback tant que la couverture
  éditoriale Qt n’est pas équivalente.

## Volontairement différé

- images interactives, redimensionnement, recadrage et légendes ;
- notes de bas de page et raccourci `((note))` dans l’interface Qt ;
- tableaux WYSIWYG et blocs `verbatim` ;
- autosauvegarde et récupération après incident ;
- aperçu HTML par le pipeline réel, gestion complète des fichiers et
  métadonnées éditables ;
- toute extension bidirectionnelle du protocole, notamment la transmission
  d’une configuration de preview modifiée pendant que Qt reste ouvert.

Restent également liés à l’ancien adaptateur Tkinter : construction du widget
`Text`, tags et marques, undo compensatoire, formatage GUI, affichage des
images, panneaux de notes, dialogues et bindings.
