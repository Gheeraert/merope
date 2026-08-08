"""Create a ready-to-edit project skeleton for a new MEROPE site.

Used by the "Nouveau projet..." action in the GUI: given an empty (or
mostly empty) target folder, lay out the standard directory structure and
write a small amount of welcoming content, so a first-time user has
something real to look at, edit, and build immediately instead of a blank
folder full of empty config fields.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from bloggen.config.defaults import build_default_config
from bloggen.config.io import save_config
from bloggen.config.models import MenuLink, ProjectConfig
from bloggen.content.writer import default_filename, write_content_file

_WELCOME_PAGE_SLUG = "bienvenue"
_WELCOME_POST_SLUG = "premier-billet"

_WELCOME_PAGE_BODY = """\
# Bienvenue sur votre nouveau carnet

Ce site a été généré par MEROPE. Cette page sert de point de départ :
modifiez-la ou remplacez-la par votre propre contenu.

## Comment ça marche ?

- Les **pages** (comme celle-ci) vivent dans `content/pages/`. Elles n'ont pas de date.
- Les **billets** (articles datés) vivent dans `content/posts/`.
- Chaque fichier commence par un en-tête (front matter) entre deux lignes `---`, qui précise au minimum un titre, un identifiant d'URL (slug) et un type (`page` ou `post`).
- Les images se placent dans `assets/images/` et se référencent avec `!\\[Description\\](../../assets/images/mon-image.jpg)` (sans les antislashs).

## Pour continuer

- Ouvrez l'**Éditeur de contenu** (barre d'outils) pour créer ou modifier des pages et des billets sans écrire de Markdown à la main.
- Les dossiers utilisés par le projet sont modifiables à tout moment dans l'onglet **Chemins**.
- Une fois prêt, utilisez **Générer le site** dans le menu Actions.

Bonne rédaction !
"""

_WELCOME_POST_BODY = """\
# Premier billet

Ceci est un billet de démonstration, créé automatiquement avec votre nouveau projet.

Un billet est un article daté : il apparaît dans la liste des **Billets** et
peut inclure du texte mis en forme, des images, des listes, des citations,
des tableaux et des notes de bas de page[^1].

Vous pouvez modifier ou supprimer ce billet directement depuis l'**Éditeur
de contenu** de MEROPE.

[^1]: Comme celle-ci.
"""


def create_new_project(root: Path) -> Path:
    """Lay out a minimal project at ``root`` and return its config file path.

    Creates the standard directory structure (``content/pages``,
    ``content/posts``, ``assets/images``, ``assets/banner``,
    ``theme/templates``, ``theme/xslt`` — the last two are optional
    overrides and may stay empty, the build falls back to bundled
    defaults), a welcome page, a welcome post, and a matching
    ``config/site.json``.
    """
    root = Path(root)
    pages_dir = root / "content" / "pages"
    posts_dir = root / "content" / "posts"

    for relative in (
        "content/pages",
        "content/posts",
        "assets/images",
        "assets/banner",
        "theme/templates",
        "theme/xslt",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)

    write_content_file(
        pages_dir,
        default_filename("page", _WELCOME_PAGE_SLUG),
        {"title": "Bienvenue", "slug": _WELCOME_PAGE_SLUG, "type": "page"},
        _WELCOME_PAGE_BODY,
    )

    today = date.today().isoformat()
    write_content_file(
        posts_dir,
        default_filename("post", _WELCOME_POST_SLUG, date=today),
        {
            "title": "Bienvenue !",
            "slug": _WELCOME_POST_SLUG,
            "type": "post",
            "date": today,
        },
        _WELCOME_POST_BODY,
    )

    config = _build_scaffold_config()
    config_path = root / "config" / "site.json"
    save_config(config, config_path)
    return config_path


def _build_scaffold_config() -> ProjectConfig:
    config = build_default_config()
    config.paths.project_root = "."
    config.home.source = f"content/pages/{_WELCOME_PAGE_SLUG}.md"
    config.menus.top = [
        MenuLink(label="Accueil", target="/index.html"),
        MenuLink(label="Billets", target="/billets/index.html"),
    ]
    config.menus.side = []
    return config
