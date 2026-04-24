"""Explicit configuration models for MEROPE V1."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class SiteConfig:
    title: str = "MEROPE"
    subtitle: str = ""
    base_url: str = ""
    language: str = "fr"
    author: str = ""
    description: str = ""


@dataclass(slots=True)
class BannerConfig:
    enabled: bool = False
    image: str = ""
    link: str = "/index.html"
    alt: str = ""
    show_title_overlay: bool = False
    height_px: int = 220


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


@dataclass(slots=True)
class ContentConfig:
    source_format: str = "markdown"
    markdown_origin: str = "google_docs_export"
    use_front_matter: bool = True
    default_page_layout: str = "page"
    default_post_layout: str = "post"
    slugify_mode: str = "ascii"
    copy_linked_assets: bool = True


@dataclass(slots=True)
class HomeConfig:
    enabled: bool = True
    source: str = "content/pages/accueil.md"
    layout: str = "home"
    show_recent_posts: bool = True
    recent_posts_count: int = 5


@dataclass(slots=True)
class BlogConfig:
    enabled: bool = True
    posts_per_page: int = 10
    generate_archive_page: bool = True
    archive_title: str = "Billets"
    archive_path: str = "billets"
    sort_descending_by_date: bool = True


@dataclass(slots=True)
class MenuLink:
    label: str
    target: str
    target_type: str = "internal"
    enabled: bool = True
    new_tab: bool = False


@dataclass(slots=True)
class SideMenuSection:
    label: str
    enabled: bool = True
    children: list[MenuLink] = field(default_factory=list)


@dataclass(slots=True)
class MenusConfig:
    top: list[MenuLink] = field(default_factory=list)
    side: list[SideMenuSection] = field(default_factory=list)


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


@dataclass(slots=True)
class MediaHandlingConfig:
    strategy: str = "copy_local_assets"
    images_dir: str = "assets/images"
    copy_media_to_output: bool = True
    generate_clickable_figures: bool = True
    fancybox_group_posts: bool = True
    use_captions_as_fancybox_caption: bool = True


@dataclass(slots=True)
class NotesRenderingConfig:
    mode: str = "margin_excerpt_plus_footnote"
    enable_margin_notes: bool = True
    enable_footnotes: bool = True
    margin_excerpt_words: int = 8
    margin_excerpt_chars: int = 80
    prefer_words_over_chars: bool = True
    footnotes_location: str = "end_of_article"


@dataclass(slots=True)
class FooterConfig:
    text: str = ""
    show_generation_info: bool = True
    show_last_build_date: bool = True


@dataclass(slots=True)
class BuildConfig:
    clean_output_dir: bool = True
    copy_assets: bool = True
    fail_on_missing_assets: bool = False
    fail_on_invalid_config: bool = True
    pandoc_command: str = "pandoc"


@dataclass(slots=True)
class ProjectConfig:
    version: str = "1.0"
    site: SiteConfig = field(default_factory=SiteConfig)
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ProjectConfig":
        site = SiteConfig(**_dict_or_empty(raw.get("site")))
        banner = BannerConfig(**_dict_or_empty(raw.get("banner")))
        paths = PathsConfig(**_dict_or_empty(raw.get("paths")))
        content = ContentConfig(**_dict_or_empty(raw.get("content")))
        home = HomeConfig(**_dict_or_empty(raw.get("home")))
        blog = BlogConfig(**_dict_or_empty(raw.get("blog")))
        render = RenderConfig(**_dict_or_empty(raw.get("render")))
        media_handling = MediaHandlingConfig(**_dict_or_empty(raw.get("media_handling")))
        notes_rendering = NotesRenderingConfig(**_dict_or_empty(raw.get("notes_rendering")))
        footer = FooterConfig(**_dict_or_empty(raw.get("footer")))
        build = BuildConfig(**_dict_or_empty(raw.get("build")))
        menus = _menus_from_dict(_dict_or_empty(raw.get("menus")))
        return cls(
            version=str(raw.get("version", "1.0")),
            site=site,
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
        )


def _dict_or_empty(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


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
        side_sections.append(
            SideMenuSection(
                label=str(section.get("label", "")),
                enabled=bool(section.get("enabled", True)),
                children=children,
            )
        )
    return MenusConfig(top=top_items, side=side_sections)


def _menu_link_from_dict(raw: dict[str, Any]) -> MenuLink:
    return MenuLink(
        label=str(raw.get("label", "")),
        target=str(raw.get("target", "")),
        target_type=str(raw.get("target_type", "internal")),
        enabled=bool(raw.get("enabled", True)),
        new_tab=bool(raw.get("new_tab", False)),
    )
