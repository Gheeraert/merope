# Blog Static Generator — V1

Générateur maison de site statique pour carnet académique, inspiré par un usage de type Hypothèses, mais fondé sur une chaîne entièrement statique.

## Chaîne cible

Google Docs → Markdown → XML-TEI → HTML

## Objectifs V1

- interface graphique locale (Tkinter)
- éditeur de contenu WYSIWYG intégré (pages/billets, sans écrire de Markdown à la main)
- configuration JSON chargeable / sauvegardable
- menu horizontal supérieur
- menu latéral hiérarchique simple
- bannière horizontale supérieure
- billets et pages fixes
- conversion Markdown → XML-TEI via Pandoc
- transformation TEI → HTML via XSLT
- images avec lightbox type Fancybox
- notes complètes en bas d'article (amorces en marge prévues mais désactivées pour le moment, voir `docs/ROADMAP.md`)
- recherche plein texte statique côté client
- RSS, sitemap, robots.txt et méta SEO de base
- génération en ligne de commande (headless), en plus de l'interface graphique

Détail complet des fonctionnalités livrées : `docs/ROADMAP.md`.

## Philosophie

Le projet n’est **pas** un CMS.  
C’est un outil de préparation, de configuration et de génération de site statique éditorial.

## Dépendances prévues

- Python 3.11+
- Tkinter
- lxml
- Pillow
- Pandoc installé dans le système
- pytest

## Arborescence de départ

Voir :

- `docs/ARCHITECTURE_PROJET.md`
- `docs/CODEX_BRIEF_V1.md`

## État

Le générateur est fonctionnel de bout en bout (configuration, éditeur de contenu, génération du
site, CLI headless) et couvert par une suite de tests automatisés (`pytest`). Le suivi détaillé de
l'avancement par version (V1 livrée, V1.1/V2 à venir) est tenu dans `docs/ROADMAP.md`.

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

## Génération en ligne de commande

En plus de l'interface Tkinter, le site peut être généré sans interface graphique :

```
pip install -e .
bloggen build --config chemin/vers/config/site.json
```

Le code de sortie vaut `0` en cas de succès, `1` sinon (configuration invalide ou erreurs de
build). Utile pour scripter la génération ou l'intégrer à un pipeline CI.

Pour ouvrir l'interface graphique équivalente : `bloggen gui` (ou `python -m bloggen.app`).

## RSS, sitemap et thème

Voir `docs/SPEC_JSON_CONFIG_V1.md` pour :
- la génération automatique de `feed.xml` et `sitemap.xml` (nécessite `site.base_url`) ;
- la surcharge du CSS/JS et des gabarits HTML via `paths.theme_dir` / `paths.templates_dir`.
