"""Search-engine / service verification files published at the site root.

The output directory is disposable (a clean build deletes it), so these
files (e.g. Google Search Console's ``google123456789abcdef.html``) live in
the project instead, in ``<project_root>/root-files/``, and are copied
back to the root of the output directory on every build.

Files are opaque: copied byte for byte (``shutil.copy2``), never parsed,
re-encoded or renamed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shutil
from typing import Any, Iterable

ROOT_FILES_DIRNAME = "root-files"

# Always reserved, whether or not the matching generator is enabled: a
# verification file must never stand in for one of these.
RESERVED_OUTPUT_NAMES = frozenset(
    {"index.html", "robots.txt", "sitemap.xml", "feed.xml", "search-index.json"}
)

# Windows device names are reserved whatever the extension (CON.html too),
# checked on every platform so the same JSON is valid or invalid everywhere.
_WINDOWS_RESERVED_STEMS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"{device}{digit}" for device in ("COM", "LPT") for digit in "123456789\u00b9\u00b2\u00b3"}
)

_WINDOWS_FORBIDDEN_CHARS = set('<>:"/\\|?*')


class VerificationFileExistsError(FileExistsError):
    """The project already holds a different copy under that name."""


@dataclass(slots=True)
class VerificationCopyResult:
    copied: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check_verification_filename(name: Any) -> str | None:
    """None if ``name`` is a plain, safe file name; otherwise a French
    explanation. A bare name only: no directory, drive, traversal, or
    hidden/dot file."""
    if not isinstance(name, str):
        return f"nom de fichier invalide ({name!r}) : une chaîne est attendue."
    if not name.strip():
        return "nom de fichier vide."
    if name != name.strip() or name.endswith("."):
        return f"nom de fichier invalide ({name!r}) : espace ou point en début/fin."
    if name.startswith("."):
        return f"nom de fichier invalide ({name!r}) : les fichiers cachés sont refusés."
    if "/" in name or "\\" in name:
        return (
            f"nom de fichier invalide ({name!r}) : un simple nom de fichier est requis, "
            "sans dossier ni chemin."
        )
    if any(ord(c) < 32 for c in name) or (set(name) & _WINDOWS_FORBIDDEN_CHARS):
        return f"nom de fichier invalide ({name!r}) : caractères interdits."
    if name.split(".")[0].rstrip().upper() in _WINDOWS_RESERVED_STEMS:
        return f"nom de fichier invalide ({name!r}) : nom de périphérique réservé sous Windows."
    if Path(name).name != name or Path(name).is_absolute():
        return f"nom de fichier invalide ({name!r}) : un simple nom de fichier est requis."
    return None


def root_files_dir(project_root: Path) -> Path:
    return project_root / ROOT_FILES_DIRNAME


def _source_for(name: str, project_root: Path) -> Path:
    """Resolved source path, guaranteed to be a direct child of the
    project's root-files/ (also rejects a symlink leading elsewhere)."""
    base = root_files_dir(project_root).resolve()
    source = (base / name).resolve()
    if source.parent != base:
        raise ValueError(f"« {name} » sort du dossier {ROOT_FILES_DIRNAME}/.")
    return source


def import_verification_file(source: Path, project_root: Path, *, overwrite: bool = False) -> str:
    """Copy an externally chosen file into ``<project_root>/root-files/``
    (exact bytes, same name) and return its name. Never overwrites a
    different existing copy unless ``overwrite`` is True."""
    source = Path(source)
    name = source.name
    problem = check_verification_filename(name)
    if problem:
        raise ValueError(problem)
    if not source.is_file():
        raise FileNotFoundError(f"Fichier introuvable : {source}")

    destination = _source_for(name, project_root)
    if destination.exists():
        if destination.is_dir():
            raise ValueError(f"« {name} » existe déjà comme dossier dans {ROOT_FILES_DIRNAME}/.")
        if source.resolve() == destination:
            return name  # already the project's own copy
        if not overwrite:
            raise VerificationFileExistsError(name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return name


def delete_local_copy(name: str, project_root: Path) -> bool:
    """Delete ``root-files/<name>``; True if a file was removed. Only ever
    touches a direct child of the project's root-files/."""
    problem = check_verification_filename(name)
    if problem:
        raise ValueError(problem)
    target = _source_for(name, project_root)
    if target.is_file():
        target.unlink()
        return True
    return False


def copy_root_verification_files(
    names: Iterable[str],
    project_root: Path,
    output_root: Path,
    *,
    reserved: Iterable[Path] = (),
    fail_on_missing: bool = False,
) -> VerificationCopyResult:
    """Copy each configured verification file from ``root-files/`` to the
    root of ``output_root``.

    All names are validated first; nothing is copied unless every entry is
    acceptable (a build with any error is discarded anyway, and a
    non-cleaned output directory must not be left half-updated).

    ``reserved`` lists paths already produced by this build (pages,
    robots.txt, sitemap, feed, redirect stubs...); a verification file
    landing on one of them, on a fixed reserved name, or on a directory,
    is a blocking error — never "last one wins". A missing source is a
    warning, or an error when ``fail_on_missing`` (mirrors
    ``build.fail_on_missing_assets``).
    """
    result = VerificationCopyResult()
    output_root = Path(output_root)
    project_root = Path(project_root)
    reserved_keys = {_reserved_key(Path(p), output_root) for p in reserved}
    reserved_keys.update(RESERVED_OUTPUT_NAMES)
    reserved_folded = {k.casefold() for k in reserved_keys}

    plan: list[tuple[Path, Path]] = []
    seen: dict[str, str] = {}
    for name in names:
        problem = check_verification_filename(name)
        if problem:
            result.errors.append(f"Fichier de validation refusé : {problem}")
            continue
        key = name.casefold()
        if key in seen:
            if seen[key] != name:
                result.errors.append(
                    f"Fichiers de validation en conflit : « {seen[key]} » et « {name} » "
                    "ne diffèrent que par la casse."
                )
            continue
        seen[key] = name

        if key in reserved_folded:
            result.errors.append(
                f"Fichier de validation « {name} » : collision avec un fichier généré par MÉROPE "
                "(il n'est pas copié). Renommez-le ou retirez-le de la configuration."
            )
            continue
        destination = output_root / name
        if destination.is_dir():
            result.errors.append(
                f"Fichier de validation « {name} » : un dossier du même nom existe dans la sortie."
            )
            continue
        try:
            source = _source_for(name, project_root)
        except ValueError as exc:
            result.errors.append(f"Fichier de validation refusé : {exc}")
            continue
        if not source.is_file():
            message = (
                f"Fichier de validation « {name} » introuvable dans {ROOT_FILES_DIRNAME}/ "
                f"({source}) : il ne sera pas publié."
            )
            (result.errors if fail_on_missing else result.warnings).append(message)
            continue
        plan.append((source, destination))

    if result.errors:
        return result

    for source, destination in plan:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        result.copied.append(destination)
    return result


def _reserved_key(path: Path, output_root: Path) -> str:
    """Top-level name of a generated path if it sits directly at the root
    of the output directory, else a value that can never equal a bare
    file name (deeper files cannot collide with a root-level one)."""
    try:
        relative = path.resolve().relative_to(output_root.resolve())
    except ValueError:
        return "\0outside"
    return relative.parts[0] if len(relative.parts) == 1 else "\0nested"
