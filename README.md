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

## Format Obligatoire Des Fichiers Markdown

Chaque fichier Markdown publié doit commencer par un front matter YAML.

Exemple page:

```yaml
---
title: "Titre de la page"
slug: "titre-de-la-page"
type: "page"
---
```

Exemple billet:

```yaml
---
title: "Premier billet"
slug: "premier-billet"
type: "post"
date: "2026-04-23"
author: "Auteur facultatif"
description: "Résumé facultatif"
draft: false
---
```

Règles:
- `title`, `slug`, `type` obligatoires pour tous les contenus.
- `type` doit valoir `page` ou `post`.
- `date` obligatoire pour `type: post` (format `YYYY-MM-DD`).
- `draft: true` exclut le contenu de la génération (HTML/TEI non produits).

## Procédure Conseillée Après Export Google Docs

1. Exporter le document en Markdown.
2. Ajouter en tête un front matter YAML complet (obligatoire).
3. Placer les images locales dans le dossier d'assets du projet (par exemple `assets/images/`) et vérifier les chemins dans le Markdown.
4. Lancer la génération du site depuis l'interface ou le pipeline de build.
