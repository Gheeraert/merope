# Compiler un exécutable Windows (Nuitka)

Ce document décrit la recette pour produire un `.exe` autonome de MEROPE
(`bloggen`), via [Nuitka](https://nuitka.net/). Le script correspondant est
`scripts/build_exe.ps1`.

## Point d'entrée choisi

Le build compile `src/bloggen/cli.py` (`bloggen.cli:main`, déjà exposé comme
script console dans `pyproject.toml`). Un seul exécutable couvre donc :

- `bloggen.exe build <config.json>` — génération headless du site, pour un
  usage CI/script planifié ;
- `bloggen.exe gui` — lance l'éditeur Tkinter (`bloggen.ui.main_window`).

L'éditeur Qt expérimental (`bloggen.ui.qt_editor`, extra `qt_editor`) n'est
**pas** inclus : il dépend de PySide6, vit sur la branche `pyside` en
parallèle du Tkinter, et personne ne l'importe depuis le CLI (voir
`[[content_editor_tkinter_decision]]` en mémoire — à packager séparément si
besoin plus tard, une fois stabilisé).

## Pourquoi `--include-data-dir`

Le code résout ses ressources (CSS, JS, polices, scripts Lua Pandoc, XSLT,
schéma RelaxNG commons-publishing) par un chemin relatif à `__file__`, pas
via `importlib.resources` :

- `build/assets.py::copy_builtin_resources`
- `render/xslt_runner.py`
- `tei/pandoc_converter.py`
- `tei/commons_publishing.py`

Nuitka ne suit pas ces chemins comme il le fait pour les imports Python : le
dossier `src/bloggen/resources/` doit donc être copié explicitement dans le
build (`--include-data-dir=src\bloggen\resources=bloggen/resources`), pour
atterrir au même endroit relatif que dans le paquet source.

## Dépendance externe : Pandoc

`tei/pandoc_converter.py` invoque le binaire `pandoc` via `subprocess`
(commande `"pandoc"` par défaut, cherchée dans le `PATH`). Nuitka ne compile
que du Python : Pandoc reste un exécutable séparé à fournir.

Deux options :

1. **Pandoc installé sur la machine cible**, disponible dans le `PATH` —
   rien à faire côté packaging.
2. **Pandoc embarqué à côté de l'exe** — utiliser `-PandocDir` du script
   pour copier `pandoc.exe` (et ses DLL éventuelles) dans le dossier de
   sortie. Fonctionne uniquement avec un build `--standalone` (dossier),
   ou si le dossier onefile extrait expose le binaire sur le `PATH` du
   process (voir note onefile ci-dessous).

## Prérequis

```powershell
pip install nuitka ordered-set zstandard
```

Un compilateur C est nécessaire. Sur Windows, Nuitka peut télécharger et
utiliser automatiquement MinGW64 (`--assume-yes-for-downloads`, déjà dans le
script), ou utiliser MSVC si Visual Studio Build Tools est installé.

## Utilisation

```powershell
# Build onefile (par défaut), sortie dans .\dist
.\scripts\build_exe.ps1

# Build en dossier standalone (démarrage plus rapide, plus facile à inspecter)
.\scripts\build_exe.ps1 -OneFile:$false

# Avec Pandoc embarqué
.\scripts\build_exe.ps1 -OneFile:$false -PandocDir "C:\Program Files\Pandoc"
```

## Limites connues

- **Onefile** décompresse l'application dans un dossier temporaire à chaque
  lancement (plus lent au démarrage, et complique l'ajout de Pandoc à côté
  de l'exe). Pour un usage fréquent ou pour embarquer Pandoc, préférer
  `-OneFile:$false` (dossier standalone), qu'on peut alors zipper/distribuer
  tel quel.
- **Antivirus** : les exécutables onefile générés par Nuitka/PyInstaller
  déclenchent parfois des faux positifs à la première diffusion. Signer le
  binaire ou soumettre à Microsoft Defender si besoin.
- Ce script ne fait aucune vérification de licence/signature de code ; à
  ajouter séparément si le binaire doit être distribué publiquement.

## Vérification après build

```powershell
& '.\dist\bloggen.exe' gui
& '.\dist\bloggen.exe' build .\examples\<config>.json
```
