# Guide de l'interface graphique MEROPE

Ce guide explique, en langage courant, ce que fait chaque onglet de la fenêtre MEROPE et **quoi écrire dans chaque champ**, avec un exemple concret à chaque fois.

> Astuce : dans l'application, chaque champ et chaque case à cocher a maintenant une **info-bulle** — laissez la souris quelques instants au-dessus d'un champ (ou de son libellé) pour voir s'afficher la même explication + exemple que dans ce document, sans avoir à revenir ici.
>
> Un bouton **« Parcourir... »** ouvre un sélecteur de fichier/dossier natif à côté des champs suivants : tous les dossiers de l'onglet Chemins, le fichier Markdown de l'onglet Accueil, l'image de l'onglet Bannière, et le dossier images de l'onglet Médias. Les autres chemins (gabarits, XSLT...) restent à saisir à la main car ce sont des noms de fichiers internes au thème, pas des chemins à choisir sur le disque.

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
- **Charger JSON...** (Ctrl+O) : ouvre un fichier de configuration `.json` existant pour continuer à l'éditer.
- **Enregistrer** (Ctrl+S) : sauvegarde l'état actuel du formulaire dans le fichier en cours (demande un emplacement s'il n'y en a pas encore).
- **Enregistrer sous...** (Ctrl+Maj+S) : enregistre dans un nouveau fichier, en demandant toujours l'emplacement.
- **Quitter**.

