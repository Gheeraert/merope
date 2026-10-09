<#
.SYNOPSIS
    Compile MEROPE (bloggen) en un exécutable Windows autonome avec Nuitka.

.DESCRIPTION
    Produit un .exe "onefile" à partir du point d'entrée `bloggen.cli:main`,
    qui expose à la fois `bloggen build <config.json>` (génération headless)
    et `bloggen gui` (éditeur Tkinter). Les ressources packagées dans
    src/bloggen/resources/ (CSS, JS, polices, scripts Lua Pandoc, XSLT,
    schéma RelaxNG) sont résolues par le code via chemins relatifs à
    __file__ (voir build/assets.py, render/xslt_runner.py,
    tei/pandoc_converter.py, tei/commons_publishing.py) : elles doivent donc
    être embarquées explicitement, Nuitka ne les suit pas comme des imports.

    Pandoc reste un binaire externe invoqué via subprocess (PATH, ou
    -PandocDir pour le copier à côté de l'exécutable). Ce script ne
    l'installe pas.

    L'éditeur Qt expérimental (bloggen.ui.qt_editor, PySide6) est embarqué
    via --enable-plugin=pyside6. Il tourne dans un sous-processus distinct,
    relancé par qt_editor_launcher.build_qt_editor_command : comme l'exe
    compilé n'est pas un interpréteur générique, ce sous-processus ne peut
    pas être invoqué avec "-m bloggen.ui.qt_editor" — il réutilise l'exe
    lui-même avec la sous-commande interne "_qt-editor-ipc" (voir cli.py).

.PARAMETER OutputDir
    Dossier de sortie du build (par défaut: .\dist).

.PARAMETER OneFile
    Produit un exécutable unique (onefile) plutôt qu'un dossier standalone.
    Activé par défaut ; passer -OneFile:$false pour un dossier standalone
    (démarrage plus rapide, plus facile à déboguer).

.PARAMETER PandocDir
    Dossier contenant pandoc.exe (et ses DLL) à copier à côté de
    l'exécutable compilé, pour ne pas dépendre du PATH de la machine cible.

.EXAMPLE
    .\scripts\build_exe.ps1

.EXAMPLE
    .\scripts\build_exe.ps1 -OneFile:$false -PandocDir "C:\Program Files\Pandoc"
#>

param(
    [string]$OutputDir = "dist",
    [bool]$OneFile = $true,
    [string]$PandocDir = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "== Vérification de l'environnement ==" -ForegroundColor Cyan

python -c "import nuitka" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Nuitka n'est pas installé dans cet environnement Python." -ForegroundColor Yellow
    Write-Host "Installation: pip install nuitka ordered-set zstandard" -ForegroundColor Yellow
    exit 1
}

# Un compilateur C est requis par Nuitka (MSVC via Build Tools, ou MinGW64
# que Nuitka peut télécharger seul avec --assume-yes-for-downloads).

$EntryPoint = "src\bloggen\cli.py"
$ResourcesSrc = "src\bloggen\resources"

if (-not (Test-Path $EntryPoint)) {
    throw "Point d'entrée introuvable: $EntryPoint"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$NuitkaArgs = @(
    "-m", "nuitka",
    "--standalone",
    "--assume-yes-for-downloads",
    "--enable-plugin=tk-inter",
    "--enable-plugin=pyside6",
    "--include-package=lxml",
    "--include-package=PIL",
    "--include-data-dir=$ResourcesSrc=bloggen/resources",
    "--output-dir=$OutputDir",
    "--output-filename=bloggen.exe",
    "--windows-console-mode=force",
    "--company-name=MEROPE",
    "--product-name=MEROPE",
    "--file-version=0.1.0.0",
    "--product-version=0.1.0.0"
)

if ($OneFile) {
    $NuitkaArgs += "--onefile"
}

$NuitkaArgs += $EntryPoint

Write-Host "== Compilation avec Nuitka ==" -ForegroundColor Cyan
Write-Host "python $($NuitkaArgs -join ' ')"
python @NuitkaArgs

if ($LASTEXITCODE -ne 0) {
    throw "La compilation Nuitka a échoué (code $LASTEXITCODE)."
}

$BuildDir = if ($OneFile) { $OutputDir } else { Join-Path $OutputDir "cli.dist" }

if ($PandocDir -ne "") {
    if (-not (Test-Path $PandocDir)) {
        throw "PandocDir introuvable: $PandocDir"
    }
    Write-Host "== Copie de Pandoc à côté de l'exécutable ==" -ForegroundColor Cyan
    Copy-Item -Path (Join-Path $PandocDir "*") -Destination $BuildDir -Recurse -Force
}

Write-Host ""
Write-Host "Build terminé. Résultat dans: $BuildDir" -ForegroundColor Green
Write-Host "Test rapide:  & '$BuildDir\bloggen.exe' gui" -ForegroundColor Green
Write-Host "            & '$BuildDir\bloggen.exe' build chemin\vers\config.json" -ForegroundColor Green
