# Guide utilisateur de MÉROPE

MÉROPE est un générateur de site statique éditorial : on prépare les contenus et la configuration localement, puis le logiciel produit un site HTML autonome. La chaîne générale reste :

`Markdown → XML-TEI → HTML`

Ce guide suit le **parcours de travail** plutôt que l’ordre des clés de `site.json`. Pour la liste exhaustive des paramètres, valeurs par défaut et options masquées de compatibilité, voir `docs/REFERENCE_CONFIGURATION.md`.

## 1. Démarrer un projet

Le moyen le plus simple est **Nouveau projet...** dans la barre d’outils ou le menu Fichier. Choisissez un dossier vide ou destiné au projet. MÉROPE crée une arborescence prête à l’emploi, notamment :

- `content/pages/` pour les pages ;
- `content/posts/` pour les billets ;
- `assets/` pour les images et autres fichiers ;
- `theme/` pour les gabarits, CSS/JS et XSLT ;
- `config/site.json` pour la configuration ;
- des contenus de bienvenue permettant de générer immédiatement un premier site.

Pour reprendre un projet existant, utilisez **Charger JSON...** et ouvrez son `site.json`.

Les boutons **Enregistrer** et **Enregistrer sous...** sauvegardent la configuration. Les anciens fichiers JSON peuvent contenir des paramètres qui ne sont plus affichés dans l’interface : MÉROPE les conserve lors d’un aller-retour JSON → interface → JSON lorsqu’ils appartiennent encore au modèle.

## 2. Régler l’essentiel

### Identité du site

Dans **Site**, renseignez au minimum le titre et la langue. La **Base URL** est l’adresse publique finale du site, par exemple `https://moncarnet.example.org`. Elle n’est pas nécessaire pour travailler localement, mais elle devient indispensable pour produire des URL absolues cohérentes, le flux RSS et le sitemap.

L’auteur et la description servent notamment aux métadonnées. Les champs de licence alimentent actuellement les métadonnées TEI ; ils ne provoquent pas à eux seuls l’affichage d’une licence dans les pages HTML.

### Bandeau supérieur et bannière

MÉROPE distingue deux images :

- **Bandeau supérieur** : image institutionnelle facultative, conservée telle quelle, tout en haut du site ;
- **Bannière** : grande image éditoriale, avec hauteur configurable et possibilité de superposer le titre et le sous-titre.

Le bouton **Parcourir...** copie les images choisies dans le projet. Pour la bannière, MÉROPE peut aussi proposer une copie redimensionnée ; l’original n’est pas modifié.

### Chemins

L’onglet **Chemins** décrit l’arborescence du projet. Les chemins relatifs sont résolus depuis **Racine projet**. Une valeur syntaxiquement absolue est également comprise, mais le chemin résolu doit rester à l’intérieur de la racine du projet : le générateur refuse un dossier de contenu, de sortie ou d’assets situé ailleurs sur le disque. Un projet créé par **Nouveau projet...** fournit déjà des valeurs cohérentes : il n’est normalement pas nécessaire de les modifier.

Les dossiers de contenu doivent exister pour être lus. Les dossiers de sortie et certains dossiers intermédiaires sont créés lorsque la génération en a besoin.

## 3. Choisir l’accueil et le blog

Dans **Accueil**, deux modes existent :

- **Page fixe** : `index.html` reprend le contenu d’un fichier Markdown choisi ;
- **Derniers billets publiés** : l’accueil affiche automatiquement les billets les plus récents, avec titre, date, extrait et lien vers le billet complet.

Dans ce second mode, vous choisissez le nombre de billets et la longueur approximative des extraits.

Dans **Blog**, vous pouvez activer ou désactiver la section de billets, régler la pagination et la page d’archive. **Générer le flux RSS** produit `feed.xml` lorsque le blog est actif et qu’une Base URL est renseignée.

## 4. Écrire et modifier les contenus

Deux éditeurs ouvrent les mêmes fichiers Markdown et utilisent le même modèle MÉROPE :

- **Éditeur de contenu...** : éditeur Tkinter historique, stable et conservé comme solution de repli ;
- **Éditeur Qt (expérimental)...** : nouvelle interface, plus moderne, encore en phase de recette.

