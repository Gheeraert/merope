# Contrats de conservation et de sécurité des données

Ce document répond à une question simple : dans quelles situations MÉROPE transforme-t-il, refuse-t-il ou préserve-t-il les données qu’on lui confie ? Il complète `docs/GUIDE_UI.md` (usage courant) et `docs/SPEC_JSON_CONFIG_V1.md` / `docs/ARCHITECTURE_PROJET.md` (détail technique).

## 1. Principe général

MÉROPE préfère, dans cet ordre :

```text
préserver > refuser explicitement > transformer volontairement
```

et évite autant que possible la suppression silencieuse. Quand une construction ne peut pas être représentée fidèlement, MÉROPE la conserve telle quelle (mode source/verbatim) ou refuse explicitement l’opération, plutôt que de deviner et de risquer une perte non signalée.

## 2. Markdown

Le modèle interne des éditeurs graphiques repose sur deux structures : `Block` (paragraphe, titre, citation, liste, tableau, image, note, etc.) et `InlineRun` (portions de texte avec gras, italique, souligné, barré, exposant, lien, appel de note).

Ce modèle ne couvre qu’un **sous-ensemble structuré** du Markdown : celui que les éditeurs de MÉROPE produisent et reconnaissent eux-mêmes. Toute construction Markdown que l’importeur ne reconnaît pas avec confiance devient un bloc `VERBATIM`, qui reproduit le texte source tel quel. `VERBATIM` existe précisément pour éviter de deviner une structure incertaine ou de perdre silencieusement une portion de contenu — c’est un filet de sécurité, pas une erreur.

Un tableau dont les lignes ont un nombre de cellules différent n’est plus rejeté : les lignes plus courtes sont complétées avec des cellules vides jusqu’à la largeur de la ligne la plus large, sans jamais perdre une cellule existante.

Important : ce modèle `Block`/`InlineRun` et son importeur ne remplacent en rien **Pandoc**, qui reste l’unique moteur de conversion Markdown → TEI pour la chaîne de publication. L’éditeur WYSIWYG est une commodité de saisie ; il n’intervient jamais dans le pipeline de génération du site.

## 3. Front matter

Le parseur de front matter n’est pas un parseur YAML générique : c’est un sous-ensemble volontairement limité (paires `clé: "valeur"` sur une ligne, sans listes ni structures imbriquées). Toute syntaxe non reconnue échoue explicitement (erreur de type `FrontMatterParseError`) plutôt que de corrompre silencieusement un document.

À la sauvegarde, le front matter est réécrit sous une forme canonique (guillemets doubles systématiques, échappement cohérent). Le contenu textuel est fidèlement conservé, mais la forme exacte d’origine (espacement, choix de guillemets) n’est **pas garantie byte-for-byte**.

## 4. Configuration JSON

Voir `docs/SPEC_JSON_CONFIG_V1.md` pour le détail complet. En résumé : une clé JSON inconnue de la version courante de MÉROPE est préservée lors d’un cycle chargement → modification → sauvegarde, y compris dans les objets de menu, avec priorité aux champs qui deviennent connus dans une version ultérieure. Seul le mot de passe FTP fait exception : il est systématiquement retiré du JSON écrit sur disque, une règle de sécurité qui prime sur le principe de préservation.

## 5. Sauvegarde des contenus

Avant d’écraser un fichier Markdown déjà enregistré, MÉROPE en archive une copie horodatée dans le dossier `.versions` voisin du contenu. L’écriture elle-même est atomique (fichier temporaire voisin, puis remplacement final). La purge des versions les plus anciennes n’a lieu qu’après confirmation explicite de l’utilisateur ; MÉROPE ne supprime jamais de version de sa propre initiative.

## 6. Recovery

Les éditeurs Tkinter et Qt écrivent périodiquement un brouillon de secours dans `.merope-recovery/draft.json` (toutes les 30 secondes si le document a été modifié). Ce brouillon sert uniquement à proposer une restauration après un incident (plantage, fermeture accidentelle) ; il ne remplace pas une sauvegarde volontaire et n’alimente pas `.versions`.

Dette connue : les éditeurs Tk et Qt partagent le même fichier de brouillon. Si les deux sont ouverts simultanément sur le même projet et que l’un des deux plante, MÉROPE peut proposer au redémarrage le brouillon écrit par l’autre éditeur plutôt que le sien. L’écriture reste atomique — aucune corruption du fichier n’est possible — mais le brouillon proposé peut être le mauvais. Aucune perte permanente n’a été constatée dans ce scénario.

## 7. Transformations volontaires

MÉROPE applique certaines transformations de façon systématique et documentée. Il s’agit de **normalisations volontaires**, pas de pertes silencieuses :

- **renumérotation canonique des notes** : à l’enregistrement, les notes sont renumérotées selon leur ordre d’apparition dans le texte (les notes orphelines sont conservées, triées après les notes appelées) ;
- **tableau irrégulier** : les lignes trop courtes sont complétées avec des cellules vides, sans perte de cellule existante ;
- **normalisations typographiques** : guillemets français, espaces insécables, ligatures reconnues, ordinaux de siècles — appliquées à la frappe ou via une commande explicite, jamais de façon rétroactive invisible sur tout un document ;
- **suppression d’une destination de lien dangereuse** : un schéma d’URL non autorisé (`javascript:`, `data:`, etc.) est retiré du lien à la publication ; le texte visible du lien, lui, est conservé ;
- **réécriture canonique du front matter et du JSON de configuration** : la forme est normalisée à la sauvegarde (voir sections 3 et 4), sans garantie byte-for-byte sur la mise en forme d’origine.

## 8. Sécurité

- **Schémas de liens autorisés** : `http`, `https`, `mailto`, `tel`. Tout autre schéma est refusé à la publication (destination retirée, texte conservé). Les liens sans schéma (relatifs, ancres, `//hôte`) sont acceptés.
- **HTML collé** : le contenu collé depuis Word ou Google Docs est traité comme opaque jusqu’à son import — les balises non reconnues (`<script>`, `<style>`, etc.) sont des conteneurs ignorés dans leur intégralité, jamais affichés comme texte brut.
- **TEI** : le TEI est analysé avec un parseur XML durci — aucun accès réseau, aucune DTD chargée, tout document déclarant un `DOCTYPE` est rejeté explicitement. Cette protection vise en particulier la résolution d’entités XML (XXE).
- **Appels externes** : les appels à Pandoc et aux autres commandes externes sont bornés par un timeout (120 secondes par défaut), converti en échec de build propre plutôt qu’en blocage indéfini.
- **FTP/FTPS et secrets** : FTPS et le mode passif sont activés par défaut ; une publication en FTP non chiffré exige une confirmation explicite. Le mot de passe est stocké via le gestionnaire d’identifiants du système et n’est jamais écrit en clair dans `site.json` (voir section 4).

Ce document n’a pas vocation à être un audit de sécurité exhaustif ; voir `AUDIT.md` pour l’historique des vérifications menées.
