"""Explicit validation helpers for configuration JSON."""

from __future__ import annotations

from typing import Any

from bloggen.config.models import ProjectConfig


REQUIRED_ROOT_KEYS = (
    "version",
    "site",
    "banner",
    "paths",
    "content",
    "home",
    "blog",
    "menus",
    "render",
    "media_handling",
    "notes_rendering",
    "footer",
    "build",
)

REQUIRED_PATH_KEYS = (
    "pages_dir",
    "posts_dir",
    "assets_dir",
    "theme_dir",
    "templates_dir",
    "xslt_dir",
    "output_dir",
    "tei_dir",
)

BOOLEAN_FIELDS: tuple[tuple[str, str], ...] = (
    ("banner", "enabled"),
    ("banner", "show_title_overlay"),
    ("content", "use_front_matter"),
    ("content", "copy_linked_assets"),
    ("home", "enabled"),
    ("home", "show_recent_posts"),
    ("blog", "enabled"),
    ("blog", "generate_archive_page"),
    ("blog", "sort_descending_by_date"),
    ("render", "pretty_print_html"),
    ("render", "generate_tei_files"),
    ("render", "enable_lightbox"),
    ("media_handling", "copy_media_to_output"),
    ("media_handling", "generate_clickable_figures"),
    ("media_handling", "fancybox_group_posts"),
    ("media_handling", "use_captions_as_fancybox_caption"),
    ("notes_rendering", "enable_margin_notes"),
    ("notes_rendering", "enable_footnotes"),
    ("notes_rendering", "prefer_words_over_chars"),
    ("footer", "show_generation_info"),
    ("footer", "show_last_build_date"),
    ("build", "clean_output_dir"),
    ("build", "copy_assets"),
    ("build", "fail_on_missing_assets"),
    ("build", "fail_on_invalid_config"),
)


def validate_config_dict(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["La configuration racine doit être un objet JSON."]

    _validate_root(data, errors)
    _validate_site(data, errors)
    _validate_paths(data, errors)
    _validate_menus(data, errors)
    _validate_boolean_fields(data, errors)
    return errors


def validate_config_model(config: ProjectConfig) -> list[str]:
    return validate_config_dict(config.to_dict())


def _validate_root(data: dict[str, Any], errors: list[str]) -> None:
    for key in REQUIRED_ROOT_KEYS:
        if key not in data:
            errors.append(f"Clé racine manquante: '{key}'.")

    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        errors.append("Le champ 'version' est obligatoire et doit être une chaîne non vide.")


def _validate_site(data: dict[str, Any], errors: list[str]) -> None:
    site = data.get("site")
    if not isinstance(site, dict):
        errors.append("La section 'site' doit être un objet.")
        return

    title = site.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append("Le champ 'site.title' est obligatoire.")

    language = site.get("language")
    if not isinstance(language, str) or not language.strip():
        errors.append("Le champ 'site.language' est obligatoire.")


def _validate_paths(data: dict[str, Any], errors: list[str]) -> None:
    paths = data.get("paths")
    if not isinstance(paths, dict):
        errors.append("La section 'paths' doit être un objet.")
        return

    for key in REQUIRED_PATH_KEYS:
        value = paths.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Le chemin requis 'paths.{key}' est manquant ou vide.")


def _validate_menus(data: dict[str, Any], errors: list[str]) -> None:
    menus = data.get("menus")
    if not isinstance(menus, dict):
        errors.append("La section 'menus' doit être un objet.")
        return

    top = menus.get("top")
    if not isinstance(top, list):
        errors.append("La section 'menus.top' doit être une liste.")
    else:
        for idx, item in enumerate(top):
            _validate_menu_link(item, errors, f"menus.top[{idx}]")

    side = menus.get("side")
    if not isinstance(side, list):
        errors.append("La section 'menus.side' doit être une liste.")
        return

    for idx, section in enumerate(side):
        _validate_side_section(section, errors, idx)


def _validate_side_section(section: Any, errors: list[str], index: int) -> None:
    base_path = f"menus.side[{index}]"
    if not isinstance(section, dict):
        errors.append(f"{base_path} doit être un objet.")
        return

    label = section.get("label")
    if not isinstance(label, str) or not label.strip():
        errors.append(f"{base_path}.label est requis.")

    enabled = section.get("enabled", True)
    if not isinstance(enabled, bool):
        errors.append(f"{base_path}.enabled doit être un booléen.")

    children = section.get("children")
    if not isinstance(children, list):
        errors.append(f"{base_path}.children doit être une liste.")
        return

    for child_index, child in enumerate(children):
        child_path = f"{base_path}.children[{child_index}]"
        _validate_menu_link(child, errors, child_path)
        if isinstance(child, dict) and "children" in child:
            errors.append(f"{child_path} ne peut pas contenir de sous-niveau supplémentaire.")


def _validate_menu_link(item: Any, errors: list[str], path: str) -> None:
    if not isinstance(item, dict):
        errors.append(f"{path} doit être un objet.")
        return

    label = item.get("label")
    if not isinstance(label, str) or not label.strip():
        errors.append(f"{path}.label est requis.")

    target = item.get("target")
    if not isinstance(target, str) or not target.strip():
        errors.append(f"{path}.target est requis.")

    target_type = item.get("target_type")
    if not isinstance(target_type, str) or not target_type.strip():
        errors.append(f"{path}.target_type est requis.")

    enabled = item.get("enabled")
    if not isinstance(enabled, bool):
        errors.append(f"{path}.enabled doit être un booléen.")

    new_tab = item.get("new_tab")
    if not isinstance(new_tab, bool):
        errors.append(f"{path}.new_tab doit être un booléen.")


def _validate_boolean_fields(data: dict[str, Any], errors: list[str]) -> None:
    for section_name, field_name in BOOLEAN_FIELDS:
        section = data.get(section_name)
        if not isinstance(section, dict):
            continue
        value = section.get(field_name)
        if value is not None and not isinstance(value, bool):
            errors.append(f"Le champ '{section_name}.{field_name}' doit être un booléen.")
