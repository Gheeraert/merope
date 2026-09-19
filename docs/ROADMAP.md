# Roadmap

## Livré et stabilisé

- configuration JSON avec préservation lossless des clés inconnues, écriture atomique ;
- interface Tkinter complète, menus éditables (supérieur + latéral à 3 niveaux, numérotation automatique optionnelle) ;
- bandeau institutionnel et bannière éditoriale ;
- TEI comme pivot, transformation XSLT → HTML ;
- images avec lightbox, notes finales en bas d’article (ancre de défilement doux vers l’appel) ;
- CLI headless (`bloggen build --config ...`) ;
- RSS (`feed.xml`), sitemap (`sitemap.xml` avec `lastmod`), `robots.txt`, méta SEO (Open Graph, Twitter Card, JSON-LD BlogPosting/WebSite) ;
- surcharge de thème (CSS/JS) et de gabarits HTML par projet ;
- éditeur de contenu WYSIWYG intégré (Tkinter), import Markdown et copier-coller nettoyé depuis Word/Google Docs ;
- exposants, conversion automatique des ordinaux de siècle, typographie française (guillemets, espaces insécables, ligatures) ;
- recherche plein texte statique côté client (index JSON généré au build) ;
- alignement de paragraphe (gauche/centré/droite/justifié) reporté sur le site généré ;
- sélecteur de page/billet pour les liens de menu internes ; liens externes intégrés en iframe conservant menus et bannière ;
- thème du site généré inspiré de Twenty Fourteen ;
- raccourci `((note))` (convention Hypothèses), converti en note Pandoc à la normalisation d’aperçu/génération ;
- renumérotation automatique des notes à l’enregistrement selon leur ordre d’apparition ;
- copie TEI complète conservée à côté de chaque source Markdown, indépendamment du réglage « Conserver TEI » ;
- conversion en un clic d’une page en billet (ou l’inverse) ;
- aperçu local du site généré (serveur HTTP intégré) proposé depuis le rapport de génération ;
- pagination réelle de l’archive des billets ;
- validation diagnostique du TEI généré contre le profil TEI Commons Publishing (RelaxNG + Schematron), option pour la rendre bloquante ;
- versionnement des contenus (`.versions`) et récupération après incident (`.merope-recovery/draft.json`) ;
- durcissement sécurité : timeout des sous-processus externes, parseur XML anti-XXE pour le TEI, allowlist de schémas de liens, mot de passe FTP jamais écrit en clair dans `site.json` — détail dans `AUDIT.md`.

## Migration Qt

Un éditeur de contenu Qt coexiste avec l’éditeur Tkinter historique, en phase expérimentale. Statut détaillé, architecture et parité fonctionnelle : `docs/QT_MIGRATION.md`. Tkinter reste l’éditeur principal et le repli officiel ; aucune bascule n’est planifiée à ce stade.

## Dette connue

- **Recovery multi-éditeur sans verrou** : si Tk et Qt sont ouverts simultanément sur le même projet et que l’un des deux plante, le brouillon de récupération proposé au redémarrage peut être celui écrit par l’autre éditeur. Aucune perte permanente constatée — priorité basse (détail dans `AUDIT.md` et `docs/QT_MIGRATION.md`).
- **`content.slugify_mode` sans validation d’enum stricte** : le champ a un effet réel sur la génération de slug, mais une valeur incorrecte n’est pas rejetée par le validateur — comportement de repli sûr, mais qui ne fait pas ce que l’utilisateur croit configurer. Priorité basse.

## V1.1

- amélioration responsive ;
- notes marginales (désactivées depuis V1 : ne tenaient pas de façon fiable à côté du texte selon la largeur de l’écran, voir `render/margin_notes.py`) ;
- meilleure gestion des images issues de Google Docs ;
- recette humaine de l’éditeur Qt (notamment collage Word/Google Docs) et inventaire des écarts observés avec Tkinter.

## V2

- enrichissements TEI supplémentaires ;
- meilleure automatisation des médias.
