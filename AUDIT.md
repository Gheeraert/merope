# Audit MÉROPE — 2026-09-19

Synthèse d'un audit en 5 volets : config/build/CLI, pipeline markdown/contenu, pipeline TEI/rendu HTML, UI Qt/Tkinter, sécurité du module de publication FTP.

## 🔴 Critique — sécurité réseau FTP

1. **FTP en clair autorisé par défaut** — `ftp_publisher.py:118` bascule silencieusement vers `ftplib.FTP` (non chiffré) si `use_tls=False`. Rien n'empêche ni n'avertit fortement l'utilisateur de publier identifiants + contenu en clair sur un réseau non maîtrisé. → Forcer FTPS par défaut, exiger une confirmation explicite pour désactiver.
2. **Pas de vérification de certificat même en FTPS** — `ftp_publisher.py:118-125` utilise `ftplib.FTP_TLS` sans `context=ssl.create_default_context()`. Le comportement par défaut de la stdlib n'active **pas** la vérification de certificat : un MITM actif avec un certificat quelconque passerait silencieusement. → Passer un `SSLContext` explicite avec vérification.

## 🟠 Bloquant / majeur — fonctionnel et robustesse

3. **Injection de contenu via collage HTML** — `html_paste_import.py` ne traite pas `<script>`/`<style>`/`<noscript>` comme des conteneurs opaques : leur contenu brut (JS/CSS) est inséré comme texte visible dans l'article. Coller une page web quelconque peut publier du code en clair. → Ignorer explicitement le contenu de ces balises.
4. **Schémas d'URL non filtrés sur les liens collés** (`href` d'un `<a>`) — contrairement aux images (SSRF, magic-bytes, SVG bloqué, tout est vérifié), un lien `javascript:`/`data:` collé traverse tel quel jusqu'au Markdown, et potentiellement jusqu'au HTML final si le pipeline TEI/XSLT ne revalide pas les schémas de lien du corps de texte (à vérifier côté rendu).
5. **Notes orphelines à identifiant alphabétique** font planter (`ValueError`) le renumérotage — `content/footnotes.py:125` trie avec `key=int`, alors que Pandoc/l'import acceptent des IDs non numériques (`[^ma-note]`). Un billet avec une telle note ne peut plus être sauvegardé.
6. **Aucun timeout sur les appels subprocess** (`utils/subprocesses.py:43`) — un pandoc qui bloque (entrée malformée, attente stdin) fige le build indéfiniment, sans échappatoire, y compris en CI headless.
7. **Le vrai validateur TEI Commons Publishing (RelaxNG+Schematron) n'est pas bloquant par défaut** — `tei/validator.py` (nom trompeur) ne fait qu'une vérification de structure minimale et *est* bloquant ; le vrai contrôle de conformité au schéma (`commons_publishing.validate_commons_publishing_bytes`) tourne en fin de build comme simple diagnostic (`fail_on_invalid_commons_publishing=False`). Un document non conforme au profil publie quand même.
8. **Sous-processus Qt non nettoyé à la fermeture de Mérope** — `main_window.py` n'enregistre pas de `WM_DELETE_WINDOW`, contrairement à d'autres fenêtres du projet. Fermer l'appli pendant une session Qt active laisse un processus orphelin et risque de pertes de modifications côté éditeur Qt.
9. **`slugify_mode` n'a aucun effet réel pour le français** — l'option est exposée dans l'UI/config mais toutes les valeurs suppriment les accents (« Café à Paris » → `caf-paris` dans tous les modes). Réglage fantôme.
10. **Table Markdown à cellules irrégulières fait planter toute la sérialisation** (`rich_text_export.py:81-95`) — un `ValueError` non rattrapé peut interrompre l'auto-sauvegarde et perdre l'édition en cours.
11. **Écritures TEI/redirections après le swap atomique du build**, hors de la protection transactionnelle (`site_builder.py:289-317`) — déjà documenté comme compromis assumé dans le code, mais à confirmer que c'est acceptable pour l'usage visé (un échec disque à ce stade publie un site en avance sur son propre rapport d'échec).

## 🟡 Mineur

- Mot de passe FTP stocké en clair dans `site.json` si le trousseau OS échoue (fallback documenté et averti, mais sans garantie que `site.json` est exclu de git).
- DNS rebinding possible sur le téléchargement d'images distantes collées (double résolution DNS non épinglée) — SSRF partiel malgré des protections par ailleurs solides.
- `MediaHandlingConfig.strategy` réglable dans l'UI mais jamais lu par le pipeline de build (illusion de configuration).
- `validator.py` (config) omet `top_banner`/`ftp` des clés racine requises ; plusieurs champs texte libre (`slugify_mode`, `lightbox_engine`, `notes_rendering.mode`) ne sont validés contre aucune liste de valeurs.
- `xml.etree.ElementTree` non durci dans `tei/validator.py`/`postprocess.py`, incohérent avec le parsing XML durci utilisé ailleurs (risque DoS faible type "billion laughs").
- Fichier de récupération de crash partagé Tk/Qt sans verrouillage anti-concurrence ; `editor_recovery.clear_draft` avale les erreurs silencieusement.
- Modules `utils/fs.py`, `logging.py`, `text.py` vides ("reserved for a future pass") malgré leur présence dans l'arborescence — source de confusion.
- Duplication mineure : fonctions `_guard_top_banner_asset`/`_guard_banner_asset` quasi identiques, import dupliqué dans `site_builder.py`, logique de copie d'image dupliquée entre `image_service.py` et `html_paste_import.py`.
- `front_matter.py` : parseur YAML "plat" minimal non documenté comme tel — une syntaxe YAML standard (listes multi-lignes) échoue avec un message peu clair.

## Points positifs à noter

Protection XXE réelle et bien conçue dans `xslt_runner.py`/`commons_publishing.py` (`access_control=DENY_ALL`, entités désactivées). Protocole IPC Qt↔Tk robuste (JSON Lines, pas de pickle/eval, gestion des générations de process). Garde-fous path-traversal soignés et centralisés dans `site_builder.py` et `ftp_publisher.py` (suppression distante jamais automatique, confirmation utilisateur obligatoire). Écriture atomique de fichiers correcte (tempfile + fsync + rename). Round-trip du modèle rich-text fidèle avec repli explicite en verbatim.

---

**Priorités recommandées** : (1) forcer FTPS + vérification de certificat, (2) neutraliser `<script>/<style>` au collage HTML, (3) ajouter un timeout aux appels pandoc, (4) corriger le tri des notes orphelines, (5) nettoyer le sous-processus Qt à la fermeture.
</content>
