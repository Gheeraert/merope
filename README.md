# Blog Static Generator — V1

Générateur maison de site statique pour carnet académique, inspiré par un usage de type Hypothèses, mais fondé sur une chaîne entièrement statique.

## Chaîne cible

Google Docs → Markdown → XML-TEI → HTML

## Objectifs V1

- interface graphique locale (Tkinter)
- configuration JSON chargeable / sauvegardable
- menu horizontal supérieur
- menu latéral hiérarchique simple
- bannière horizontale supérieure
- billets et pages fixes
- conversion Markdown → XML-TEI via Pandoc
- transformation TEI → HTML via XSLT
- images avec lightbox type Fancybox
- amorces de notes en marge + notes complètes en bas d’article

## Philosophie

Le projet n’est **pas** un CMS.  
C’est un outil de préparation, de configuration et de génération de site statique éditorial.

## Dépendances prévues

- Python 3.11+
- Tkinter
- lxml
- Pandoc installé dans le système
- pytest

## Arborescence de départ

Voir :

- `docs/ARCHITECTURE_PROJET.md`
- `docs/CODEX_BRIEF_V1.md`

## État

Ce dépôt est un **squelette documentaire de démarrage** destiné à lancer proprement un développement avec Codex.