L’éditeur Qt nécessite PySide6 : `pip install -e ".[qt_editor]"`. Cette même commande installe aussi `pyspellchecker`, qui alimente le correcteur orthographique visuel (soulignement) de l’éditeur Qt ; s’il manque, l’éditeur reste utilisable mais le prévient au démarrage plutôt que de laisser le soulignement silencieusement absent.

### Métadonnées

Chaque page ou billet possède un petit ensemble de métadonnées : titre, slug, type, date pour les billets, auteur éventuel, description, statut brouillon. L’éditeur les présente sous forme de formulaire : il n’est pas nécessaire d’écrire le front matter YAML à la main.

Le front matter reste cependant **obligatoire dans les fichiers Markdown enregistrés**. Un contenu publié doit au minimum avoir `title`, `slug` et `type`; un billet doit en plus avoir une `date` au format `YYYY-MM-DD`. `draft: true` exclut le contenu du build.

### Mise en forme et collage

Les éditeurs couvrent les usages éditoriaux courants : titres, gras, italique, barré, exposant, citations, listes, alignements, liens, images, tableaux et notes.

#### Encadré (éditeur Qt)

Le bouton **Insérer un encadré…** de la barre d’outils, à côté de « Insérer un tableau… », demande un titre (facultatif) puis insère une boîte à bordure fine, dans laquelle vous écrivez normalement plusieurs paragraphes, citations ou listes. Entrée à la fin du titre ouvre le premier paragraphe ; le titre tient sur une seule ligne. Le bouton est inactif dans un tableau, une légende d’image, un bloc source ou un autre encadré ; les titres, images et tableaux ne peuvent pas être placés dans un encadré. Sur le site publié, l’encadré apparaît comme une boîte à marges latérales, bordure d’un pixel et titre centré. Dans l’ancien éditeur Tkinter, un encadré est affiché comme source protégée et réenregistré à l’identique.

Le collage depuis Word ou Google Docs est nettoyé pour récupérer autant que possible la structure utile sans conserver les scories propres à ces logiciels. La typographie française est normalisée, notamment pour les guillemets et les espaces insécables.

Le raccourci `((texte de note))`, familier des carnets Hypothèses, est reconnu lors de la normalisation destinée à l’aperçu et à la génération.

### Images

Une image insérée par l’éditeur est copiée dans le **Dossier images** configuré dans l’onglet Médias. Les outils d’image permettent notamment de régler la taille d’affichage, l’alignement, le remplacement et le recadrage sans écraser l’original.

### Aperçu

L’éditeur peut produire un aperçu HTML en utilisant la vraie chaîne de rendu du projet. L’aperçu ne remplace pas une génération complète : pour contrôler menus, assets, RSS, sitemap et vérifications globales, utilisez **Générer le site**.

## 5. Organiser la navigation

### Menu supérieur

Chaque entrée possède un libellé, une destination, un type de cible et un état activé/désactivé.

- **Lien interne** : pointe vers une page ou un billet du projet ;
- **Lien externe** : utilise une URL HTTP(S). MÉROPE génère une page d’intégration conservant l’environnement du site ; certains sites distants peuvent refuser l’affichage dans une iframe.

L’option **Ouvrir dans un nouvel onglet** est disponible pour les liens. Pour un lien externe intégré, le nouvel onglet ouvre la page d’intégration générée par MÉROPE.

### Menu latéral

Le menu latéral accepte trois niveaux :

1. sections ;
2. sous-entrées ou sous-sections ;
3. billets/liens dans une sous-section.

Une section peut rester un simple titre ou devenir cliquable. Les sections marquées **Numérotée** reçoivent automatiquement I., II., III. ; leurs sous-sections reçoivent A., B., C.

L’éditeur de menu permet d’ajouter, modifier, supprimer, déplacer et désactiver les entrées sans les effacer de la configuration.

## 6. Rendu, médias, notes et pied de page

### Rendu

L’onglet **Rendu** expose les fichiers qui déterminent la structure HTML (`page.html`, `post.html`, `home.html`) et la transformation XSLT du TEI vers HTML.

**Conserver TEI** garde les fichiers intermédiaires dans le dossier TEI configuré. **Diagnostic TEI Commons Publishing** vérifie le TEI généré avec les règles RelaxNG et Schematron embarquées. Par défaut une non-conformité produit un avertissement ; l’onglet Génération permet de transformer cet avertissement en erreur bloquante.

