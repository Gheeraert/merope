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
- les images Markdown statiques, représentées comme de vrais
  `QTextImageFormat`, ouvertes et enregistrées sans perte de `src`, légende,
  dimensions ni alignement ;
- l’insertion d’une image locale dans un document déjà ouvert, avec copie et
  résolution du chemin relatif assurées par le service d’images partagé ;
- les appels et définitions de notes de bas de page existants, séparés entre le
  document principal et un store canonique affiché dans un panneau en lecture
  seule, puis réunis sans sérialisation Qt lors de la sauvegarde ;
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

### Images statiques

Le chemin documentaire des images est désormais :

```text
Markdown image
  → InlineRun image
  → QTextImageFormat + UserProperty Mérope
  → InlineRun image
  → Markdown image
```

Les propriétés centralisées conservent un marqueur Mérope ainsi que `src`,
`image_alt`, `width`, `height` et `align`. `QTextImageFormat.name()` reçoit le
`src` canonique sans le convertir en chemin absolu. Lors du chargement,
`QTextDocument.baseUrl` est fixé au dossier du fichier Markdown, après
validation complète du nouveau modèle. Qt peut ainsi résoudre une ressource
relative pour l’affichage sans modifier ce qui sera réexporté. Une image
absente reste une image sémantique valide et Qt peut afficher son indication
de ressource manquante.

Les dimensions Markdown restent des chaînes ou `None`. Seules les valeurs
entières positives sont recopiées dans la largeur ou la hauteur visuelle
native de Qt ; une dimension absente ou non traduisible n’est jamais inventée
à partir du rendu. L’alignement `left`, `center` ou `right` est conservé comme
donnée Mérope sans simuler pour l’instant le rendu publié. `image_alt` reste
le champ historique de légende et conserve littéralement ses marqueurs `*` et
`**` ; aucun modèle de légende distinct n’est introduit.

La commande « Insérer une image... » exige un document réel ouvert et un
répertoire d’images configuré. Elle copie le fichier avec
`copy_into_images_dir`, demande une légende simple, puis insère le même
`InlineRun` via `insert_blocks`. Undo/redo porte sur le document Qt ; la copie
physique reste volontairement sur disque après undo.

Une image Mérope est ciblée par la plage exacte de son caractère objet Qt et
par ses métadonnées reconstruites avec l’adaptateur commun. Une sélection ne
devient éditable que si elle contient exactement une image ; un curseur sans
sélection peut cibler son unique image adjacente, mais la frontière entre deux
images reste volontairement ambiguë. Un clic dans les limites visuelles de
l’objet sélectionne exactement cette plage, sans widget superposé. Les images
Qt étrangères sans marqueur Mérope sont refusées.

L’action « Image... » ouvre un dialogue simple : `src` en lecture seule,
`image_alt`, largeur, hauteur et alignement. Elle remplace l’objet ciblé par un
`QTextImageFormat` neuf produit par `make_image_format`, dans une seule
opération undo. Cette reconstruction élimine notamment toute ancienne taille
visuelle lorsqu’une dimension devient `None`, vide ou non numérique. Les
champs non touchés conservent exactement `None` ou `""`; vider explicitement
une largeur ou une hauteur signifie `None`, tandis qu’une légende vidée reste
la chaîne vide.

Les commandes gras, italique, barré, exposant et lien parcourent désormais
seulement les intervalles textuels d’une sélection. Une image traversée reste
strictement inchangée ; une sélection composée uniquement d’une image est un
no-op sans entrée undo. La suppression avec Delete/Backspace reste native Qt,
et ne touche jamais au fichier physique.

Le redimensionnement à la souris reste une interaction de viewport autour du
même objet documentaire :

```text
ImageTarget
  → rectangle visuel courant
  → poignée inférieure droite
  → drag à ratio constant
  → nouvel InlineRun (width/height)
  → make_image_format
  → QTextImageFormat
```

Le cadre et la poignée ne sont dessinés que pour la sélection exacte d’une
unique image Mérope dont la ressource possède une taille réellement lisible.
Ils sont repeints depuis les coordonnées courantes du viewport après sélection,
scroll, redimensionnement de fenêtre ou changement du document ; aucune
géométrie d’écran n’entre dans le modèle. Une image manquante reste
sélectionnable et éditable avec « Image... », mais ne propose pas de resize.

