# Audit MÉROPE — historique et traitement

Audit initial en 5 volets (config/build/CLI, pipeline markdown/contenu,
pipeline TEI/rendu HTML, UI Qt/Tkinter, sécurité du module de publication
FTP), suivi d'une série de passes correctives puis d'un contre-audit de
synthèse. Ce document consigne chaque point soulevé et la manière dont il
a été traité — ce n'est plus une liste de tâches en attente.

## Sécurité réseau FTP — corrigé

1. **FTP en clair** — `ftp_publisher.py` basculait silencieusement vers
   `ftplib.FTP` non chiffré si `use_tls=False`, sans avertissement.
   Corrigé : un dialogue de confirmation bloquant (`_confirm_plain_ftp`)
   est désormais obligatoire avant toute publication non chiffrée.
2. **Absence de vérification de certificat en FTPS** —
   `ftplib.FTP_TLS` était instancié sans `SSLContext` explicite, donc sans
   vérification de certificat par défaut. Corrigé :
   `ssl.create_default_context()` est passé systématiquement
   (`ftp_publisher.py:_make_ftp`).

## Fonctionnel et robustesse — traité

3. **Collage HTML : `<script>`/`<style>`/`<noscript>`/`<template>`
   affichés comme texte** — corrigé. Ces balises sont désormais des
   conteneurs réellement opaques (contenu et imbrications ignorés, y
   compris en cas de fermeture malformée) dans `html_paste_import.py`.
4. **Schémas d'URL non filtrés sur les liens collés** (`javascript:`,
   `data:`, `vbscript:`...) — corrigé à toutes les frontières
   concernées : collage HTML, import Markdown structuré, export
   `InlineRun`, et jusqu'à la TEI publiée (`link_safety.py`,
   `pandoc_converter.py`/`postprocess.py`). Vérifié par sonde directe :
   Pandoc lui-même supprime le HTML brut injecté dans du Markdown avant
   la conversion TEI, sans qu'aucun correctif supplémentaire soit
   nécessaire de ce côté.
5. **Notes orphelines à identifiant alphabétique faisaient planter le
   renumérotage** (`ValueError` sur `key=int`) — corrigé :
   `content/footnotes.py` sépare désormais les identifiants numériques et
   non numériques sans jamais lever d'exception ; l'éditeur Qt accepte
   également ces identifiants jusqu'à la sauvegarde, qui les canonise en
   `1, 2, 3...`.
6. **Aucun timeout sur les appels subprocess** — corrigé : un délai de
   120 s par défaut entoure tout appel externe (`utils/subprocesses.py`),
   converti en échec de build propre (`CommandTimeoutError`) plutôt qu'un
   blocage indéfini.
7. **Validation Commons Publishing non bloquante par défaut** — examiné
   et retenu comme choix de conception assumé, pas un bug : la
   validation est active par défaut, produit un avertissement documenté
   (`docs/REFERENCE_CONFIGURATION.md`) en cas de non-conformité, et
   l'option pour la rendre bloquante (`fail_on_invalid_commons_publishing`)
   est exposée dans l'UI. Le compromis est justifié en commentaire :
   certaines constructions Markdown légitimes (blocs de code, règles
   horizontales) produisent encore du TEI hors profil.
8. **Sous-processus Qt non nettoyé à la fermeture de Mérope** — examiné
   et retenu comme choix de conception assumé : l'éditeur Qt possède son
   propre `closeEvent`, sa propre confirmation de modifications non
   enregistrées et son propre autosave/recovery indépendants
   (`qt_editor/window.py`, `qt_editor/recovery.py`). Le tuer
   automatiquement à la fermeture de Tk risquerait une perte de données
   sans bénéfice net.
9. **`slugify_mode` sans effet réel** — l'analyse initiale était
   inexacte : le mode `"ascii"` a bien un effet réel (translittération
   des accents). Reste toutefois sans validation d'enum stricte —
   consigné comme dette mineure différée ci-dessous.
10. **Tableau Markdown irrégulier faisait planter la sérialisation** —
    corrigé : `rich_text_export.py` complète désormais les lignes
    manquantes avec des cellules vides plutôt que de lever `ValueError`,
    sans jamais perdre de cellule existante.
11. **Écritures TEI/redirections hors protection transactionnelle** —
    vérifié : le swap atomique du build regroupe bien site + TEI comme
    une seule unité avec rollback, et les sidecars/l'historique de
    redirections ne sont écrits qu'après un build confirmé réussi
    (`site_builder.py`). Compromis déjà correctement implémenté.

