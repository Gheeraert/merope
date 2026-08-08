# Guide de l'interface graphique MEROPE

Ce guide explique, en langage courant, ce que fait chaque onglet de la fenêtre MEROPE et **quoi écrire dans chaque champ**, avec un exemple concret à chaque fois.

> Astuce : dans l'application, chaque champ et chaque case à cocher a maintenant une **info-bulle** — laissez la souris quelques instants au-dessus d'un champ (ou de son libellé) pour voir s'afficher la même explication + exemple que dans ce document, sans avoir à revenir ici.

## Comment lire ce document

Pour chaque onglet :
- une phrase qui explique **à quoi il sert**,
- puis, pour chaque champ, **ce qui est attendu** et **un exemple**.

Les champs marqués **obligatoire** doivent être remplis avant de pouvoir enregistrer ou générer le site ; les autres peuvent rester vides sans bloquer.

Sauf mention contraire, les chemins de fichiers/dossiers demandés sont **relatifs** : ils partent soit de la racine du projet (`project_root`, onglet Chemins), soit d'un des sous-dossiers qu'elle définit. Utilisez toujours des slashs `/`, même sous Windows (ex. `content/pages`, pas `content\pages`).

---

## Barre de menu

**Fichier**
- **Nouveau** : repart d'une configuration vierge (valeurs par défaut).
- **Charger JSON...** : ouvre un fichier de configuration `.json` existant pour continuer à l'éditer.
- **Enregistrer** : sauvegarde l'état actuel du formulaire. La première fois, une fenêtre demande où créer le fichier.
- **Quitter**.

**Actions**
- **Générer le site** : construit les pages HTML à partir de la configuration actuelle et du contenu présent dans les dossiers configurés. Un rapport s'affiche à la fin (succès, avertissements, ou erreurs à corriger).
- **Ouvrir dossier de sortie** : pas encore disponible dans cette version (affiche un message d'information).

---

## 1. Site
*Identité générale du site : ce qui apparaît dans l'onglet du navigateur, en haut des pages, et dans les métadonnées utilisées par les moteurs de recherche et les flux RSS.*

| Champ | Ce qu'on y met | Exemple |
|---|---|---|
| Titre **(obligatoire)** | Le nom du site. | `Carnets de recherche` |
| Sous-titre | Une accroche courte affichée sous le titre. | `Notes de terrain et carnets d'enquête` |
| Langue **(obligatoire)** | Code de langue à deux lettres (norme ISO 639-1). | `fr` |
| Base URL | Adresse complète où le site sera mis en ligne, **sans** `/` à la fin. Sert à générer les liens absolus, le sitemap et le flux RSS. | `https://moncarnet.example.org` |
| Auteur | Le nom affiché comme auteur du site. | `Jeanne Dupont` |
| Description | Un résumé en une phrase, utilisé pour le référencement (SEO) et les aperçus de partage sur les réseaux. | `Carnet de recherche sur les archives orales du XIXe siècle.` |

## 2. Bannière
*Image large affichée en haut de la page d'accueil (et éventuellement des autres pages), au-dessus du menu ou du titre. Entièrement facultative.*

| Champ | Ce qu'on y met | Exemple |
|---|---|---|
| Activer la bannière | Case à cocher : sans elle, les autres champs de cet onglet sont ignorés et rien ne s'affiche. | — |
| Image | Chemin du fichier image, relatif au dossier assets. | `assets/images/banniere.jpg` |
| Lien | Page ouverte quand on clique sur la bannière. | `/index.html` |
| Alt | Texte alternatif de l'image (accessibilité, lu par les lecteurs d'écran). | `Vue aérienne du campus au printemps` |
| Hauteur (px) | Hauteur d'affichage en pixels ; l'image est recadrée pour la remplir. | `220` |
| Afficher le titre sur l'image | Si coché, le titre du site est superposé en texte sur la bannière plutôt qu'affiché séparément en dessous. | — |