Le ratio de départ est celui de la taille effectivement affichée. Après un
geste volontaire, y compris lorsque les valeurs initiales étaient `None` ou
`50%`, largeur et hauteur deviennent deux chaînes de pixels explicites. Le
minimum de 40 px est appliqué par un facteur d’échelle commun afin de ne pas
déformer le ratio. `src`, `image_alt` et `align` restent inchangés.

La mutation documentaire commence seulement au-delà d’un seuil de déplacement
de 3 px. Tout le drag est enveloppé dans un bloc d’édition Qt extérieur : les
mises à jour visuelles intermédiaires forment une seule opération undo/redo.
Une fois ce seuil franchi, le geste continue à suivre le pointeur jusque sous
le seuil ; un retour exact à l’origine restaure les métadonnées initiales.
Un clic sans déplacement effectif ne modifie ni le document, ni son état dirty,
ni sa pile undo. Le resize ne modifie jamais le fichier bitmap ; undo/redo ne
porte que sur les métadonnées documentaires.

Le remplacement contrôlé du fichier source suit le même ciblage sémantique :

```text
ImageTarget
  → choix d’un nouveau fichier
  → copy_into_images_dir
  → nouvel image_src
  → make_image_format
  → QTextImageFormat
```

L’action « Remplacer l’image... » n’est active que pour une image Mérope ciblée
sans ambiguïté. Elle exige un fichier Markdown réellement ouvert et le
répertoire `images_dir` du projet. Le fichier choisi doit être lisible par Qt ;
il est ensuite copié sans collision et son chemin reste relatif au dossier du
Markdown grâce au service partagé avec Tkinter. Aucun chemin absolu n’entre
dans `InlineRun`.

Seul `image_src` change. La légende historique `image_alt`, la largeur, la
hauteur et l’alignement restent strictement identiques : le ratio naturel du
nouveau bitmap ne provoque aucun recalcul documentaire. Un remplacement peut
donc réparer une référence manquante, et le resize reste disponible ensuite si
l’utilisateur souhaite adapter explicitement les dimensions.

Le changement de source est une autorisation explicite de
`replace_merope_image`; le chemin ordinaire du dialogue « Image... » continue
de refuser toute modification accidentelle de `src`. Undo/redo porte sur la
référence du document seulement. Comme pour l’insertion, la nouvelle copie
physique reste sur disque après undo. Un choix annulé ou une source aboutissant
au même chemin relatif reste un no-op sans dirty state ni entrée undo.

Le recadrage est volontairement distinct du resize :

```text
ImageTarget
  → résolution du fichier source local
  → CropImageDialog
  → boîte en pixels de l’image source
  → write_cropped_copy
  → nouvel image_src
  → replace_merope_image(allow_source_change=True)
  → QTextImageFormat
```

Le resize est une modification documentaire non destructive de `width` et
`height`. Le crop crée au contraire un nouveau bitmap et ne change que `src`.
L’original reste intact ; `image_alt`, largeur, hauteur et alignement sont
conservés exactement, même lorsque le crop modifie le ratio naturel.

Le dialogue charge l’image selon la même sémantique Pillow que le service
partagé. Un noyau géométrique indépendant calcule une prévisualisation dont la
plus grande dimension ne dépasse pas 700 px, un rectangle initial à environ
10 % des bords, puis la conversion bornée des coordonnées preview vers la boîte
source `(left, top, right, bottom)`. Ses quatre poignées autorisent un crop
libre, sans conservation de ratio. Seule la boîte en pixels originaux est
transmise à `write_cropped_copy` : le pixmap réduit n’est jamais recadré ni
enregistré.

« Recadrer... » est activé séparément des autres actions image : une image
manquante, distante, absolue ou illisible reste éditable et remplaçable, mais
n’est pas recadrable. Aucun téléchargement n’est tenté. Une annulation ou un
échec d’écriture laisse le document et le disque inchangés. Après réussite,
undo/redo porte uniquement sur le nouveau `src`; le fichier `-cropN` reste sur
disque après undo, et pourrait également rester orphelin si le remplacement
documentaire échouait après son écriture.

Le service partagé conserve son comportement historique : il convertit le
résultat en RGB avant sauvegarde. Un PNG transparent peut donc perdre son canal
alpha. Aucune correction EXIF, conversion de format ou modification de cette
politique commune n’est introduite par la migration Qt.

Les images venant du collage HTML (`img`, `v:imagedata`, `v:shape`) et les
bitmaps seuls du presse-papiers restent refusés : leur extraction et leur
copie transactionnelle feront l’objet d’un autre lot.

### Notes de bas de page statiques

