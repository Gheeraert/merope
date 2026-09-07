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
    "search",
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

NUMBER_FIELDS: tuple[tuple[str, str, int, int | None], ...] = (
    ("banner", "height_px", 1, None),
    ("home", "recent_posts_count", 0, None),
    ("blog", "posts_per_page", 0, None),
    ("notes_rendering", "margin_excerpt_words", 0, None),
    ("notes_rendering", "margin_excerpt_chars", 0, None),
    ("search", "excerpt_length", 0, None),
    ("ftp", "port", 1, 65535),
)

HOME_MODES = ("page", "recent_posts")
TARGET_TYPES = ("internal", "external")

BOOLEAN_FIELDS: tuple[tuple[str, str], ...] = (
    ("banner", "enabled"),
    ("banner", "show_title_overlay"),
    ("content", "use_front_matter"),
    ("content", "copy_linked_assets"),
    ("home", "enabled"),
    ("blog", "enabled"),
    ("blog", "generate_archive_page"),
    ("blog", "sort_descending_by_date"),
    ("blog", "generate_rss_feed"),
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
    ("build", "generate_sitemap"),
    ("build", "generate_robots_txt"),
    ("build", "check_broken_links"),
    ("build", "fail_on_broken_links"),
    ("build", "generate_redirects"),
    ("search", "enabled"),
    ("ftp", "use_tls"),
    ("ftp", "passive_mode"),
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
    _validate_number_fields(data, errors)
    _validate_home_mode(data, errors)
    _validate_ftp_site_url(data, errors)
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


def _validate_optional_http_url(value: Any, errors: list[str], path: str) -> None:
    """Used for fields fed straight into <link>/<meta>/RSS/sitemap URLs or
    opened in a browser (site.base_url, ftp.site_url) — an empty string is
    fine (the feature it drives is simply skipped, already warned about
    elsewhere at build time), but a non-empty value that isn't a real
    http(s) URL would silently corrupt every absolute link built from it.
    """
    if value is None:
        return
    if not isinstance(value, str):
        errors.append(f"'{path}' doit être une chaîne.")
        return
    text = value.strip()
    if text and not text.lower().startswith(("http://", "https://")):
        errors.append(f"'{path}' doit être une URL http(s) (ex. https://exemple.org), reçu {value!r}.")


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

    _validate_optional_http_url(site.get("base_url"), errors, "site.base_url")


def _validate_ftp_site_url(data: dict[str, Any], errors: list[str]) -> None:
    ftp = data.get("ftp")
    if not isinstance(ftp, dict):
        return
    _validate_optional_http_url(ftp.get("site_url"), errors, "ftp.site_url")


def _validate_home_mode(data: dict[str, Any], errors: list[str]) -> None:
    home = data.get("home")
    if not isinstance(home, dict):
        return
    mode = home.get("mode")
    if mode is not None and mode not in HOME_MODES:
        errors.append(f"'home.mode' doit être l'une de {HOME_MODES}, reçu {mode!r}.")


def _validate_number_fields(data: dict[str, Any], errors: list[str]) -> None:
    for section_name, field_name, minimum, maximum in NUMBER_FIELDS:
        section = data.get(section_name)
        if not isinstance(section, dict):
            continue
        value = section.get(field_name)
        if value is None:
            continue
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"Le champ '{section_name}.{field_name}' doit être un nombre entier.")
            continue
        if value < minimum:
            errors.append(f"Le champ '{section_name}.{field_name}' doit être supérieur ou égal à {minimum}.")
        elif maximum is not None and value > maximum:
            errors.append(f"Le champ '{section_name}.{field_name}' doit être inférieur ou égal à {maximum}.")


def _normalized_path_key(value: str) -> str:
    return value.strip().replace("\\", "/").rstrip("/") or "."


