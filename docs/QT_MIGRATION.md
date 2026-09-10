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
  chemin Markdown facultatif en argument, ouverture et enregistrement du
  sous-ensemble documentaire validé ;
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

## Explicitement refusé

- l’ouverture éditable et l’enregistrement de fichiers contenant images,
  notes, tableaux, blocs `verbatim`, titres hors H1–H4 ou listes complexes ;
- les listes vides ou imbriquées et les éléments de liste contenant des blocs ;
- l’alignement d’une sélection mêlant paragraphes et éléments de liste ;
- tout objet, cadre ou tableau Qt que l’adaptateur ne sait pas retranscrire.

Ces cas lèvent une erreur avant le remplacement du document courant. Un fichier
refusé n’est ni réécrit ni archivé.

## À faire dans le prochain lot

- définir le lancement du processus Qt depuis Tkinter et son cycle de vie ;
- définir un échange explicite du chemin et du résultat entre les deux
  processus, avec remontée des refus de compatibilité ;
- conserver Tkinter comme éditeur principal tant que la couverture Qt n’est
  pas équivalente.

## Volontairement différé

- images interactives, redimensionnement, recadrage et légendes ;
- notes de bas de page et raccourci `((note))` dans l’interface Qt ;
- collage riche Word / Google Docs et presse-papiers personnalisé ;
- tableaux WYSIWYG et blocs `verbatim` ;
- autosauvegarde et récupération après incident ;
- aperçu HTML par le pipeline réel, gestion complète des fichiers et
  métadonnées éditables ;
- IPC et lancement de Qt depuis l’interface Tkinter, jusqu’au prochain lot.

Restent également liés à l’ancien adaptateur Tkinter : construction du widget
`Text`, tags et marques, undo compensatoire, formatage GUI, affichage des
images, panneaux de notes, dialogues et bindings.
