# Spécification de l’interface graphique V1

## Technologie
Tkinter.

## Principe
L’interface est un outil local de préparation et de génération.  
Elle n’est pas un CMS.

## Organisation recommandée en onglets

1. Site
2. Bannière
3. Chemins
4. Contenus
5. Accueil
6. Blog
7. Menu supérieur
8. Menu latéral
9. Rendu
10. Médias
11. Notes
12. Footer
13. Génération

## Fonctions minimales

### Barre principale
- Nouveau projet
- Charger une configuration
- Enregistrer la configuration
- Générer le site
- Ouvrir le dossier de sortie

### Onglet `Site`
- titre
- sous-titre
- langue
- URL de base
- auteur
- description

### Onglet `Bannière`
- activer / désactiver
- choisir image
- lien
- alt
- hauteur
- afficher ou non le titre sur l’image

### Onglet `Menu supérieur`
Liste ordonnée avec :
- ajouter
- modifier
- supprimer
- monter
- descendre

### Onglet `Menu latéral`
Sections + sous-entrées, un seul niveau de profondeur.

### Onglet `Médias`
- stratégie de récupération
- dossier images
- lightbox
- regroupement des figures

### Onglet `Notes`
- activer les notes marginales
- activer les notes complètes
- longueur de l’amorce
- emplacement des notes finales

### Onglet `Génération`
- messages
- erreurs de validation
- rapport de génération

## Validations attendues
- chemins obligatoires
- JSON valide
- bannière existante si activée
- Pandoc détectable
- conflits de slugs signalés
- fichiers Markdown manquants signalés