def _validate_paths(data: dict[str, Any], errors: list[str]) -> None:
    paths = data.get("paths")
    if not isinstance(paths, dict):
        errors.append("La section 'paths' doit être un objet.")
        return

    seen: dict[str, str] = {}
    for key in REQUIRED_PATH_KEYS:
        value = paths.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Le chemin requis 'paths.{key}' est manquant ou vide.")
            continue

        # Two roles sharing one folder means the build overwrites one with
        # the other (e.g. output_dir == assets_dir would wipe assets on
        # every clean) — every path field must point somewhere distinct.
        normalized = _normalized_path_key(value)
        collision = seen.get(normalized)
        if collision is not None:
            errors.append(
                f"'paths.{key}' et 'paths.{collision}' pointent vers le même dossier "
                f"({value!r}) : corrigez l'un des deux."
            )
        else:
            seen[normalized] = key


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


def _validate_target_type(target_type: str, errors: list[str], path: str) -> None:
    if target_type and target_type not in TARGET_TYPES:
        errors.append(f"'{path}.target_type' doit être l'une de {TARGET_TYPES}, reçu {target_type!r}.")


def _validate_external_target_scheme(target: str, target_type: str, errors: list[str], path: str) -> None:
    """An "external" menu target is embedded in an <iframe> and linked in
    an <a href> (see render_external_link_fragment) — only http(s) is
    safe there. A scheme such as javascript:/data: would otherwise reach
    the generated HTML verbatim.
    """
    if target_type != "external" or not isinstance(target, str):
        return
    if target.strip() and not target.strip().lower().startswith(("http://", "https://")):
        errors.append(f"{path}.target doit être une URL http(s) pour un lien de type 'external'.")


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

    target = section.get("target", "")
    if not isinstance(target, str):
        errors.append(f"{base_path}.target doit être une chaîne.")

    target_type = section.get("target_type", "internal")
    if not isinstance(target_type, str):
        errors.append(f"{base_path}.target_type doit être une chaîne.")
    else:
        _validate_target_type(target_type, errors, base_path)
        if isinstance(target, str):
            _validate_external_target_scheme(target, target_type, errors, base_path)

    numbered = section.get("numbered", False)
    if not isinstance(numbered, bool):
        errors.append(f"{base_path}.numbered doit être un booléen.")

    children = section.get("children")
    if not isinstance(children, list):
        errors.append(f"{base_path}.children doit être une liste.")
    else:
        for child_index, child in enumerate(children):
            child_path = f"{base_path}.children[{child_index}]"
            _validate_menu_link(child, errors, child_path)
            if isinstance(child, dict) and "children" in child:
                errors.append(f"{child_path} ne peut pas contenir de sous-niveau supplémentaire.")

    subsections = section.get("subsections", [])
    if not isinstance(subsections, list):
        errors.append(f"{base_path}.subsections doit être une liste.")
        return

    for sub_index, subsection in enumerate(subsections):
        sub_path = f"{base_path}.subsections[{sub_index}]"
        _validate_side_subsection(subsection, errors, sub_path)


def _validate_side_subsection(subsection: Any, errors: list[str], base_path: str) -> None:
    if not isinstance(subsection, dict):
        errors.append(f"{base_path} doit être un objet.")
        return

    label = subsection.get("label")
    if not isinstance(label, str) or not label.strip():
        errors.append(f"{base_path}.label est requis.")

    enabled = subsection.get("enabled", True)
    if not isinstance(enabled, bool):
        errors.append(f"{base_path}.enabled doit être un booléen.")

    target = subsection.get("target", "")
    if not isinstance(target, str):
        errors.append(f"{base_path}.target doit être une chaîne.")

    target_type = subsection.get("target_type", "internal")
    if not isinstance(target_type, str):
        errors.append(f"{base_path}.target_type doit être une chaîne.")
    else:
        _validate_target_type(target_type, errors, base_path)
        if isinstance(target, str):
            _validate_external_target_scheme(target, target_type, errors, base_path)

    children = subsection.get("children")
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
    else:
        _validate_target_type(target_type, errors, path)
        if isinstance(target, str):
            _validate_external_target_scheme(target, target_type, errors, path)

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
