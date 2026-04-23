# Cahier des charges V1

## Objet

Développer un générateur de site statique léger, pérenne et simple d’usage, destiné à produire un site de type carnet académique / blog savant, avec une chaîne :

**Google Docs → Markdown → XML-TEI → HTML**

## Périmètre V1

### Contenus
- pages fixes
- billets datés
- titres de niveaux 1 à 4
- paragraphes
- gras / italique
- listes
- liens
- notes de bas de page
- images
- tableaux simples
- citations

### Navigation
- bannière horizontale supérieure
- menu horizontal supérieur
- menu latéral à gauche, hiérarchique simple

### Interface
- application locale
- création / chargement / sauvegarde du JSON de configuration
- édition des menus depuis l’interface
- panneau bannière
- panneau médias
- panneau notes
- lancement de génération

### Rendu
- TEI comme format pivot
- XSLT pour TEI → HTML
- images cliquables avec lightbox
- amorce marginale des notes + notes complètes en fin d’article

## Hors périmètre V1
- CMS web
- authentification
- commentaires
- taxonomies complexes
- API Google Docs
- multi-utilisateur
- édition WYSIWYG interne
