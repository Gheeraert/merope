---
title: "Titre du document - Racine"
slug: "titre-racine"
type: "post"
date: "2026-04-25"
---

**RACINE-FAIRFAX**  
**Mai-Juin 2026**

**RACINE**

**A. Pilotage du flux de transcriptions**  
tenir la chaîne de traitement entre fichiers transcrits, contrôle, intégration dans ETS, validation, et remontée des problèmes.

**1\. Définir un lot pilote**

* quelques scènes simples ;  
* quelques scènes difficiles ;  
* au moins un exemple de chaque phénomène délicat.

**2\. Organiser le circuit des fichiers**

* sources brutes XMiser  
* fichiers relus  
* fichiers validés pour intégration  
* exports TEI  
* exports HTML / visualisation  
* fichiers problématiques

**3\. Définir les critères d’acceptation**

* structure stable ;  
* lignes parallèles ;  
* marqueurs correctement employés ;  
* absence d’erreurs bloquantes ;  
* relu une première fois ;  
* testé dans ETS.

**4\. Identifier les zones où XMLiser produit des fragilités**

* quelles erreurs viennent de l’OCR/transcription ;  
* quelles erreurs viennent de la préparation humaine ;  
* quelles erreurs viennent du moteur ETS ;  
* quelles erreurs révèlent un besoin d’évolution du modèle.

**B. Construction de la batterie de tests**

Trois niveaux de tests

**1\. Tests de conformité d’entrée**

* nombre de lignes cohérent dans un bloc ;  
* structure acte / scène / locuteur repérable ;  
* tildes correctement placés ;  
* absence de bricolages invisibles ;  
* encodage de caractères stable ;  
* cohérence des marqueurs.

(Ce niveau peut largement être confié à Clara…)

**2\. Tests fonctionnels dans ETS**

Une fois le fichier chargé :

* la structure est-elle reconnue ?  
* les variantes sont-elles bien calculées ?  
* les vers partagés sont-ils bien rendus ?  
* les lacunes sont-elles bien comprises ?  
* les noms de personnages / locuteurs passent-ils correctement ?  
* les didascalies explicites et implicites se comportent-elles comme prévu ?

**3\. Tests de rendu**

* la TEI est-elle cohérente ?  
* le HTML est-il lisible ?  
* les variants sont-ils interprétables ?  
* la scène correspond-elle au texte source ?  
* les erreurs sont-elles de surface ou de structure ?

**Les cas minimaux à couvrir**

* scène simple sans difficulté ;  
* variantes de ponctuation ;  
* variantes orthographiques ;  
* variation de nom de personnage ;  
* variation de locuteur ;  
* vers partagé ;  
* vers entièrement réécrit ;  
* variante partielle d’hémistiche ;  
* lacune ;  
* didascalie explicite ;  
* didascalie implicite ;  
* titre d’acte / de scène variant ;  
* liste de personnages variable ;  
* cas où la régularisée diffère utilement ;  
* cas franchement monstrueux.

**Forme de la batterie**  
Chaque test doit avoir :

* un nom ;  
* un fichier source ;  
* le phénomène visé ;  
* le comportement attendu ;  
* le résultat observé ;  
* un statut.

**C. Livrables : corpus des cas difficiles avec statuts**

Ce corpus doit servir à quoi ?

À devenir :

* le noyau de tests du projet ;  
* le matériau de discussion avec toi ;  
* le corpus de démonstration pour la stagiaire ;  
* la base de futurs développements.

Ce que doit contenir chaque cas

Pour chaque cas difficile :

***identifiant ;***

* pièce / acte / scène ;  
* phénomène en jeu ;  
* fichier source ;  
* ce qui est attendu ;  
* ce qui se passe réellement ;  
* qualification du problème.

**Vert. *Cas validé***  
Le fichier fonctionne et peut servir de référence.

**Jaune. Cas toléré / contourné**  
Le comportement n’est pas parfait, mais acceptable provisoirement.

**Orange. Cas limite**  
Le phénomène est réel, important, mais le traitement est instable ou discutable.

**Rouge. Cas bloquant**  
Impossible d’intégrer ou de publier sereinement sans correction.

**D. Registre de bugs / cas limites / besoin de développement**

Il faut distinguer quatre catégories

1\. Erreur de transcription  
2\. Erreur de protocole  
3\. Limite éditoriale  
4\. Bug logiciel / besoin de développement

Pour chaque bug, demander ces champs

* identifiant ;  
* date ;  
* signalé par ;  
* fichier concerné ;  
* description courte ;  
* étapes de reproduction ;  
* résultat attendu ;  
* résultat observé ;  
* gravité ;  
* contournement possible ;  
* besoin de développement : oui/non ;  
* priorité.  
* Hiérarchie de gravité

* bloquant : impossible de poursuivre ;  
* majeur : la sortie est fausse ou trompeuse ;  
* moyen : le rendu est gênant mais exploitable ;  
* mineur : détail cosmétique ou confort.

**E. À plus long terme : TEI enrichie \+ conformité aux guidelines**

**Volet 1**

* typer les didascalies explicites ;  
* mieux documenter locuteurs / personnages ;  
* harmoniser certains éléments de structure ;  
* préciser la documentation des témoins ;  
* clarifier certaines conventions d’appareil critique.

**Volet 2**

* traitement plus fin des didascalies implicites ;  
* meilleure modélisation des mouvements scéniques ;  
* préparation de visualisations ;  
* réflexion sur les couches analytiques.  
* Conformité aux guidelines

**F. Fixer les normes documentaires**  
1\. Arborescence des dossiers

01\_sources\_brutes  
02\_transcriptions\_en\_cours  
03\_relues  
04\_validees  
05\_tests  
06\_exports\_tei  
07\_exports\_html  
08\_cas\_limites  
09\_archive

**2\. Convention de nommage**

piece\_acte\_scene\_temoins\_version\_statut.ext

**3\. Statuts documentaires**

Chaque fichier doit être identifiable comme :

* brouillon ;  
* relu ;  
* validé ;  
* de référence ;  
* problématique ;  
* archivé.

**4\. Règles de version**

* date ;  
* version ;  
* auteur de modification si besoin ;  
* éventuellement changelog succinct.

**FAIRFAX : 8 fichiers (2x facsimilé+transcription semi-diplo+régularisée+1699)**

- Préparer une visualisation à partir de  
  - facsimilé (ordi Josselin)  
  - encodage de Claire  
  - régularisée : *avec la stagiaire*  
  - 3e version 1699 (récupérée par Josselin)  
    - *\> Echéance    ?*

- Travail avec la stagiaire : principes de régularisation (2 semaines) \- semaines du 18 mai et du 25 mai (Edgar maître de stage ?)

