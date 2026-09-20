"""Explicit configuration models for MEROPE V1."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any


@dataclass(slots=True)
class SiteConfig:
    title: str = "MEROPE"
    subtitle: str = ""
    base_url: str = ""
    language: str = "fr"
    author: str = ""
    description: str = ""
    # Site-wide license (a personal/academic site has one license for its
    # whole content, not one per post). license_spdx_id, when it names a
    # known Creative Commons license (see bloggen.tei.licenses), resolves
    # automatically and overrides license_name/license_url — those two
    # stay as a free-text fallback for any other license. All three blank
    # means "no license declared" in the TEI teiHeader. HTML does not
    # currently expose these license fields.
    license_spdx_id: str = ""
    license_name: str = ""
    license_url: str = ""
    # See ProjectConfig.unknown_data's docstring: a lossless-round-trip
    # passthrough bag for keys this section doesn't (yet) know about,
    # never a real editorial field.
    unknown_data: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(slots=True)
class BannerConfig:
    enabled: bool = False
    image: str = ""
    link: str = "/index.html"
    alt: str = ""
    show_title_overlay: bool = False
    height_px: int = 220
    unknown_data: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(slots=True)
class TopBannerConfig:
    enabled: bool = False
    image: str = ""
    alt: str = ""
    link: str = ""
    unknown_data: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(slots=True)
class PathsConfig:
    project_root: str = "."
    content_dir: str = "content"
    pages_dir: str = "content/pages"
    posts_dir: str = "content/posts"
    assets_dir: str = "assets"
    theme_dir: str = "theme"
    templates_dir: str = "theme/templates"
    xslt_dir: str = "theme/xslt"
    output_dir: str = "site"
    tei_dir: str = "build/tei"
    unknown_data: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(slots=True)
class ContentConfig:
    source_format: str = "markdown"
    markdown_origin: str = "google_docs_export"
    use_front_matter: bool = True
    default_page_layout: str = "page"
    default_post_layout: str = "post"
    slugify_mode: str = "ascii"
    copy_linked_assets: bool = True
    unknown_data: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(slots=True)
class HomeConfig:
    mode: str = "page"  # "page" (page fixe) ou "recent_posts" (derniers billets)
    source: str = "content/pages/accueil.md"
    layout: str = "home"
    recent_posts_count: int = 5
    # In "recent_posts" mode: length (characters) of the excerpt shown
    # per post on the home page — the full body used to be embedded
    # there too, duplicating every one of those posts' content across
    # two fully-indexable URLs.
    recent_posts_excerpt_length: int = 2000
    unknown_data: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(slots=True)
class BlogConfig:
    enabled: bool = True
    posts_per_page: int = 10
    generate_archive_page: bool = True
    archive_title: str = "Billets"
    archive_path: str = "billets"
    sort_descending_by_date: bool = True
    generate_rss_feed: bool = True
    unknown_data: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(slots=True)
class MenuLink:
    label: str
    target: str
    target_type: str = "internal"
    enabled: bool = True
    new_tab: bool = False
    unknown_data: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(slots=True)
class SideMenuSubSection:
    """The optional third menu level: a lettered (A., B., C.) group of leaf
    links nested inside a numbered ``SideMenuSection`` — e.g. for an outline
    like "I. Rhétorique / A. Bossuet et la rhétorique chrétienne / <billets>".
    """

    label: str
    enabled: bool = True
    target: str = ""  # optional: makes the subsection header itself a clickable link
    target_type: str = "internal"
    children: list[MenuLink] = field(default_factory=list)
    unknown_data: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(slots=True)
class SideMenuSection:
    label: str
    enabled: bool = True
    target: str = ""  # optional: makes the section header itself a clickable link
    target_type: str = "internal"
    numbered: bool = False  # prefixes this section "I.", "II."... and its subsections "A.", "B."...
    children: list[MenuLink] = field(default_factory=list)
    subsections: list[SideMenuSubSection] = field(default_factory=list)
    unknown_data: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(slots=True)
class MenusConfig:
    top: list[MenuLink] = field(default_factory=list)
    side: list[SideMenuSection] = field(default_factory=list)
    side_title: str = ""  # optional heading shown above the side menu, e.g. "Menu"
    unknown_data: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(slots=True)
class RenderConfig:
    theme_name: str = "default"
    html_template: str = "page.html"
    post_template: str = "post.html"
    home_template: str = "home.html"
    tei_to_html_xslt: str = "tei_to_html.xsl"
    pretty_print_html: bool = True
    generate_tei_files: bool = True
    enable_lightbox: bool = True
    lightbox_engine: str = "fancybox"
    # Diagnostic by default (see bloggen.tei.commons_publishing's module
    # docstring) — ordinary editorial content now conforms to the Commons
    # Publishing profile, but three Markdown constructs still don't (see
    # that docstring) and are only ever reported as a warning here. Set
    # build.fail_on_invalid_commons_publishing to turn that warning into
    # a build failure instead.
    validate_commons_publishing: bool = True
    unknown_data: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(slots=True)
class MediaHandlingConfig:
    strategy: str = "copy_local_assets"
    images_dir: str = "assets/images"
    copy_media_to_output: bool = True
    generate_clickable_figures: bool = True
    fancybox_group_posts: bool = True
    use_captions_as_fancybox_caption: bool = True
    unknown_data: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(slots=True)
class NotesRenderingConfig:
    mode: str = "margin_excerpt_plus_footnote"
    # Not implemented for now regardless of this flag — see
    # render/margin_notes.py, which unconditionally ignores it.
    enable_margin_notes: bool = False
    enable_footnotes: bool = True
    margin_excerpt_words: int = 8
    margin_excerpt_chars: int = 80
    prefer_words_over_chars: bool = True
    footnotes_location: str = "end_of_article"
    unknown_data: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(slots=True)
class FooterConfig:
    text: str = ""
    show_generation_info: bool = True
    show_last_build_date: bool = True
    unknown_data: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(slots=True)
class BuildConfig:
    clean_output_dir: bool = True
    copy_assets: bool = True
    fail_on_missing_assets: bool = False
    fail_on_invalid_config: bool = True
    pandoc_command: str = "pandoc"
    generate_sitemap: bool = True
    generate_robots_txt: bool = True
    check_broken_links: bool = True
    fail_on_broken_links: bool = False
    generate_redirects: bool = True
    # Off by default, like fail_on_broken_links above: fenced code blocks
    # and horizontal rules can still produce TEI outside the Commons
    # Publishing profile (see bloggen.tei.commons_publishing's module
    # docstring), which would fail the build when this is on. This flag
    # has no effect when render.validate_commons_publishing is off (see
    # build_site).
    fail_on_invalid_commons_publishing: bool = False
    unknown_data: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(slots=True)
class SearchConfig:
    """Client-side static search: a JSON index built at generation time,
    filtered entirely in the visitor's browser (no server, no database)."""

    enabled: bool = True
    excerpt_length: int = 160
    unknown_data: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(slots=True)
