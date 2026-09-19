# MÉROPE

Générateur de site statique pour carnet académique, inspiré par un usage de type Hypothèses, mais fondé sur une chaîne entièrement statique : pas de serveur applicatif, pas de base de données, un site HTML autonome en sortie.

## Chaîne de publication

```text
configuration JSON (site.json)
     +
contenus Markdown
     ↓
Pandoc
     ↓
XML-TEI
     ↓
post-traitements et validation
     ↓
XSLT
     ↓
HTML statique
```

MÉROPE se présente sous trois formes complémentaires :

- une **application desktop** (Tkinter, avec un éditeur de contenu Qt en complément — voir plus bas) pour préparer, écrire et générer un site sans toucher au JSON ni au Markdown à la main ;
- une **CLI headless** (`bloggen build --config ...`) pour générer un site en ligne de commande, sans interface graphique ;
- un **module de publication FTP/FTPS** pour déployer le site généré vers un hébergement distant.

MÉROPE ne génère que des fichiers statiques : il n’y a pas de CMS, pas de back-office web, pas de partie serveur à héberger.

## Objectifs V1

- interface graphique locale principale en Tkinter
- deux éditeurs de contenu disponibles : l’éditeur Tkinter historique et
  l’éditeur Qt expérimental, tous deux pour les pages/billets sans écrire de
  Markdown à la main
- configuration JSON chargeable / sauvegardable
- menu horizontal supérieur
- menu latéral hiérarchique simple
- bandeau institutionnel et bannière éditoriale
- billets et pages fixes
- conversion Markdown → XML-TEI via Pandoc
- transformation TEI → HTML via XSLT
- images avec lightbox type Fancybox
- notes complètes en bas d'article
- recherche plein texte statique côté client
- RSS, sitemap, robots.txt et méta SEO de base
- génération en ligne de commande (headless), en plus de l'interface graphique
- publication FTP/FTPS depuis l'interface

Détail complet des fonctionnalités livrées : `docs/ROADMAP.md`.

## Philosophie

Le projet n’est **pas** un CMS.  
C’est un outil de préparation, d’édition, de configuration et de génération de site statique éditorial.

## Dépendances prévues

- Python 3.11+
- Tkinter
- PySide6 optionnel pour l’éditeur Qt (`pip install -e ".[qt_editor]"`)
- pyspellchecker optionnel, même extra, pour le correcteur orthographique visuel de l’éditeur Qt
- lxml
- Pillow
- Pandoc installé dans le système
- pytest

## Documentation

Pour utiliser MÉROPE sans entrer dans son architecture interne :

- `docs/GUIDE_UI.md` — **manuel utilisateur**, organisé selon le parcours réel : créer un projet, écrire, organiser, générer et publier ;
- `docs/REFERENCE_CONFIGURATION.md` — **référence exhaustive de la configuration**, y compris les options masquées de compatibilité ;
- `docs/CONTRATS_DONNEES.md` — ce que MÉROPE préserve, refuse ou transforme, et pourquoi.

Pour le développement :

- `docs/ARCHITECTURE_PROJET.md` — architecture du code et frontières de sécurité ;
- `docs/SPEC_JSON_CONFIG_V1.md` — contrat technique et invariants du format `site.json` ;
- `docs/QT_MIGRATION.md` — état de la migration de l’éditeur vers Qt ;
- `docs/TABLE_CORRESPONDANCE_MD_TEI_HTML.md` — correspondance Markdown → TEI → HTML ;
- `docs/ROADMAP.md` — livré, dette connue et prévisions ;
- `AUDIT.md` — historique des audits de sécurité et de robustesse.

## État

Le générateur est fonctionnel de bout en bout : configuration, édition de contenu, génération du site, contrôles, recherche statique, publication FTP/FTPS et CLI headless. La suite `pytest` couvre le comportement automatisable ; la recette visuelle des interfaces reste nécessaire.

Deux éditeurs de contenu coexistent actuellement dans l’interface principale :

- **Éditeur de contenu...** ouvre l’éditeur Tkinter historique, qui reste le fallback ;
- **Éditeur Qt (expérimental)...** lance l’adaptateur Qt dans un processus séparé. Il reste en phase de recette et ne remplace pas encore officiellement l’éditeur Tkinter.

Les deux éditeurs lisent et écrivent le même modèle MÉROPE et les mêmes fichiers Markdown.

## Démarrage rapide

```bash
pip install -e .
bloggen gui
```

Dans l’interface :

1. **Nouveau projet...**
2. renseigner au minimum le titre du site ;
3. créer ou importer une page/un billet avec un éditeur de contenu ;
4. **Générer le site** ;
5. ouvrir le résultat dans le navigateur depuis le rapport de génération.

Pour publier RSS et sitemap, renseigner aussi **Site > Base URL**.

## Format obligatoire des fichiers Markdown

Chaque fichier Markdown publié doit commencer par un front matter YAML.

Exemple page :

```yaml
---
title: "Titre de la page"
slug: "titre-de-la-page"
type: "page"
---
```

Exemple billet :

```yaml
---
title: "Premier billet"
slug: "premier-billet"
type: "post"
date: "2026-09-18"
author: "Auteur facultatif"
description: "Résumé facultatif"
draft: false
---
```

Règles principales :

- `title`, `slug`, `type` obligatoires ;
- `type` vaut `page` ou `post` ;
- `date` obligatoire pour `type: post` au format `YYYY-MM-DD` ;
- `draft: true` exclut le contenu de la génération.

Les éditeurs graphiques remplissent ces métadonnées par formulaire : il n’est normalement pas nécessaire de saisir ce YAML à la main.

## Génération en ligne de commande

```bash
pip install -e .
bloggen build --config chemin/vers/config/site.json
```

Le code de sortie vaut `0` en cas de succès, `1` sinon. Pour ouvrir l’interface graphique : `bloggen gui` ou `python -m bloggen.app`.

## RSS, sitemap et thème

Voir `docs/GUIDE_UI.md` pour l’usage courant et `docs/REFERENCE_CONFIGURATION.md` pour les clés exactes. La personnalisation du thème et les invariants techniques sont décrits dans `docs/SPEC_JSON_CONFIG_V1.md`.