## 3. Chemins
*Où se trouvent (ou doivent être créés) tous les dossiers utilisés par le générateur. Les chemins ci-dessous sont relatifs à « Racine projet », sauf celle-ci qui peut être absolue. Vous n'avez pas besoin de créer ces dossiers à l'avance : MEROPE les crée si besoin.*

| Champ | Ce qu'on y met | Exemple |
|---|---|---|
| Racine projet | Le dossier de base du projet ; tous les autres chemins en partent. `.` signifie « le dossier où se trouve le fichier de configuration ». | `.` ou `C:/Users/moi/mon-carnet` |
| Dossier contenu | Regroupe l'ensemble du contenu source (pages + billets). | `content` |
| Dossier pages | Pages statiques (à propos, contact...). | `content/pages` |
| Dossier billets | Articles de blog datés. | `content/posts` |
| Dossier assets | Fichiers annexes copiés tels quels (images, PDF...). | `assets` |
| Dossier thème | Contient les gabarits et le CSS/JS du thème graphique. | `theme` |
| Dossier templates | Sous-dossier du thème avec les fichiers `.html` de gabarit. | `theme/templates` |
| Dossier XSLT | Sous-dossier du thème avec les feuilles de transformation TEI → HTML. | `theme/xslt` |
| Dossier sortie | Où le site final est généré ; peut être vidé automatiquement à chaque génération (voir onglet Génération). | `site` |
| Dossier TEI | Dossier intermédiaire où les fichiers TEI générés sont conservés (pratique pour inspecter/déboguer). | `build/tei` |

## 4. Contenus
*Comment MEROPE doit lire vos fichiers Markdown avant de les transformer en pages.*

| Champ | Ce qu'on y met | Exemple |
|---|---|---|
| Format source | Format des fichiers à importer. Seul le Markdown est actuellement pris en charge. | `markdown` |
| Origine markdown | D'où viennent vos fichiers, pour adapter le nettoyage automatique (ex. artefacts d'export Google Docs). | `google_docs_export` |
| Layout page | Nom du gabarit utilisé par défaut pour une page qui ne précise rien dans son en-tête. | `page` |
| Layout billet | Idem pour un billet. | `post` |
| Mode slugification | Méthode de fabrication des identifiants d'URL à partir des titres ; `ascii` retire les accents (é → e). | `ascii` |
| Utiliser front matter | Si coché, MEROPE lit les métadonnées (titre, date, layout...) placées en tête de chaque fichier, entre deux lignes `---`. | — |
| Copier assets liés | Si coché, les images/fichiers référencés dans vos billets/pages sont automatiquement copiés dans le site généré. | — |

**Qu'est-ce que le « front matter » ?** C'est un petit bloc au tout début d'un fichier Markdown, entre deux lignes de tirets, où l'on précise des informations sur la page :

```
---
title: Mon premier billet
date: 2026-08-08
layout: post
---
Le contenu de l'article commence ici...
```

## 5. Accueil
*Configuration de la page d'accueil du site (`index.html`).*

| Champ | Ce qu'on y met | Exemple |
|---|---|---|
| Activer accueil | Si décoché, aucune page d'accueil n'est générée. | — |
| Source accueil | Fichier Markdown utilisé comme contenu de l'accueil. | `content/pages/accueil.md` |
| Layout accueil | Gabarit HTML utilisé pour l'accueil. | `home` |
| Afficher billets récents | Si coché, une liste des derniers billets publiés apparaît sur l'accueil. | — |
| Nombre billets récents | Combien de billets afficher dans cette liste (nombre entier). | `5` |

## 6. Blog
*Comportement de la section « blog » : liste chronologique des billets et page d'archive.*