La lightbox agrandit les images au clic.

### Médias

L’onglet **Médias** permet surtout de choisir le dossier d’images, de décider si les médias sont copiés vers la sortie, et de régler le comportement des figures cliquables et de leurs légendes.

### Notes

L’interface ne montre désormais qu’un réglage utile : **Afficher les notes complètes en fin de page**. Les anciens paramètres de notes marginales sont conservés dans le modèle pour compatibilité, mais les notes marginales ne sont pas rendues actuellement.

### Footer

Le pied de page accepte un texte libre, la mention « généré avec MÉROPE » et une **date de mise à jour**. Cette dernière n’est pas la date technique du build : MÉROPE utilise d’abord la date `updated` explicite des métadonnées lorsqu’elle existe, sinon la date de modification du fichier source, puis la date de publication. La date de modification du fichier est un indicateur technique qui peut changer sans modification éditoriale du contenu.

## 7. Générer et contrôler le site

**Actions > Générer le site** ou le bouton de la barre d’outils lance le build. Le rapport final récapitule les succès, avertissements et erreurs. En cas de succès, MÉROPE peut démarrer un petit serveur HTTP local et ouvrir le site dans le navigateur.

Les réglages courants de **Génération** permettent notamment de :

- nettoyer le dossier de sortie avant le build ;
- copier les assets ;
- générer `sitemap.xml` et `robots.txt` ;
- arrêter le build si un asset manque ;
- vérifier liens et médias internes, pages orphelines, canoniques, JSON-LD, meta description et unicité du `<h1>` ;
- rendre ces vérifications bloquantes ou simplement informatives ;
- rendre bloquante la validation TEI Commons Publishing ;
- créer des redirections lors d’un changement de slug ;
- activer la recherche statique dans le navigateur et régler la longueur de ses extraits.

Le sitemap nécessite une Base URL. `robots.txt` peut être produit sans Base URL ; la référence au sitemap n’y est ajoutée que si celui-ci peut être généré.

La recherche reste entièrement statique : le build produit un index JSON, puis le navigateur filtre les résultats sans serveur ni base de données.

### Référencement : fichiers de validation

Les moteurs de recherche demandent parfois de prouver que vous possédez le site en publiant un petit fichier à sa racine (par exemple `google123456789abcdef.html` pour Google Search Console).

1. Télécharger le fichier fourni par Google Search Console ou un autre service.
2. Dans MÉROPE, onglet **Référencement**, cliquer sur « Ajouter un fichier… ».
3. MÉROPE en conserve une copie exacte dans le dossier `root-files/` du projet. Si un fichier du même nom s’y trouve déjà, une confirmation est demandée avant de le remplacer.
4. À chaque génération, le fichier est automatiquement recopié à la racine du site (`https://exemple.org/google123456789abcdef.html`), puis publié avec le reste par FTP.
5. Ne pas supprimer le fichier tant que la validation du service doit rester active. Le bouton « Supprimer » retire l’entrée de la configuration et demande s’il faut aussi supprimer la copie dans `root-files/`.

Le dossier de sortie (`site/`) reste un artefact généré : il peut être supprimé ou reconstruit sans perdre la validation. Plusieurs fichiers sont possibles. Les options `sitemap.xml` et `robots.txt` restent dans l’onglet **Génération**.

## 8. Publier par FTP/FTPS

Le bouton **Publier (FTP)...** envoie le contenu du dossier de sortie vers un serveur FTP ou FTPS. Il faut donc générer le site au moins une fois avant de publier.

Renseignez l’hôte, le port, l’utilisateur, le dossier distant et éventuellement l’URL publique. FTPS et le mode passif sont activés par défaut.

Pour le mot de passe, MÉROPE **tente d’utiliser le gestionnaire d’identifiants du système** (`keyring`). Le mot de passe **n’est jamais écrit en clair dans `site.json`**, que ce stockage sécurisé réussisse ou non : avant chaque sauvegarde, MÉROPE retire systématiquement le mot de passe du JSON. Si le stockage sécurisé réussit, le mot de passe est retrouvé automatiquement à la prochaine ouverture. S’il échoue (trousseau indisponible ou `keyring` non installé), un avertissement s’affiche : le mot de passe reste utilisable pour la session en cours, mais il faudra le ressaisir à la prochaine ouverture du projet, puisqu’il n’a été conservé nulle part.

