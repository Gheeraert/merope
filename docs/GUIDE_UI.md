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
- **Générer le site** : construit les pages HTML à partir de la configuration actuelle et du contenu présent dans les dossiers configurés. Un rapport s'affiche à la fin (succès, avertissements, ou erreurs à corriger).
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
  - **Entrée de menu pointant vers :** deux choix :
    - **Lien interne** (par défaut) : une page ou un billet déjà présent sur ce site. Un second menu déroulant, **Page ou billet**, apparaît alors pour le choisir directement dans la liste (accueil, archive des billets, ou n'importe quelle page/billet existant) — il remplit automatiquement le champ Destination ci-dessous.
    - **Lien externe** : un autre site web. Ce lien ne fait pas sortir du site : la page générée affiche le site externe intégré dans un cadre (iframe), en conservant le menu latéral et le haut de la page de ce site, avec un lien de secours au cas où le site visé refuse d'être ainsi intégré (certains sites l'interdisent — limite du site externe, pas de ce logiciel).
  - **Destination (obligatoire)** : chemin ou URL vers laquelle ce lien pointe réellement — rempli automatiquement pour un lien interne (via le sélecteur ci-dessus), à saisir à la main pour un lien externe (ex. `https://example.org`). Reste modifiable dans tous les cas.
  - **Activé** : décocher pour masquer le lien sans le supprimer
- **Supprimer** : retire le lien définitivement.
- **Monter / Descendre** : change l'ordre d'affichage.
- **Activer/Désactiver** : bascule rapidement sans ouvrir la fenêtre d'édition.

## 8. Menu latéral
*Menu affiché sur le côté des pages, organisé en deux étapes.*

Les deux colonnes sont **vides au départ** : c'est normal, il faut commencer par la colonne de gauche.

1. **Colonne de gauche (« 1. Sections »)** : créez d'abord une ou plusieurs sections avec **+ Section** (ex. `Le projet`). Actions : + Section / Modifier / Supprimer / Monter / Descendre / Activer-Désactiver. Une section a un nom, un statut activé/désactivé, et — nouveau — peut optionnellement être elle-même un lien cliquable :
   - **Titre de section pointant vers : Aucun** (par défaut) : comportement inchangé, un simple titre de regroupement, non cliquable.
   - **Lien interne** : le titre de section devient cliquable, vers une page/un billet choisi dans un menu déroulant dédié — **avec ou sans sous-entrées**. Les sous-menus ne sont donc plus obligatoires pour placer un billet ou une page au premier niveau du menu latéral : une section seule, sans aucune sous-entrée, suffit.
   - **Lien externe** : le titre de section pointe vers un autre site, intégré dans un cadre (iframe) en conservant le menu et la bannière de ce site — même mécanisme que pour un lien externe en sous-entrée (voir « 7. Menu supérieur »).
2. **Colonne de droite (« 2. Sous-entrées de la section sélectionnée »)** : cliquez sur une section à gauche pour voir/éditer ses sous-entrées ici. Elle reste vide tant qu'aucune section n'est sélectionnée ou créée, ou si la section n'a volontairement aucune sous-entrée (cas d'une section qui n'est qu'un lien direct). Cliquer sur **+ Sous-entrée** sans avoir sélectionné de section affiche un message vous invitant à en créer/sélectionner une d'abord, au lieu de ne rien faire silencieusement. Chaque sous-entrée a les mêmes champs qu'une entrée du menu supérieur (label, lien interne/externe, destination, activé) — voir la section « 7. Menu supérieur » ci-dessus pour le détail de ces champs.

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
- **Supprimer** : supprime définitivement le fichier sélectionné (confirmation demandée).
- **Actualiser** : recharge la liste depuis le disque.