| Champ | Ce qu'on y met | Exemple |
|---|---|---|
| Activer blog | Si décoché, ni page de blog ni archive ne sont générées. | — |
| Billets par page | Nombre de billets affichés avant pagination (nombre entier). | `10` |
| Générer archive | Si coché, une page listant tous les billets est créée. | — |
| Titre archive | Titre affiché en haut de cette page. | `Billets` |
| Chemin archive | Segment d'URL de la page d'archive, sans `/` au début ni à la fin. | `billets` (donne `/billets/index.html`) |
| Tri décroissant par date | Si coché, les billets les plus récents apparaissent en premier. | — |

## 7. Menu supérieur
*Les liens affichés dans la barre de menu en haut de chaque page (ex. Accueil, Billets). L'ordre de la liste est l'ordre d'affichage.*

Actions disponibles (boutons à droite de la liste) :
- **Ajouter / Modifier** : ouvre une fenêtre avec :
  - **Label (obligatoire)** : texte du lien. Exemple : `Billets`
  - **Target (obligatoire)** : destination — un chemin interne commençant par `/` (ex. `/billets/index.html`) ou une URL externe complète (ex. `https://example.org`)
  - **Type** : `internal` (page de ce site) ou `external` (autre site)
  - **Activé** : décocher pour masquer le lien sans le supprimer
  - **Nouvel onglet** : ouvre le lien dans un nouvel onglet du navigateur
- **Supprimer** : retire le lien définitivement.
- **Monter / Descendre** : change l'ordre d'affichage.
- **Activer/Désactiver** : bascule rapidement sans ouvrir la fenêtre d'édition.

## 8. Menu latéral
*Menu affiché sur le côté des pages, organisé en sections (colonne de gauche) contenant chacune des sous-entrées (colonne de droite). Un seul niveau de sous-entrées est possible — pas de sous-sous-menu.*

- Colonne de gauche (**sections**) : + Section / Modifier / Supprimer / Monter / Descendre / Activer-Désactiver. Une section n'a qu'un nom (ex. `Navigation`) et un statut activé/désactivé.
- Colonne de droite (**sous-entrées de la section sélectionnée**) : mêmes actions, et chaque sous-entrée a les mêmes champs qu'une entrée du menu supérieur (label, cible, type, activé, nouvel onglet).

## 9. Rendu
*Quels fichiers de thème utiliser pour transformer le contenu en HTML, et options d'affichage des images.*