Un ancien fichier `site.json` créé par une version antérieure peut encore contenir un mot de passe en clair : MÉROPE le lit et tente aussitôt de le migrer vers le trousseau du système. La sauvegarde suivante retire ce mot de passe du JSON dans tous les cas.

Après une première publication réussie, un manifeste distant permet à MÉROPE de repérer les fichiers qu’il avait publiés auparavant mais qui n’existent plus localement. Leur suppression n’est effectuée qu’après confirmation ; le mécanisme n’essaie pas d’effacer les fichiers étrangers au manifeste MÉROPE.

## 9. Quelques problèmes fréquents

**Le RSS ou le sitemap ne sont pas produits.** Vérifiez d’abord **Site > Base URL**. Le RSS exige aussi que le blog et l’option de génération du flux soient actifs.

**Une image n’apparaît pas.** Vérifiez le chemin de l’image, le dossier images, les options de copie des médias/assets et le rapport de génération.

**Une page a changé de slug et un ancien lien casse.** Activez les redirections de slug et régénérez le site. Les liens déjà écrits dans d’autres contenus ou menus ne sont pas tous réécrits automatiquement : les vérifications du build servent précisément à les signaler.

**Le TEI est signalé non conforme.** Le diagnostic est informatif par défaut. Les blocs de code et règles horizontales peuvent encore produire du TEI hors profil Commons Publishing.

**Un site externe ne s’affiche pas dans une entrée de menu.** Certains sites interdisent leur intégration dans une iframe. Ce comportement dépend du site distant.

**Le mot de passe FTP doit être ressaisi à chaque ouverture.** Le stockage sécurisé a probablement échoué ou `keyring` n’est pas disponible sur ce poste. Installez/configurez `keyring`, puis enregistrez de nouveau le mot de passe : il ne sera jamais écrit en clair dans `site.json`, mais sans trousseau fonctionnel il ne peut pas non plus être mémorisé d’une session à l’autre.

## 9bis. Ce que MÉROPE fait pour protéger votre travail

- **`.versions`** : avant d’écraser un fichier Markdown déjà enregistré, MÉROPE en archive une copie horodatée dans le dossier `.versions` voisin. Les versions les plus anciennes ne sont purgées qu’après confirmation explicite.
- **Récupération après incident** : les éditeurs Tkinter et Qt enregistrent périodiquement un brouillon de secours (`.merope-recovery/draft.json`). Au redémarrage, MÉROPE propose de restaurer ce brouillon s’il en trouve un. Limite connue : si Tk et Qt sont ouverts simultanément sur le même projet, ils partagent ce même brouillon.
- **Écriture atomique** : les fichiers de configuration et de contenu sont remplacés de manière atomique, afin qu’une sauvegarde interrompue (coupure, plantage) ne laisse pas normalement un fichier partiellement écrit.
- **Conservation du Markdown non reconnu** : dans les éditeurs graphiques, toute construction Markdown que l’éditeur ne sait pas représenter fidèlement est conservée telle quelle en mode source (« verbatim ») plutôt que d’être devinée ou perdue.
- **Conservation des clés de configuration inconnues** : un `site.json` créé par une version différente de MÉROPE peut contenir des réglages que la version actuelle ne connaît pas ou n’affiche pas. Ils sont préservés lors d’un cycle chargement → modification → sauvegarde plutôt que d’être silencieusement effacés.

## 10. Documentation complémentaire

- `docs/REFERENCE_CONFIGURATION.md` : référence exhaustive des clés de configuration, valeurs par défaut et options cachées ;
- `docs/CONTRATS_DONNEES.md` : ce que MÉROPE préserve, refuse ou transforme, et pourquoi ;
- `docs/SPEC_JSON_CONFIG_V1.md` : contrat technique du format JSON et invariants de validation ;
- `docs/ARCHITECTURE_PROJET.md` : architecture du code et du pipeline ;
- `docs/QT_MIGRATION.md` : état détaillé de la migration de l’éditeur vers Qt ;
- `docs/ROADMAP.md` : fonctionnalités livrées et prévues.
