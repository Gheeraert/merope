# Préparation de la migration de l’éditeur vers Qt

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

`Block` et `InlineRun` restent le pivot canonique de l’éditeur. Le pipeline
de publication reste inchangé : Markdown → Pandoc → TEI Commons Publishing
→ XSLT → HTML.

## Ce qui est désormais indépendant de la GUI

- `content/image_service.py` : chemins relatifs des images, copie avec
  gestion des collisions, lecture et sauvegarde d’une image du
  presse-papiers via Pillow, calcul de la taille d’affichage, chargement de
  secours et création des copies recadrées ;
- `content/versioning.py` : inventaire et numérotation des archives
  `.versions`, archivage, calcul explicite des versions à purger, suppression
  après décision de l’appelant et conversion fichier page ↔ billet ;
- `content/footnotes.py` : allocation et suppression des définitions de
  notes, ordre documentaire des références et calcul du plan de
  renumérotation, y compris les notes orphelines ;
- les noyaux déjà portables restent inchangés : modèle `Block`/`InlineRun`,
  import/export Markdown, import HTML riche, typographie, raccourci
  `((note))`, attributs d’image, alignement et récupération après incident.

## Ce qui reste dépendant de Tkinter

- construction et parcours du widget `Text` ;
- tags de caractères et de blocs, index et marques Tk ;
- undo/redo compensatoire et tags de polices combinées ;
- commandes et état visuel de mise en forme ;
- affichage interactif des images, poignées et dialogue de recadrage ;
- panneau, champs, focus et marqueurs cliquables des notes ;
- dialogues, boîtes de messages et sélecteurs de fichiers ;
- bindings clavier/souris et accès au presse-papiers de l’adaptateur ;
- timers d’autosauvegarde et d’aperçu, ainsi que la fenêtre d’aperçu.

`autosave.py`, `preview.py`, `dialogs.py`, `paste.py`, `typography.py` et
`formatting.py` ont été examinés. Leur logique réutilisable est déjà dans
des modules sans GUI, ou leur extraction demanderait de modifier le contrat
de l’éditeur. Ils restent donc volontairement inchangés hors branchement aux
nouveaux services.

## Étape suivante recommandée

Créer un éditeur Qt autonome minimal, lancé dans un processus séparé, qui ne
gère d’abord que la conversion `Block`/`InlineRun ↔ QTextDocument`. Le garder
en parallèle de l’éditeur Tkinter jusqu’à ce que les tests de round-trip
Markdown et les cas de non-régression soient équivalents. PySide6 ne doit
être introduit qu’à cette étape.