| Champ | Ce qu'on y met | Exemple |
|---|---|---|
| Nom thème | Nom indicatif du thème actif (n'affecte pas les chemins, définis onglet Chemins). | `default` |
| Template page | Fichier de gabarit HTML pour les pages, cherché dans le dossier templates. | `page.html` |
| Template billet | Idem pour les billets. | `post.html` |
| Template accueil | Idem pour l'accueil. | `home.html` |
| Fichier XSLT | Feuille XSLT qui transforme le TEI intermédiaire en HTML, cherchée dans le dossier XSLT. | `tei_to_html.xsl` |
| HTML lisible | Si coché, le HTML généré est indenté (plus facile à relire, un peu plus volumineux). | — |
| Conserver TEI | Si coché, les fichiers TEI intermédiaires sont gardés dans le dossier TEI au lieu d'être supprimés après génération. | — |
| Activer lightbox | Si coché, les images des articles s'ouvrent en grand au clic plutôt que de rester simplement affichées en ligne. | — |
| Moteur lightbox | Bibliothèque JavaScript utilisée pour cet agrandissement. | `fancybox` |

## 10. Médias
*Comment les images référencées dans vos billets/pages sont récupérées, copiées et affichées.*

| Champ | Ce qu'on y met | Exemple |
|---|---|---|
| Stratégie | Méthode de récupération des médias ; `copy_local_assets` copie les fichiers déjà présents localement. | `copy_local_assets` |
| Dossier images | Où sont copiées les images du site généré. | `assets/images` |
| Copier médias vers sortie | Si coché, les images sont copiées à chaque génération (à désactiver seulement si vous gérez les images vous-même). | — |
| Figures cliquables | Si coché, chaque image devient cliquable pour s'afficher en grand. | — |
| Regrouper figures par article | Si coché, les images d'un même article forment un groupe navigable dans la visionneuse (nécessite le moteur `fancybox`). | — |
| Utiliser légendes comme légendes lightbox | Si coché, la légende Markdown sous l'image est réutilisée dans la visionneuse plein écran. | — |

## 11. Notes
*Réglage de l'affichage des notes de bas de page : appel de note dans le texte, aperçu en marge, texte complet.*

| Champ | Ce qu'on y met | Exemple |
|---|---|---|
| Mode | Mode d'affichage global ; `margin_excerpt_plus_footnote` = aperçu en marge + texte complet en fin d'article. | `margin_excerpt_plus_footnote` |
| Activer notes marginales | Si coché, un court aperçu de chaque note apparaît dans la marge, à côté du texte. | — |
| Activer notes complètes | Si coché, le texte complet de chaque note est listé (voir « Emplacement notes finales »). | — |
| Amorce (mots) | Longueur max. de l'aperçu en marge, en nombre de mots — utilisée si « Préférer le comptage en mots » est coché. | `8` |
| Amorce (caractères) | Longueur max. de l'aperçu en marge, en caractères — utilisée sinon. | `80` |
| Préférer le comptage en mots | Choisit laquelle des deux limites ci-dessus s'applique. | — |
| Emplacement notes finales | Où placer la liste des notes complètes ; `end_of_article` les regroupe en fin de billet/page. | `end_of_article` |

## 12. Footer
*Contenu affiché en bas de chaque page du site.*

| Champ | Ce qu'on y met | Exemple |
|---|---|---|
| Texte footer | Texte libre (copyright, mentions légales...). | `© 2026 Jeanne Dupont — Tous droits réservés` |
| Afficher info génération | Si coché, ajoute une mention « généré avec MEROPE ». | — |
| Afficher date build | Si coché, affiche la date de la dernière génération du site. | — |

## 13. Génération
*Réglages du processus de génération, déclenché via le menu Actions > Générer le site.*

| Champ | Ce qu'on y met | Exemple |
|---|---|---|
| Commande pandoc | Commande ou chemin complet vers l'exécutable Pandoc. Laissez `pandoc` si l'outil est déjà installé et accessible depuis le terminal. | `pandoc` ou `C:/Program Files/Pandoc/pandoc.exe` |
| Nettoyer dossier de sortie | Si coché, le dossier de sortie est entièrement vidé avant chaque génération (évite les fichiers obsolètes). | — |
| Copier assets | Si coché, le dossier assets est copié vers la sortie à chaque génération. | — |
| Échouer si assets manquants | Si coché, la génération s'arrête en erreur quand un fichier référencé (image, PDF...) est introuvable. Si décoché, un avertissement s'affiche mais la génération continue. | — |
| Échouer si config invalide | Si coché, la génération est bloquée tant que des erreurs de validation subsistent. | — |

---

## Validation

Avant sauvegarde ou génération, la configuration est vérifiée automatiquement. Les erreurs (ex. champ obligatoire vide, chemin manquant) s'affichent dans une boîte de dialogue et empêchent l'opération tant qu'elles ne sont pas corrigées.

## Fichiers sources correspondants

- `src/bloggen/ui/main_window.py` — fenêtre principale et onglets simples (Site, Chemins, Contenus, Accueil, Blog, Rendu, Footer, Génération).
- `src/bloggen/ui/banner_panel.py` — onglet Bannière.
- `src/bloggen/ui/media_panel.py` — onglet Médias.
- `src/bloggen/ui/notes_panel.py` — onglet Notes.
- `src/bloggen/ui/menu_editor.py` — onglets Menu supérieur / Menu latéral.
- `src/bloggen/ui/dialogs.py` — boîtes de dialogue d'ajout/modification d'une entrée de menu ou d'une section.
- `src/bloggen/ui/tooltip.py` — composant d'info-bulle affiché au survol des champs.