## Points mineurs — traités ou clarifiés

- **Mot de passe FTP en clair** — corrigé : persistance exclusivement via
  le trousseau de clés du système d'exploitation, jamais écrit dans
  `site.json` (dégradation propre si le trousseau est indisponible).
- **DNS rebinding sur les images distantes collées** — hors périmètre
  des passes correctives ; protections SSRF par ailleurs solides déjà en
  place (résolution d'hôte vérifiée, redirections refusées).
- **`MediaHandlingConfig.strategy` réglable mais jamais lu** — clarifié :
  le champ n'est en réalité jamais exposé comme widget interactif dans
  l'UI (commentaire explicite "round-trip only" dans le code) ; pas une
  configuration trompeuse.
- **Validation de config incomplète pour certains champs texte libre**
  (`slugify_mode`, `lightbox_engine`, `notes_rendering.mode`) — pour
  `notes_rendering.mode`, champ également jamais exposé dans l'UI
  (round-trip only). `slugify_mode` reste sans validation d'enum —
  consigné ci-dessous.
- **`xml.etree.ElementTree` non durci dans `tei/validator.py`/
  `postprocess.py`** — corrigé : `bloggen.tei.xml_safety` durcit les 7
  points d'entrée (aucun accès réseau, aucune DTD, tout DOCTYPE rejeté),
  cohérent avec la politique déjà appliquée dans `xslt_runner.py`/
  `commons_publishing.py`. Confirmé par sonde directe : la résolution
  d'entité interne par le parseur stdlib était un risque réel, pas
  seulement théorique.
- **Fichier de récupération de crash partagé Tk/Qt sans verrouillage** —
  examiné : l'écriture reste atomique (aucune corruption possible) ;
  seul un scénario rare (Tk et Qt ouverts simultanément sur le même
  projet, l'un des deux crashant) peut proposer le mauvais brouillon à
  la restauration, sans jamais de perte permanente. Consigné comme dette
  différée ci-dessous.
- **Modules réservés vides** (`utils/fs.py`, `logging.py`, `text.py`,
  `tei/notes.py`, `ui/bindings.py`) — clarifié : réservation
  intentionnelle et documentée ("Reserved for a future development
  pass"), pas du code mort.
- **Duplication mineure** (`_guard_top_banner_asset`/`_guard_banner_asset`,
  logique Tk/Qt des notes) — examinée : aucune divergence fonctionnelle
  constatée entre les implémentations dupliquées ; relève de la
  maintenance non urgente, pas d'un bug.
- **`front_matter.py` : sous-ensemble YAML minimal non documenté comme
  tel** — clarifié : le sous-ensemble est volontaire, toute syntaxe non
  reconnue échoue explicitement (`FrontMatterParseError`) plutôt que de
  corrompre silencieusement un document.

## Points positifs à noter

Protection XXE réelle et bien conçue dans `xslt_runner.py`/
`commons_publishing.py` (`access_control=DENY_ALL`, entités désactivées),
désormais étendue à `validator.py`/`postprocess.py` via
`bloggen.tei.xml_safety`. Protocole IPC Qt↔Tk robuste (JSON Lines, pas de
pickle/eval, gestion des générations de process). Garde-fous
path-traversal soignés et centralisés dans `site_builder.py` et
`ftp_publisher.py` (suppression distante jamais automatique, confirmation
utilisateur obligatoire). Écriture atomique de fichiers correcte
(tempfile + fsync + rename), y compris pour le swap transactionnel du
build. Round-trip du modèle rich-text fidèle avec repli explicite en
verbatim, y compris pour des tableaux irréguliers ou des identifiants de
note non numériques.

---

## Dette différée

Deux points mineurs restent sciemment différés, sans urgence :

- **Recovery multi-éditeur sans verrou** (`editor_recovery.py`) — si Tk
  et Qt sont ouverts simultanément sur le même projet et que l'un des
  deux crashe, le prompt de restauration peut proposer le brouillon
  écrit en dernier par l'autre éditeur plutôt que le sien. Aucune perte
  permanente constatée — priorité basse.
- **`slugify_mode` sans validation d'enum** — le champ a un effet réel
  sur la génération de slug, mais `config/validator.py` ne rejette
  aucune valeur incorrecte : une faute de frappe ne casse rien, mais ne
  fait pas non plus ce que l'utilisateur croit configurer. Comportement
  de repli sûr — priorité basse.
</content>
