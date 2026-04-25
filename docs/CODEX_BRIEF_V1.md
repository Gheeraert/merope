# Brief Codex — V1

## Mission

Construire la V1 d’un générateur statique académique avec interface graphique locale.

Chaîne obligatoire :

**Google Docs → Markdown → XML-TEI → HTML**

## Ce que Codex doit faire
- créer l’arborescence prévue
- implémenter les modèles de configuration JSON
- charger / sauvegarder la config
- charger les contenus Markdown
- normaliser les exports Google Docs
- appeler Pandoc pour générer la TEI
- post-traiter la TEI
- transformer la TEI en HTML via XSLT
- construire le site statique
- fournir une interface Tkinter simple
- écrire les tests

## Ce que Codex ne doit pas faire
- élargir le périmètre sans demande explicite
- remplacer Pandoc par un parseur Markdown maison
- déplacer de la logique métier dans les widgets Tkinter
- inventer un schéma JSON différent
- introduire un CMS ou un back-office web
- refondre plusieurs modules à la fois sans nécessité

## Contraintes techniques
- Python 3.11+
- Tkinter pour la V1
- Pandoc comme brique de conversion
- XSLT pour TEI → HTML
- pytest pour les tests
- configuration JSON validée strictement
- front matter YAML obligatoire dans chaque Markdown publié (`title`, `slug`, `type`, et `date` pour `post`)

## Style de code attendu
- fonctions courtes
- responsabilités nettes
- modules parlants
- dataclasses ou modèles explicites
- commentaires utiles
- tests ajoutés pour chaque évolution

## Ordre recommandé
1. config JSON
2. chargement Markdown
3. normalisation
4. Pandoc → TEI
5. TEI → HTML
6. build statique
7. interface graphique
8. tests end-to-end

## Fichiers de référence à lire d’abord
- `docs/CAHIER_DES_CHARGES_V1.md`
- `docs/SPEC_TEI_V1.md`
- `docs/SPEC_JSON_CONFIG_V1.md`
- `docs/SPEC_UI_V1.md`
- `docs/TABLE_CORRESPONDANCE_MD_TEI_HTML.md`
- `docs/ARCHITECTURE_PROJET.md`
