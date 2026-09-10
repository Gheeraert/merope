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

## Fonctionne maintenant

- les services sans GUI extraits lors de la première phase : images,
  versionnement et sémantique des notes ;
- un prototype autonome lancé par `python -m bloggen.ui.qt_editor`, avec un
  chemin Markdown facultatif en argument et sans commande d’enregistrement ;
- l’adaptateur explicite `Block`/`InlineRun ↔ QTextDocument` pour les
  paragraphes, titres H1 à H4, citations, listes simples à puces ou numérotées
  et alignements ;
- les formats inline gras, italique, barré, exposant et lien, y compris leurs
  combinaisons ;
- la préservation exacte des espaces insécables U+00A0 par parcours des
  `QTextBlock` et `QTextFragment`, sans `QTextDocument.toPlainText()` ;
- les listes, ancres, alignements, curseurs et piles undo/redo natifs de Qt ;
- des propriétés Mérope centralisées fondées sur `QTextFormat.UserProperty`
  pour lever les ambiguïtés sémantiques ;
- une erreur explicite avant toute modification du document pour les blocs ou
  feuilles inline que ce prototype ne sait pas conserver.

Le round-trip expérimenté est exclusivement :

```text
Markdown → rich_text_import → Block / InlineRun
         → QTextDocument
         → Block / InlineRun → rich_text_export → Markdown
```

Les fonctions Qt `toMarkdown`, `setMarkdown`, `toHtml` et `setHtml` ne font
pas partie de ce chemin.

## À faire dans le prochain lot

- valider davantage les commandes de bloc sur des sélections couvrant
  plusieurs paragraphes et listes ;
- définir le contrat d’ouverture du prototype depuis Tkinter et le cycle de
  vie du processus, sans encore fusionner les deux boucles d’événements ;
- choisir un format d’échange explicite pour transmettre le modèle canonique
  et signaler les contenus encore non pris en charge ;
- conserver l’éditeur Tkinter comme solution principale tant que la couverture
  fonctionnelle Qt n’est pas équivalente.

## Volontairement différé

- images interactives, redimensionnement, recadrage et légendes ;
- notes de bas de page et raccourci `((note))` dans l’interface Qt ;
- collage riche Word / Google Docs et presse-papiers personnalisé ;
- tableaux WYSIWYG et blocs `verbatim` ;
- autosauvegarde, récupération après incident et versions `.versions` ;
- aperçu HTML par le pipeline réel, gestion complète des fichiers et
  métadonnées éditables ;
- IPC et lancement de Qt depuis l’interface Tkinter.

Restent également liés à l’ancien adaptateur Tkinter : construction du widget
`Text`, tags et marques, undo compensatoire, formatage GUI, affichage des
images, panneaux de notes, dialogues et bindings.