**Barre de mise en forme** (au-dessus de la zone de texte, sur deux lignes) :
- *Première ligne* — sélectionnez du texte puis cliquez sur **G** (gras), **I** (italique), **S** (barré), **X²** (exposant) ; ou placez le curseur sur une ligne puis cliquez sur **H1-H4** (titre), **Citation**, **Liste à puces**, **Liste numérotée** pour transformer la ligne. **Gauche / Centré / Droite / Justifié** alignent le paragraphe (ou la citation) où se trouve le curseur, ou tous les paragraphes couverts par la sélection — chaque bouton fixe directement cet alignement (ce n'est pas un bascule on/off). Limite assumée : « Justifié » ne peut pas s'afficher tel quel dans cet éditeur (Tk ne sait pas dessiner un texte étiré aux deux marges), il apparaît aligné à gauche ici, mais le rendu réel — vraiment justifié — apparaît correctement sur le site généré.
- *Deuxième ligne* — **Espace insécable** insère une espace insécable au curseur (empêche par exemple la coupure entre un nombre et son unité, ex. `10 km`) ; elle est déjà posée automatiquement par la typographie française avant `; : ! ?` et dans les guillemets, ce bouton sert pour les autres cas. **Lien...** transforme la sélection en lien (demande l'URL). **Image...** insère une image existante (voir plus bas). **Tableau...** insère un tableau simple (nombre de lignes/colonnes demandé), modifiable ensuite comme du texte structuré dans la zone grisée. **Note...** insère un appel de note de bas de page (voir plus bas). **Corriger la typographie** applique aux guillemets et à la ponctuation de la sélection les mêmes règles qu'à la frappe (utile après un collage — voir ci-dessous ; remplace le texte sélectionné, la mise en forme de la sélection n'est pas conservée).

**Typographie française automatique** : en tapant directement dans l'éditeur, les guillemets droits (`"`) sont convertis à la volée en guillemets français alternés (`«`/`»`, ouvrant puis fermant, puis ouvrant à nouveau...), avec une espace insécable collée à l'intérieur. Une espace insécable est aussi automatiquement posée avant `; : ! ?` (qu'elle soit tapée avec ou sans espace avant). Les siècles écrits en chiffres romains suivis de « er »/« e » (ex. « Ier siècle », « XXIe siècle ») voient automatiquement leur terminaison ordinale passer en exposant (Iᵉʳ, XXIᵉ). Cela ne s'applique pas dans les zones de tableau ou de contenu non reconnu (fond grisé/jauni).

**Raccourcis clavier** : Ctrl+B (gras), Ctrl+I (italique), Ctrl+Maj+S (barré), Ctrl+Maj+= (exposant), Alt+Espace (espace insécable), Alt+J (bascule le paragraphe courant entre aligné à gauche et justifié, comme sous WordPress).

**Zoom (Ctrl+molette)** : en maintenant Ctrl et en tournant la molette de la souris au-dessus de la zone de texte ou du panneau des notes, la taille du texte (titres, gras, exposants...) et des notes de bas de page s'agrandit ou se réduit ensemble, sans modifier le texte lui-même ni le rendu du site généré (c'est un confort de lecture/saisie, propre à cette fenêtre).

**Défilement** : une échelle (ascenseur) à droite de la zone de texte permet de faire défiler le document vers le haut ou le bas, en plus de la molette et des flèches.

**Coller depuis Word ou Google Docs** : un `Ctrl+V` normal dans la zone de texte détecte automatiquement si le presse-papiers contient de la mise en forme (copie depuis Word, Google Docs, un navigateur...) et, si oui, colle le texte **avec** son gras/italique/barré/exposant/titres/liens/listes, nettoyé au passage des scories propres à ces logiciels (styles internes, balises techniques, commentaires) et retypographié à la française (guillemets, espaces insécables, siècles en exposant) comme à la frappe. Si le presse-papiers ne contient que du texte brut (ex. copié depuis le Bloc-notes), le collage classique s'effectue normalement, sans changement de comportement. Les images copiées depuis Google Docs (hébergées à distance) sont automatiquement téléchargées et enregistrées dans le dossier images du projet ; en cas d'échec (pas de réseau), un texte `[Image : ...]` est inséré à la place plutôt que de bloquer le collage. Limite assumée : comme pour l'import Markdown, tout ce qui n'est pas reconnu conserve son texte visible mais perd sa mise en forme d'origine plutôt que de planter ou d'afficher du HTML brut.

**Notes de bas de page** : un panneau dédié sous la zone de texte liste toutes les notes du document ([1], [2]...), avec un champ modifiable pour chacune — le texte de la note se corrige directement là, sans dialogue séparé. Cliquer sur un appel de note `[N]` dans le texte donne le focus à la note correspondante dans le panneau. **Supprimer** retire une note (les appels de note existants dans le texte ne sont pas retirés automatiquement).

**Images** : **Image...** ouvre un sélecteur de fichier et copie l'image choisie dans le dossier images du projet ; elle s'affiche ensuite en aperçu réel (pas un simple texte de remplacement), avec sa propre mini barre d'outils :
- **Poignées de redimensionnement** (petits carrés bleus aux 4 coins) : cliquer-glisser change la taille d'affichage, proportionnellement. Redimensionnement non destructif — le fichier original n'est jamais modifié, seule la taille d'affichage choisie est enregistrée.
- **⇐ / ≡ / ⇒** : alignement gauche / centré / droite. Affecte la mise en page du site publié (l'image flotte à gauche ou à droite du texte, ou reste centrée) ; dans l'éditeur, seule l'étiquette texte de l'alignement change (Tkinter ne peut pas simuler visuellement un flottement).
- **Recadrer...** : ouvre une fenêtre avec l'image en pleine résolution et un cadre de sélection à poignées ; à la validation, une **copie réellement découpée** du fichier est enregistrée (le fichier d'origine n'est pas modifié) et l'image de l'éditeur pointe désormais vers cette copie.
- **Remplacer...** : change le fichier image utilisé, en conservant la taille et l'alignement déjà choisis.

**Métadonnées...** : ouvre une petite fenêtre pour renseigner le titre, le slug (identifiant d'URL, suggéré automatiquement à partir du titre), la date (pour un billet), l'auteur, la description, le gabarit (`layout`, optionnel) et le statut brouillon. C'est l'équivalent du front matter YAML en tête d'un fichier Markdown classique, mais rempli via un formulaire plutôt qu'à la main.

**Enregistrer** : convertit le contenu saisi en Markdown (avec front matter) et l'écrit sur disque ; si les métadonnées n'ont pas encore été renseignées, la fenêtre de métadonnées s'ouvre automatiquement avant l'enregistrement.

> Limite assumée : cet éditeur ne comprend, à la réouverture d'un fichier, que le Markdown qu'il produit lui-même (voir `docs/ARCHITECTURE_PROJET.md`). Un passage non reconnu (HTML brut, syntaxe inhabituelle) est affiché tel quel dans une zone repérable (fond jauni) plutôt que d'être mal interprété ou perdu.

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
- `src/bloggen/ui/content_editor.py` — fenêtre de l'éditeur de contenu WYSIWYG, boîte de dialogue des métadonnées, panneau de notes, typographie française en direct.
- `src/bloggen/ui/image_widget.py` — aperçu d'image réel, poignées de redimensionnement, alignement, recadrage.
- `src/bloggen/markdown/rich_text_model.py`, `rich_text_export.py`, `rich_text_import.py` — modèle pivot et conversions Markdown <-> saisie visuelle.
- `src/bloggen/markdown/typography.py` — conversion des guillemets et espaces insécables.
- `src/bloggen/markdown/image_attributes.py` — suffixe `{width=... height=... align=...}` sur les images Markdown.
- `src/bloggen/ui/clipboard_html.py` — lecture du presse-papiers au format HTML (Word/Google Docs/navigateurs).
- `src/bloggen/markdown/html_paste_import.py` — conversion du HTML collé vers le modèle de blocs.
- `src/bloggen/content/writer.py` — écriture des fichiers de pages/billets (slug, nom de fichier, front matter).