class SeoConfig:
    """Referencing settings. ``verification_files`` lists plain file names
    (no directory) of search-engine/service ownership-verification files
    (e.g. ``google123456789abcdef.html``, ``BingSiteAuth.xml``). Their
    canonical source is ``<project_root>/root-files/<name>``; every build
    copies each one, byte for byte, to the root of the output directory
    (see bloggen.build.verification_files)."""

    verification_files: list[str] = field(default_factory=list)
    unknown_data: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(slots=True)
class FtpConfig:
    """Publishing settings for the FTP/FTPS transfer of the generated site.

    ``password`` is kept in memory and MEROPE attempts to persist it in the
    OS credential store. It is never written to the saved JSON, whether or
    not that credential-store persistence succeeds; if it fails, the
    password stays usable for the current session only, and callers
    collecting save warnings are notified that it will need to be
    re-entered next time.
    """

    host: str = ""
    port: int = 21
    username: str = ""
    password: str = ""
    remote_dir: str = "/"
    use_tls: bool = True
    passive_mode: bool = True
    site_url: str = ""
    # password is a declared field name, so it can never end up here (see
    # _extra_fields) — it always goes through the dedicated keyring
    # handling in bloggen.config.io, never through this generic
    # passthrough. Regression-tested in test_config_ftp_password.py.
    unknown_data: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(slots=True)