Le chemin documentaire des notes est désormais :

```text
Markdown
  → Block / InlineRun
  → séparation corps / FootnoteDefinitions
  → QTextDocument + panneau de définitions
  → reconstruction des blocs complets
  → Markdown
```

À l’ouverture, les blocs `FOOTNOTE_DEFINITION` sont retirés du corps avant
`populate_document` et conservés, dans leur ordre existant, sous la forme
canonique `FootnoteDefinitions = dict[str, list[InlineRun]]`. Le document Qt
principal ne montre donc pas les définitions en fin de corps. À la sauvegarde,
`extract_blocks` produit le corps et les définitions sont reconstruites en
blocs canoniques avant l’appel inchangé à `blocks_to_markdown`.

Dans le corps, un `InlineRun(footnote_ref="12")` est rendu comme le texte natif
Qt `[12]`, avec `FOOTNOTE_MARKER_PROPERTY` et `FOOTNOTE_ID_PROPERTY`. Une
propriété d’instance purement transitoire empêche Qt de fusionner deux appels
adjacents du même ID ; elle n’est jamais persistée. L’extraction exige à la
fois les propriétés Mérope et le texte visible exact. Un `[12]` tapé par
l’utilisateur reste donc du texte ordinaire, tandis qu’un marqueur incomplet
ou incohérent provoque un refus explicite.

L’apparence réduite en exposant et la couleur du marqueur sont seulement
visuelles : elles ne deviennent ni `superscript=True`, ni lien, ni autre format
inline. Les commandes gras, italique, barré, exposant et lien ignorent les
appels de note comme elles ignorent les images. Un clic sélectionne le marqueur
entier ; une sélection ou un curseur qui le traverse est étendu à l’objet
complet avant saisie, suppression, coupe ou collage. Une suppression entière
utilise l’undo/redo natif Qt et laisse volontairement sa définition dans le
store comme note orpheline.

Le panneau « Notes » est un `QDockWidget` en lecture seule. Il reconstruit un
affichage séparé par ID numérique et montre le texte ainsi que gras, italique,
barré, exposant et liens lorsque présents, sans modifier les `InlineRun`
stockés et sans rendre le document dirty. Les IDs existants ne sont pas
renumérotés. Une définition sans appel et un appel sans définition sont tous
deux conservés lors de la sauvegarde.

## Explicitement refusé

- l’ouverture éditable et l’enregistrement de fichiers contenant tableaux,
  blocs `verbatim`, titres hors H1–H4 ou listes complexes ;
- les listes vides ou imbriquées et les éléments de liste contenant des blocs ;
- l’alignement d’une sélection mêlant paragraphes et éléments de liste ;
- tout objet, cadre ou tableau Qt que l’adaptateur ne sait pas retranscrire.

Ces cas lèvent une erreur avant le remplacement du document courant. Un fichier
refusé n’est ni réécrit ni archivé.

## À faire dans le prochain lot

- porter les opérations interactives de notes sur le store canonique :
  insertion, édition et suppression explicites, puis appliquer le service
  partagé `plan_footnote_renumbering` sans inventer d’identité Qt persistée ;
- vérifier manuellement les formats MIME réellement exposés par Word et Google
  Docs sous Windows ;
- éprouver le redimensionnement sous les facteurs d’échelle d’écran réellement
  utilisés sous Windows ;
- définir séparément la stratégie de copie et de validation avant d’autoriser
  les images provenant du presse-papiers ou du HTML riche ;
- éprouver le lancement et le timeout sur les plateformes distribuées ainsi
  que le conditionnement de l’extra PySide6 ;
- conserver Tkinter comme éditeur principal et fallback tant que la couverture
  éditoriale Qt n’est pas équivalente.

## Volontairement différé

- collage d’images et édition riche des légendes ;
- édition riche des définitions, insertion/suppression interactive,
  renumérotation et raccourci `((note))` dans l’interface Qt ;
- tableaux WYSIWYG et blocs `verbatim` ;
- autosauvegarde et récupération après incident ;
- aperçu HTML par le pipeline réel, gestion complète des fichiers et
  métadonnées éditables ;
- toute extension bidirectionnelle du protocole, notamment la transmission
  d’une configuration de preview modifiée pendant que Qt reste ouvert.

Restent également liés à l’ancien adaptateur Tkinter : construction du widget
`Text`, tags et marques, undo compensatoire, formatage GUI, affichage des
images, panneaux de notes, dialogues et bindings.
