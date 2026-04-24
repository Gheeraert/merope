"""Default configuration values for MEROPE V1."""

from __future__ import annotations

from bloggen.config.models import MenuLink, ProjectConfig, SideMenuSection


def build_default_config() -> ProjectConfig:
    """Return a coherent default V1 configuration."""
    config = ProjectConfig()
    config.site.title = "MEROPE"
    config.site.subtitle = "Carnet académique statique"
    config.site.language = "fr"
    config.site.description = "Configuration locale par défaut."

    config.menus.top = [
        MenuLink(label="Accueil", target="/index.html"),
        MenuLink(label="Billets", target="/billets/index.html"),
    ]
    config.menus.side = [
        SideMenuSection(
            label="Navigation",
            children=[
                MenuLink(label="Présentation", target="/presentation/index.html"),
            ],
        )
    ]
    return config