class ProjectConfig:
    version: str = "1.0"
    site: SiteConfig = field(default_factory=SiteConfig)
    top_banner: TopBannerConfig = field(default_factory=TopBannerConfig)
    banner: BannerConfig = field(default_factory=BannerConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    content: ContentConfig = field(default_factory=ContentConfig)
    home: HomeConfig = field(default_factory=HomeConfig)
    blog: BlogConfig = field(default_factory=BlogConfig)
    menus: MenusConfig = field(default_factory=MenusConfig)
    render: RenderConfig = field(default_factory=RenderConfig)
    media_handling: MediaHandlingConfig = field(default_factory=MediaHandlingConfig)
    notes_rendering: NotesRenderingConfig = field(default_factory=NotesRenderingConfig)
    footer: FooterConfig = field(default_factory=FooterConfig)
    build: BuildConfig = field(default_factory=BuildConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    seo: SeoConfig = field(default_factory=SeoConfig)
    ftp: FtpConfig = field(default_factory=FtpConfig)
    # Round-trip passthrough for whatever this version of MEROPE doesn't
    # recognize at the JSON root (e.g. a future top-level section) — see
    # the module-level "lossless round-trip" invariant. Every section
    # dataclass above carries the same kind of bag for keys unknown
    # *within* that section. Known fields always take priority: a key
    # that used to be unknown and later becomes a real field is read (and
    # written back) through that real field, never through this bag —
    # see _extra_fields/_section_to_dict. Never surfaced in the UI: it is
    # populated purely by ProjectConfig.from_dict/to_dict and threaded
    # through bloggen.ui.main_window.MainWindow between load and save.
    unknown_data: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {**self.unknown_data}
        data["version"] = self.version
        data["site"] = _section_to_dict(self.site)
        data["top_banner"] = _section_to_dict(self.top_banner)
        data["banner"] = _section_to_dict(self.banner)
        data["paths"] = _section_to_dict(self.paths)
        data["content"] = _section_to_dict(self.content)
        data["home"] = _section_to_dict(self.home)
        data["blog"] = _section_to_dict(self.blog)
        data["menus"] = _menus_to_dict(self.menus)
        data["render"] = _section_to_dict(self.render)
        data["media_handling"] = _section_to_dict(self.media_handling)
        data["notes_rendering"] = _section_to_dict(self.notes_rendering)
        data["footer"] = _section_to_dict(self.footer)
        data["build"] = _section_to_dict(self.build)
        data["search"] = _section_to_dict(self.search)
        data["seo"] = _section_to_dict(self.seo)
        data["ftp"] = _section_to_dict(self.ftp)
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ProjectConfig":
        # Every section is filtered through _filtered_fields (not just
        # home/ftp, previously): a stray/renamed key left over from an
        # older site.json must be dropped, not raise a raw TypeError out of
        # the dataclass constructor (see _filtered_fields' docstring). Its
        # complement, _extra_fields, captures exactly those dropped keys
        # into unknown_data instead of discarding them, so a later save
        # can still write them back (see ProjectConfig.unknown_data).
        site = _section_from_dict(SiteConfig, _dict_or_empty(raw.get("site")))
        top_banner = _section_from_dict(TopBannerConfig, _dict_or_empty(raw.get("top_banner")))
        banner = _section_from_dict(BannerConfig, _dict_or_empty(raw.get("banner")))
        paths = _section_from_dict(PathsConfig, _dict_or_empty(raw.get("paths")))
        content = _section_from_dict(ContentConfig, _dict_or_empty(raw.get("content")))
        home = _section_from_dict(HomeConfig, _dict_or_empty(raw.get("home")))
        blog = _section_from_dict(BlogConfig, _dict_or_empty(raw.get("blog")))
        render = _section_from_dict(RenderConfig, _dict_or_empty(raw.get("render")))
        media_handling = _section_from_dict(MediaHandlingConfig, _dict_or_empty(raw.get("media_handling")))
        notes_rendering = _section_from_dict(NotesRenderingConfig, _dict_or_empty(raw.get("notes_rendering")))
        footer = _section_from_dict(FooterConfig, _dict_or_empty(raw.get("footer")))
        build = _section_from_dict(BuildConfig, _dict_or_empty(raw.get("build")))
        search = _section_from_dict(SearchConfig, _dict_or_empty(raw.get("search")))
        ftp = _section_from_dict(FtpConfig, _dict_or_empty(raw.get("ftp")))
        seo = _section_from_dict(SeoConfig, _dict_or_empty(raw.get("seo")))
        # A hand-edited value that isn't a list of strings can't be a valid
        # file name list: fall back to empty rather than crash on load.
        files = seo.verification_files
        seo.verification_files = [f for f in files if isinstance(f, str)] if isinstance(files, list) else []
        menus = _menus_from_dict(_dict_or_empty(raw.get("menus")))
        return cls(
            version=str(raw.get("version", "1.0")),
            site=site,
            top_banner=top_banner,
            banner=banner,
            paths=paths,
            content=content,
            home=home,
            blog=blog,
            menus=menus,
            render=render,
            media_handling=media_handling,
            notes_rendering=notes_rendering,
            footer=footer,
            build=build,
            search=search,
            seo=seo,
            ftp=ftp,
            unknown_data=_extra_fields(ProjectConfig, raw),
        )


def _dict_or_empty(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _known_field_names(dataclass_type: type) -> set[str]:
    return {f.name for f in fields(dataclass_type) if f.name != "unknown_data"}


def _filtered_fields(dataclass_type: type, raw: dict[str, Any]) -> dict[str, Any]:
    """Drop keys with no matching field, so removed/renamed settings in an
    older site.json don't break loading."""
    known = _known_field_names(dataclass_type)
    return {key: value for key, value in raw.items() if key in known}


def _extra_fields(dataclass_type: type, raw: dict[str, Any]) -> dict[str, Any]:
    """The complement of _filtered_fields: every key with no matching field,
    captured instead of dropped so it can be written back on save (see
    ProjectConfig.unknown_data)."""
    known = _known_field_names(dataclass_type)
    return {key: value for key, value in raw.items() if key not in known}


def _section_from_dict(dataclass_type: type, raw: dict[str, Any]) -> Any:
    return dataclass_type(**_filtered_fields(dataclass_type, raw), unknown_data=_extra_fields(dataclass_type, raw))


def _section_to_dict(section: Any) -> dict[str, Any]:
    """Known fields always take priority over same-named leftover opaque
    keys (should such a collision ever occur) — spread order below is not
    incidental."""
    known = {f.name: getattr(section, f.name) for f in fields(section) if f.name != "unknown_data"}
    return {**section.unknown_data, **known}


def _menus_from_dict(raw: dict[str, Any]) -> MenusConfig:
    top_items: list[MenuLink] = []
    for item in raw.get("top", []):
        if isinstance(item, dict):
            top_items.append(_menu_link_from_dict(item))

    side_sections: list[SideMenuSection] = []
    for section in raw.get("side", []):
        if not isinstance(section, dict):
            continue
        children: list[MenuLink] = []
        for child in section.get("children", []):
            if isinstance(child, dict):
                children.append(_menu_link_from_dict(child))
        subsections: list[SideMenuSubSection] = []
        for subsection in section.get("subsections", []):
            if isinstance(subsection, dict):
                subsections.append(_side_subsection_from_dict(subsection))
        side_sections.append(
            SideMenuSection(
                label=str(section.get("label", "")),
                enabled=bool(section.get("enabled", True)),
                target=str(section.get("target", "")),
                target_type=str(section.get("target_type", "internal")),
                numbered=bool(section.get("numbered", False)),
                children=children,
                subsections=subsections,
                unknown_data=_extra_fields(SideMenuSection, section),
            )
        )
    return MenusConfig(
        top=top_items,
        side=side_sections,
        side_title=str(raw.get("side_title", "")),
        unknown_data=_extra_fields(MenusConfig, raw),
    )


def _menus_to_dict(menus: MenusConfig) -> dict[str, Any]:
    return {
        **menus.unknown_data,
        "top": [_menu_link_to_dict(item) for item in menus.top],
        "side": [_side_section_to_dict(section) for section in menus.side],
        "side_title": menus.side_title,
    }


def _side_section_to_dict(section: SideMenuSection) -> dict[str, Any]:
    return {
        **section.unknown_data,
        "label": section.label,
        "enabled": section.enabled,
        "target": section.target,
        "target_type": section.target_type,
        "numbered": section.numbered,
        "children": [_menu_link_to_dict(child) for child in section.children],
        "subsections": [_side_subsection_to_dict(sub) for sub in section.subsections],
    }


def _side_subsection_from_dict(raw: dict[str, Any]) -> SideMenuSubSection:
    children: list[MenuLink] = []
    for child in raw.get("children", []):
        if isinstance(child, dict):
            children.append(_menu_link_from_dict(child))
    return SideMenuSubSection(
        label=str(raw.get("label", "")),
        enabled=bool(raw.get("enabled", True)),
        target=str(raw.get("target", "")),
        target_type=str(raw.get("target_type", "internal")),
        children=children,
        unknown_data=_extra_fields(SideMenuSubSection, raw),
    )


def _side_subsection_to_dict(subsection: SideMenuSubSection) -> dict[str, Any]:
    return {
        **subsection.unknown_data,
        "label": subsection.label,
        "enabled": subsection.enabled,
        "target": subsection.target,
        "target_type": subsection.target_type,
        "children": [_menu_link_to_dict(child) for child in subsection.children],
    }


def _menu_link_from_dict(raw: dict[str, Any]) -> MenuLink:
    return MenuLink(
        label=str(raw.get("label", "")),
        target=str(raw.get("target", "")),
        target_type=str(raw.get("target_type", "internal")),
        enabled=bool(raw.get("enabled", True)),
        new_tab=bool(raw.get("new_tab", False)),
        unknown_data=_extra_fields(MenuLink, raw),
    )


def _menu_link_to_dict(link: MenuLink) -> dict[str, Any]:
    return {
        **link.unknown_data,
        "label": link.label,
        "target": link.target,
        "target_type": link.target_type,
        "enabled": link.enabled,
        "new_tab": link.new_tab,
    }
