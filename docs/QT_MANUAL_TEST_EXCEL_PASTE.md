# Test manuel : tableaux de l'éditeur Qt (thème et collage Excel)

Les tests automatisés rejouent de vraies captures du presse-papiers Excel
(`tests/fixtures/excel_clipboard`), mais pas Excel ni le thème Windows en direct.
Compter cinq minutes sous Windows, éditeur Qt ouvert sur un document de test.

## Thème

1. Paramètres Windows > Personnalisation > Couleurs : passer en **Sombre**, sans
   fermer Mérope. Insérer un tableau contenant un lien.
   - L'en-tête est gris-bleu sombre, son texte clair ; le lien est bleu clair.
   - Sélectionner du texte dans une cellule d'en-tête : il reste lisible.
   - Le clic droit (menu « Tableau ») et la boîte « Insérer un tableau » sont sombres.
2. Repasser en **Clair**, toujours sans redémarrer : en-tête `#e8edf3`, texte noir,
   icônes de la barre d'outils foncées. Le document n'est pas marqué comme modifié.

## Collage Excel

Copier chaque plage dans Excel, puis Ctrl+V dans un paragraphe vide de Mérope.

| Plage copiée | Résultat attendu |
| --- | --- |
| 3 colonnes, 3 lignes (texte, dates, `007`, décimales) | Boîte « Coller un tableau », puis tableau aux valeurs identiques à l'affichage d'Excel |
| Même plage, « Première ligne = en-têtes » décochée | Ligne d'en-têtes vide au-dessus des données |
| Une seule cellule | Valeur collée comme texte, sans boîte |
| Cellules fusionnées (horizontalement, puis verticalement) | Message « cellules fusionnées », document inchangé |
| Cellule avec Alt+Entrée | Message « plusieurs lignes », document inchangé |
| Plage recouverte d'une image | Message « image ou un objet », document inchangé |
| Texte « centré sur plusieurs colonnes » | Accepté : ce n'est pas une fusion, les cellules suivantes sont vides |

Après un collage réussi, Ctrl+Z retire le tableau d'un seul coup. Enregistrer :
le fichier contient un tableau `| … |`. L'aperçu HTML l'affiche.

Contrôles de non-régression : un collage depuis Notepad ou une page web se comporte
comme avant ; Ctrl+Maj+V colle toujours le texte brut, tabulations comprises.