**Actions**
- **Générer le site** : construit les pages HTML à partir de la configuration actuelle et du contenu présent dans les dossiers configurés. Un rapport s'affiche à la fin (succès, avertissements, ou erreurs à corriger) ; en cas de succès, une question **Ouvrir le site dans le navigateur ?** (Oui/Non) l'accompagne. Répondre Oui démarre un petit serveur local (équivalent à `python -m http.server`, mais géré directement par MEROPE — rien à installer ni à lancer à la main) sur le dossier de sortie et ouvre l'adresse dans le navigateur par défaut ; répondre Non ferme simplement le rapport. Le serveur reste actif tant que l'application est ouverte (une nouvelle génération vers le même dossier réutilise le même serveur ; vers un dossier différent, il redémarre dessus).
- **Ouvrir dossier de sortie** : pas encore disponible dans cette version (affiche un message d'information).

## Barre d'outils

Sous la barre de menu, une rangée de boutons donne un accès direct à **Nouveau projet...**, **Charger... / Enregistrer / Enregistrer sous...** (mêmes actions que le menu Fichier), à l'**Éditeur de contenu...** (détaillé plus bas) et à **Générer le site** (équivalent à Actions > Générer le site).

### Nouveau projet...

Demande un dossier (vide de préférence) puis y crée une arborescence complète et prête à l'emploi : `content/pages`, `content/posts`, `assets/images`, `assets/banner`, `theme/templates`, `theme/xslt`, une page « Bienvenue » et un billet « Bienvenue ! » contenant des explications simples pour démarrer, et une configuration (`config/site.json`) déjà chargée dans le formulaire (accueil pointant sur la page de bienvenue). Les dossiers restent modifiables ensuite dans l'onglet Chemins comme pour n'importe quel projet.

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

**Référencement (SEO)** : dès que « Base URL » est renseignée, chaque page générée reçoit automatiquement une balise `<link rel="canonical">`, une méta-description, les balises Open Graph et Twitter Card (aperçus de partage sur les réseaux), un bloc de données structurées `schema.org` (JSON-LD — `Article` pour les billets avec leur date de publication, `WebSite` pour la page d'accueil), ainsi qu'un `sitemap.xml` (avec date de dernière modification), un `feed.xml` (RSS) et un `robots.txt` référençant le sitemap. Sans « Base URL », ces fichiers annexes ne sont pas générés (avertissement affiché), mais un `robots.txt` minimal (`Allow: /`) est tout de même produit.

## 2. Bannière
*Image large affichée en haut de la page d'accueil (et éventuellement des autres pages), au-dessus du menu ou du titre. Entièrement facultative.*

| Champ | Ce qu'on y met | Exemple |
|---|---|---|
| Activer la bannière | Case à cocher : sans elle, les autres champs de cet onglet sont ignorés et rien ne s'affiche. | — |
| Image | Chemin du fichier image, relatif au dossier assets. Le bouton **Parcourir...** propose, après avoir choisi une image, de la redimensionner directement aux dimensions d'affichage de la bannière (1260 px de large × la « Hauteur (px) » ci-dessous) — recommandé si l'image d'origine est beaucoup plus grande ou n'a pas les mêmes proportions, ce qui peut sinon donner une bannière qui paraît uniformément noire ou grise faute de bien remplir la hauteur configurée. L'image d'origine n'est jamais modifiée (une copie redimensionnée est créée), et l'image choisie (redimensionnée ou non) est copiée dans `assets/banner/` du projet. | `assets/images/banniere.jpg` |
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
| Dossier TEI | Dossier intermédiaire (nommé par slug) où les fichiers TEI générés sont conservés si « Conserver TEI » est coché (pratique pour inspecter/déboguer). Indépendamment de ce réglage, une copie de chaque TEI généré est **toujours** enregistrée à côté de sa source Markdown, dans `content/pages`/`content/posts`, sous le même nom de fichier (ex. `mon-billet.md` → `mon-billet.xml`) — c'est cette copie-là qu'on garde/versionne pour conserver le TEI d'un billet. | `build/tei` |

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

Le champ **Mode** choisit comment la page d'accueil est construite :
- **Page fixe (Markdown)** : le contenu vient d'un fichier Markdown que vous rédigez (comportement historique).
- **Derniers billets publiés** : la page d'accueil liste automatiquement les billets les plus récents, du dernier publié au plus ancien — pas de fichier Markdown à entretenir.

| Champ | Ce qu'on y met | Exemple | Mode concerné |
|---|---|---|---|
| Activer accueil | Si décoché, aucune page d'accueil n'est générée. | — | les deux |
| Mode | Page fixe ou Derniers billets publiés. | — | les deux |
| Source accueil | Fichier Markdown utilisé comme contenu de l'accueil. | `content/pages/accueil.md` | Page fixe |
| Layout accueil | Gabarit HTML utilisé pour l'accueil. | `home` | Page fixe |
| Nombre de billets affichés | Combien de billets récents afficher sur l'accueil. | `5` | Derniers billets publiés |
| Titre de la liste | Titre affiché au-dessus de la liste des billets. | `Derniers billets` | Derniers billets publiés |

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
  - **Entrée de menu pointant vers :** deux choix :
    - **Lien interne** (par défaut) : une page ou un billet déjà présent sur ce site. Un second menu déroulant, **Page ou billet**, apparaît alors pour le choisir directement dans la liste (accueil, archive des billets, ou n'importe quelle page/billet existant) — il remplit automatiquement le champ Destination ci-dessous.
    - **Lien externe** : un autre site web. Ce lien ne fait pas sortir du site : la page générée affiche le site externe intégré dans un cadre (iframe), en conservant le menu latéral et le haut de la page de ce site, avec un lien de secours au cas où le site visé refuse d'être ainsi intégré (certains sites l'interdisent — limite du site externe, pas de ce logiciel).
  - **Destination (obligatoire)** : chemin ou URL vers laquelle ce lien pointe réellement — rempli automatiquement pour un lien interne (via le sélecteur ci-dessus), à saisir à la main pour un lien externe (ex. `https://example.org`). Reste modifiable dans tous les cas.
  - **Activé** : décocher pour masquer le lien sans le supprimer
- **Supprimer** : retire le lien définitivement.
- **Monter / Descendre** : change l'ordre d'affichage.
- **Activer/Désactiver** : bascule rapidement sans ouvrir la fenêtre d'édition.

## 8. Menu latéral
*Menu affiché sur le côté des pages, organisé sur trois niveaux au maximum. Aucun niveau au-delà de la section n'est obligatoire : une section seule, sans rien en dessous, fonctionne déjà comme un lien de menu simple.*

Sur le site généré, seules les sections (et sous-sections) sont affichées d'emblée : leur contenu (sous-sections, billets) n'apparaît qu'au survol, dans un sous-menu déroulant à droite — évite d'afficher tous les billets d'un coup. Une petite flèche (`›`) signale les sections/sous-sections qui ont un sous-menu. Sur mobile (pas de survol possible), le menu reste simplement déplié en entier.

**Titre du menu** : champ facultatif (ex. `Menu`) affiché en tête du menu latéral sur le site généré, dans une mise en forme discrète (petit, majuscules, atténué, séparé du reste par un filet) qui le distingue des sections en dessous sans les concurrencer. Laissez-le vide pour n'afficher aucun titre.

Les trois colonnes sont **vides au départ** : c'est normal, il faut commencer par la colonne de gauche.

1. **Colonne de gauche (« 1. Sections »)** : créez d'abord une ou plusieurs sections avec **+ Section** (ex. `Rhétorique`). Actions : + Section / Modifier / Supprimer / Monter / Descendre / Activer-Désactiver. Une section a un nom, un statut activé/désactivé, et peut optionnellement être elle-même un lien cliquable :
   - **Titre de section pointant vers : Aucun** (par défaut) : un simple titre de regroupement, non cliquable.
   - **Lien interne** : le titre de section devient cliquable, vers une page/un billet choisi dans un menu déroulant dédié — avec ou sans contenu en dessous.
   - **Lien externe** : le titre de section pointe vers un autre site, intégré dans un cadre (iframe) en conservant le menu et la bannière de ce site — même mécanisme que pour un lien externe ailleurs dans les menus (voir « 7. Menu supérieur »).
   - **Numérotée** (case à cocher) : préfixe automatiquement le titre de la section « I. », « II. », « III. »... selon sa position parmi les sections numérotées (les sections non numérotées ne comptent pas dans la numérotation, et le numéro n'est jamais tapé à la main : il est recalculé à chaque génération du site). Cochez-la pour un plan structuré, ex. « I. Rhétorique ».
2. **Colonne du milieu (« 2. Sous-entrées / sous-sections de la section sélectionnée »)** : cliquez sur une section à gauche pour voir/éditer son contenu ici. Deux types de lignes peuvent y apparaître, dans n'importe quelle combinaison :
   - **Sous-entrées** (bouton **+ Billet**, même libellé et même info-bulle que le bouton de la colonne de droite, ci-dessous) : un lien direct, comme avant — mêmes champs qu'une entrée du menu supérieur (label, lien interne/externe, destination, activé).
   - **Sous-sections** (bouton **+ Sous-section**, préfixées `§` dans la liste) : un sous-groupe nommé (ex. `Bossuet et la rhétorique chrétienne`), qui peut lui-même être un simple titre ou un lien cliquable (mêmes trois choix que pour une section). Si la section est **numérotée**, ses sous-sections sont automatiquement préfixées « A. », « B. », « C. »... Sélectionnez une sous-section pour voir/éditer ses billets dans la colonne de droite.
   - Cliquer sur **+ Sous-section**/**+ Billet** sans avoir sélectionné de section affiche un message vous invitant à en créer/sélectionner une d'abord.
3. **Colonne de droite (« 3. Billets de la sous-section sélectionnée »)** : cliquez sur une sous-section au milieu pour voir/éditer ses billets ici (bouton **+ Billet** — mêmes champs qu'une sous-entrée). Reste vide tant qu'aucune sous-section n'est sélectionnée (une simple sous-entrée, elle, n'a pas de niveau en dessous).

**Exemple** : pour un plan de type « I. Rhétorique / A. Bossuet et la rhétorique chrétienne / *L'héritage de saint Augustin*, *La place de l'héritage profane* » — créez la section `Rhétorique` (case Numérotée cochée), ajoutez-lui la sous-section `Bossuet et la rhétorique chrétienne`, puis ajoutez les deux billets dans la colonne de droite une fois cette sous-section sélectionnée.

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
*Réglage de l'affichage des notes de bas de page : appel de note dans le texte, texte complet en fin d'article.*

**Notes en marge : non disponibles pour le moment.** Un aperçu flottant dans la marge à côté du texte ne tenait pas de façon fiable selon la largeur de l'écran (il finissait par chevaucher soit la barre latérale, soit le texte de l'article) ; la case « Activer notes marginales » est donc désactivée dans l'interface, et le réglage est ignoré au moment de la génération même s'il est resté activé dans un fichier de configuration existant. Les notes s'affichent uniquement en texte complet en bas d'article, avec un appel de note cliquable qui fait défiler la page en douceur jusqu'à la note (et un lien retour ↩ pour revenir au texte).

| Champ | Ce qu'on y met | Exemple |
|---|---|---|
| Mode | Mode d'affichage global ; `margin_excerpt_plus_footnote` = aperçu en marge + texte complet en fin d'article (l'aperçu en marge n'est actuellement pas rendu, voir ci-dessus). | `margin_excerpt_plus_footnote` |
| Activer notes marginales | Non disponible pour le moment (voir ci-dessus). | — |
| Activer notes complètes | Si coché, le texte complet de chaque note est listé (voir « Emplacement notes finales »). | — |
| Amorce (mots) | Longueur max. de l'aperçu en marge, en nombre de mots — utilisée si « Préférer le comptage en mots » est coché. Sans effet tant que les notes en marge ne sont pas disponibles. | `8` |
| Amorce (caractères) | Longueur max. de l'aperçu en marge, en caractères — utilisée sinon. Sans effet tant que les notes en marge ne sont pas disponibles. | `80` |
| Préférer le comptage en mots | Choisit laquelle des deux limites ci-dessus s'applique. Sans effet tant que les notes en marge ne sont pas disponibles. | — |
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
| Activer la recherche sur le site | Si coché, un index de recherche (`search-index.json`) est généré à chaque build et une case de recherche apparaît sur chaque page du site publié. La recherche se fait entièrement dans le navigateur du visiteur (aucun serveur, aucune base de données) : elle filtre par sous-chaîne, insensible à la casse et aux accents, sur le titre et le texte intégral des pages et billets publiés. | — |
| Longueur de l'extrait de recherche (car.) | Nombre de caractères affichés sous chaque résultat de recherche. | `160` |

*Limite assumée : recherche par sous-chaîne simple, sans pondération ni tolérance aux fautes de frappe ; la page d'accueil et la page d'archive (simples listes de liens) ne sont pas indexées.*

---

## Éditeur de contenu

*Fenêtre séparée (bouton « Éditeur de contenu... » dans la barre d'outils) pour rédiger des pages et des billets en saisie visuelle (WYSIWYG) — sans écrire de Markdown à la main — et les enregistrer directement dans les dossiers `pages_dir`/`posts_dir` définis dans l'onglet Chemins.*

**Colonne de gauche** : liste des pages et billets déjà présents sur le disque.
- **Nouvelle page** / **Nouveau billet** : repart d'un document vierge du type choisi.
- **Ouvrir** (ou double-clic) : recharge le fichier sélectionné en saisie visuelle.
- **Importer...** : charge un fichier Markdown existant (venant d'ailleurs que ce projet) dans l'éditeur pour compléter ses métadonnées et l'enregistrer ici.
- **Convertir en page/billet** : transforme le fichier sélectionné de page en billet, ou l'inverse, sans avoir à recopier son contenu à la main — il suffit de le sélectionner puis de cliquer sur ce bouton (pas besoin de l'ouvrir d'abord). Le fichier est déplacé vers le bon dossier (`pages_dir`/`posts_dir`), renommé selon la convention du nouveau type (les billets sont préfixés par leur date, ex. `2026-05-01-mon-billet.md`) et son champ `type` est mis à jour dans le front matter. En passant de page à billet, une date de publication est demandée (AAAA-MM-JJ) ; en passant de billet à page, le champ `date` est retiré. Une confirmation est demandée, car **l'URL du contenu change** (une page vit à `/slug/`, un billet à `/billets/slug/` par exemple) — les liens déjà posés ailleurs (menus, autres billets...) vers l'ancienne adresse ne sont pas mis à jour automatiquement.
- **Supprimer** : supprime définitivement le fichier sélectionné (confirmation demandée).
- **Actualiser** : recharge la liste depuis le disque.

**Barre de mise en forme** (au-dessus de la zone de texte, sur deux lignes) — comme dans TinyMCE ou Word, les boutons sont des icônes plutôt que des mots ; le nom et l'effet de chacun apparaissent dans l'info-bulle au survol :
- *Première ligne* — sélectionnez du texte puis cliquez sur **G** (gras, affiché en gras), **I** (italique, affiché en italique), **S** (barré, affiché barré), **x²** (exposant) ; ou placez le curseur sur une ligne puis cliquez sur **H1-H4** (titre), l'icône de **citation** (barre verticale + lignes), l'icône de **liste à puces** ou de **liste numérotée** pour transformer la ligne. Les quatre icônes d'alignement (barres de texte à gauche / centrées / à droite / pleine largeur) alignent le paragraphe (ou la citation) où se trouve le curseur, ou tous les paragraphes couverts par la sélection — chaque bouton fixe directement cet alignement (ce n'est pas un bascule on/off). Limite assumée : l'alignement justifié ne peut pas s'afficher tel quel dans cet éditeur (Tk ne sait pas dessiner un texte étiré aux deux marges), il apparaît aligné à gauche ici, mais le rendu réel — vraiment justifié — apparaît correctement sur le site généré.
- *Deuxième ligne* — **␣** insère une espace insécable au curseur (empêche par exemple la coupure entre un nombre et son unité, ex. `10 km`) ; elle est déjà posée automatiquement par la typographie française avant `; : ! ?` et dans les guillemets, ce bouton sert pour les autres cas. L'icône **chaîne** transforme la sélection en lien (demande l'URL). L'icône **image** insère une image existante (voir plus bas). L'icône **grille** insère un tableau simple (nombre de lignes/colonnes demandé), modifiable ensuite comme du texte structuré dans la zone grisée. **†** insère un appel de note de bas de page (voir plus bas). **Aa** (Corriger la typographie) applique aux guillemets et à la ponctuation de la sélection les mêmes règles qu'à la frappe (utile après un collage — voir ci-dessous ; remplace le texte sélectionné, la mise en forme de la sélection n'est pas conservée). **⚙** ouvre les métadonnées (titre, slug, date, auteur, description...). **Enregistrer** (avec son icône de disquette) reste étiqueté en toutes lettres, cette action validant tout le document plutôt que de mettre en forme la sélection.

**Typographie française automatique** : en tapant directement dans l'éditeur, les guillemets droits (`"`) sont convertis à la volée en guillemets français alternés (`«`/`»`, ouvrant puis fermant, puis ouvrant à nouveau...), avec une espace insécable collée à l'intérieur. Une espace insécable est aussi automatiquement posée avant `; : ! ?` (qu'elle soit tapée avec ou sans espace avant), ainsi qu'après une référence de page abrégée « p. » ou « pp. » suivie d'un chiffre (ex. « p. 12 », « pp. 12-15 »), pour empêcher que le numéro de page se retrouve seul en début de ligne. Les siècles écrits en chiffres romains suivis de « er »/« e » (ex. « Ier siècle », « XXIe siècle ») voient automatiquement leur terminaison ordinale passer en exposant (Iᵉʳ, XXIᵉ). Au collage depuis Word ou Google Docs, si le texte importé contient déjà des guillemets chevrons tels quels, ils sont conservés (jamais dédoublés ni réinterprétés comme des guillemets droits) mais l'espace qui les touche à l'intérieur (juste après l'ouvrant, juste avant le fermant) est normalisée en espace insécable si ce n'était qu'une espace normale. Ces conversions (guillemets, ponctuation double, « p. »/« pp. », siècles) s'appliquent aussi bien à la frappe qu'au collage depuis Word ou Google Docs (voir plus bas). Cela ne s'applique pas dans les zones de tableau ou de contenu non reconnu (fond grisé/jauni).

**Raccourcis clavier** : Ctrl+B (gras), Ctrl+I (italique), Ctrl+Maj+S (barré), Ctrl+Maj+= (exposant), Alt+Espace (espace insécable), Alt+J (bascule le paragraphe courant entre aligné à gauche et justifié, comme sous WordPress).

**Zoom (Ctrl+molette)** : en maintenant Ctrl et en tournant la molette de la souris au-dessus de la zone de texte ou du panneau des notes, la taille du texte (titres, gras, exposants...) et des notes de bas de page s'agrandit ou se réduit ensemble, sans modifier le texte lui-même ni le rendu du site généré (c'est un confort de lecture/saisie, propre à cette fenêtre).

**Défilement** : une échelle (ascenseur) à droite de la zone de texte permet de faire défiler le document vers le haut ou le bas, en plus de la molette et des flèches.

**Coller depuis Word ou Google Docs** : un `Ctrl+V` normal dans la zone de texte détecte automatiquement si le presse-papiers contient de la mise en forme (copie depuis Word, Google Docs, un navigateur...) et, si oui, colle le texte **avec** son gras/italique/barré/exposant/titres/liens/listes, nettoyé au passage des scories propres à ces logiciels (styles internes, balises techniques, commentaires) et retypographié à la française (guillemets, espaces insécables, siècles en exposant) comme à la frappe. Si le presse-papiers ne contient que du texte brut (ex. copié depuis le Bloc-notes), le collage classique s'effectue normalement, sans changement de comportement. Les images copiées depuis Google Docs (hébergées à distance) sont automatiquement téléchargées et enregistrées dans le dossier images du projet ; en cas d'échec (pas de réseau), un texte `[Image : ...]` est inséré à la place plutôt que de bloquer le collage. Limite assumée : comme pour l'import Markdown, tout ce qui n'est pas reconnu conserve son texte visible mais perd sa mise en forme d'origine plutôt que de planter ou d'afficher du HTML brut.

**Notes de bas de page** : un panneau dédié sous la zone de texte liste toutes les notes du document ([1], [2]...), avec un champ modifiable pour chacune — le texte de la note se corrige directement là, sans dialogue séparé. Cliquer sur un appel de note `[N]` dans le texte donne le focus à la note correspondante dans le panneau. **Supprimer** retire une note (les appels de note existants dans le texte ne sont pas retirés automatiquement).

**Raccourci `((...))`** : comme sur les carnets Hypothèses, un texte entouré de doubles parenthèses (`((comme ceci))`) est automatiquement transformé en note de bas de page, sans passer par le bouton **Note...** — y compris lorsque la note est directement collée à la ponctuation qui la suit (ex. `((comme ceci)).`), le cas le plus courant à l'usage. Seules les parenthèses simples (ex. `(a)`) ne sont pas concernées ; il faut le doublement `((`/`))` pour déclencher la conversion. À la frappe, la conversion se déclenche dès que la seconde parenthèse fermante est tapée. Au collage (`Ctrl+V`, avec ou sans mise en forme), tous les `((...))` présents dans le texte collé sont convertis de la même façon. **Cette conversion s'applique aussi au moment de la génération du site** : un fichier Markdown écrit ou importé en dehors de cet éditeur (donc jamais passé par le collage/la frappe ci-dessus) profite quand même du raccourci lors du prochain « Générer le site » — sauf dans un bloc de code (` ```...``` `) ou un passage de code en ligne (`` `comme ceci` ``), volontairement ignorés.

**Images** : l'icône **Image** de la barre de mise en forme ouvre un sélecteur de fichier et copie l'image choisie dans le dossier images du projet ; elle s'affiche ensuite en aperçu réel (pas un simple texte de remplacement), avec sa propre mini barre d'outils :
- **Poignées de redimensionnement** (petits carrés bleus aux 4 coins) : cliquer-glisser change la taille d'affichage, proportionnellement. Redimensionnement non destructif — le fichier original n'est jamais modifié, seule la taille d'affichage choisie est enregistrée.
- **⇐ / ≡ / ⇒** : alignement gauche / centré / droite. Affecte la mise en page du site publié (l'image flotte à gauche ou à droite du texte, ou reste centrée) ; dans l'éditeur, seule l'étiquette texte de l'alignement change (Tkinter ne peut pas simuler visuellement un flottement).
- **Recadrer...** : ouvre une fenêtre avec l'image en pleine résolution et un cadre de sélection à poignées ; à la validation, une **copie réellement découpée** du fichier est enregistrée (le fichier d'origine n'est pas modifié) et l'image de l'éditeur pointe désormais vers cette copie.
- **Remplacer...** : change le fichier image utilisé, en conservant la taille et l'alignement déjà choisis.

**Métadonnées** (icône **⚙**) : ouvre une petite fenêtre pour renseigner le titre, le slug (identifiant d'URL, suggéré automatiquement à partir du titre), la date (pour un billet), l'auteur, la description, le gabarit (`layout`, optionnel) et le statut brouillon. C'est l'équivalent du front matter YAML en tête d'un fichier Markdown classique, mais rempli via un formulaire plutôt qu'à la main.

**Enregistrer** : convertit le contenu saisi en Markdown (avec front matter) et l'écrit sur disque ; si les métadonnées n'ont pas encore été renseignées, la fenêtre de métadonnées s'ouvre automatiquement avant l'enregistrement.

> Limite assumée : cet éditeur ne comprend, à la réouverture d'un fichier, que le Markdown qu'il produit lui-même (voir `docs/ARCHITECTURE_PROJET.md`). Un passage non reconnu (HTML brut, syntaxe inhabituelle) est affiché tel quel dans une zone repérable (fond jauni) plutôt que d'être mal interprété ou perdu.

---

## Validation

Avant sauvegarde ou génération, la configuration est vérifiée automatiquement. Les erreurs (ex. champ obligatoire vide, chemin manquant) s'affichent dans une boîte de dialogue et empêchent l'opération tant qu'elles ne sont pas corrigées.

## Fichiers sources correspondants

- `src/bloggen/ui/main_window.py` — fenêtre principale et onglets simples (Site, Chemins, Contenus, Accueil, Blog, Rendu, Footer, Génération).
- `src/bloggen/ui/site_preview.py` — serveur HTTP local (en thread, pas de sous-processus) pour l'aperçu du site généré depuis le rapport de génération.
- `src/bloggen/ui/banner_panel.py` — onglet Bannière, redimensionnement/copie de l'image à l'import.
- `src/bloggen/ui/media_panel.py` — onglet Médias.
- `src/bloggen/ui/notes_panel.py` — onglet Notes.
- `src/bloggen/ui/menu_editor.py` — onglets Menu supérieur / Menu latéral.
- `src/bloggen/ui/dialogs.py` — boîtes de dialogue d'ajout/modification d'une entrée de menu ou d'une section.
- `src/bloggen/ui/tooltip.py` — composant d'info-bulle affiché au survol des champs.
- `src/bloggen/ui/content_editor.py` — fenêtre de l'éditeur de contenu WYSIWYG, boîte de dialogue des métadonnées, panneau de notes, typographie française en direct.
- `src/bloggen/ui/toolbar_icons.py` — icônes de la barre de mise en forme, dessinées à la volée (pas de fichiers image externes).
- `src/bloggen/ui/image_widget.py` — aperçu d'image réel, poignées de redimensionnement, alignement, recadrage.
- `src/bloggen/markdown/rich_text_model.py`, `rich_text_export.py`, `rich_text_import.py` — modèle pivot et conversions Markdown <-> saisie visuelle.
- `src/bloggen/markdown/typography.py` — conversion des guillemets et espaces insécables.
- `src/bloggen/markdown/note_shortcuts.py` — conversion du raccourci `((note))` en note de bas de page, à la frappe et au collage dans l'éditeur, ainsi qu'au moment de la génération pour le Markdown qui n'est pas passé par l'éditeur.
- `src/bloggen/markdown/image_attributes.py` — suffixe `{width=... height=... align=...}` sur les images Markdown.
- `src/bloggen/ui/clipboard_html.py` — lecture du presse-papiers au format HTML (Word/Google Docs/navigateurs).
- `src/bloggen/markdown/html_paste_import.py` — conversion du HTML collé vers le modèle de blocs.
- `src/bloggen/content/writer.py` — écriture des fichiers de pages/billets (slug, nom de fichier, front matter).
