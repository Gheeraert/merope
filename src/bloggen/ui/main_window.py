"""Main Tkinter window for MEROPE V1 configuration editing."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from bloggen.config.defaults import build_default_config
from bloggen.config.io import ConfigValidationError, load_config, save_config
from bloggen.config.models import (
    BlogConfig,
    BuildConfig,
    ContentConfig,
    FooterConfig,
    HomeConfig,
    MenusConfig,
    PathsConfig,
    ProjectConfig,
    RenderConfig,
    SiteConfig,
)
from bloggen.config.validator import validate_config_model
from bloggen.ui.banner_panel import BannerPanel
from bloggen.ui.media_panel import MediaPanel
from bloggen.ui.menu_editor import SideMenuEditor, TopMenuEditor
from bloggen.ui.notes_panel import NotesPanel


class MainWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("MEROPE - Blog Static Generator")
        self.geometry("1100x760")
        self.current_config_path: Path | None = None
        self._build_ui()
        self.new_config()

    def _build_ui(self) -> None:
        self._build_menu_bar()

        self.path_label = ttk.Label(self, text="Configuration: (nouvelle)")
        self.path_label.pack(fill="x", padx=8, pady=(8, 2))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.site_tab, self.site_vars = _create_form_tab(
            self.notebook,
            [
                ("title", "Titre", "MEROPE"),
                ("subtitle", "Sous-titre", ""),
                ("language", "Langue", "fr"),
                ("base_url", "Base URL", ""),
                ("author", "Auteur", ""),
                ("description", "Description", ""),
            ],
        )
        self.notebook.add(self.site_tab, text="Site")

        self.banner_panel = BannerPanel(self.notebook)
        self.notebook.add(self.banner_panel, text="Bannière")

        self.paths_tab, self.paths_vars = _create_form_tab(
            self.notebook,
            [
                ("project_root", "Racine projet", "."),
                ("content_dir", "Dossier contenu", "content"),
                ("pages_dir", "Dossier pages", "content/pages"),
                ("posts_dir", "Dossier billets", "content/posts"),
                ("assets_dir", "Dossier assets", "assets"),
                ("theme_dir", "Dossier thème", "theme"),
                ("templates_dir", "Dossier templates", "theme/templates"),
                ("xslt_dir", "Dossier XSLT", "theme/xslt"),
                ("output_dir", "Dossier sortie", "site"),
                ("tei_dir", "Dossier TEI", "build/tei"),
            ],
        )
        self.notebook.add(self.paths_tab, text="Chemins")

        self.content_tab, self.content_vars = _create_form_tab(
            self.notebook,
            [
                ("source_format", "Format source", "markdown"),
                ("markdown_origin", "Origine markdown", "google_docs_export"),
                ("default_page_layout", "Layout page", "page"),
                ("default_post_layout", "Layout billet", "post"),
                ("slugify_mode", "Mode slugification", "ascii"),
            ],
            bool_fields=[
                ("use_front_matter", "Utiliser front matter", True),
                ("copy_linked_assets", "Copier assets liés", True),
            ],
        )
        self.notebook.add(self.content_tab, text="Contenus")

        self.home_tab, self.home_vars = _create_form_tab(
            self.notebook,
            [
                ("source", "Source accueil", "content/pages/accueil.md"),
                ("layout", "Layout accueil", "home"),
                ("recent_posts_count", "Nombre billets récents", "5"),
            ],
            bool_fields=[
                ("enabled", "Activer accueil", True),
                ("show_recent_posts", "Afficher billets récents", True),
            ],
        )
        self.notebook.add(self.home_tab, text="Accueil")

        self.blog_tab, self.blog_vars = _create_form_tab(
            self.notebook,
            [
                ("posts_per_page", "Billets par page", "10"),
                ("archive_title", "Titre archive", "Billets"),
                ("archive_path", "Chemin archive", "billets"),
            ],
            bool_fields=[
                ("enabled", "Activer blog", True),
                ("generate_archive_page", "Générer archive", True),
                ("sort_descending_by_date", "Tri décroissant par date", True),
            ],
        )
        self.notebook.add(self.blog_tab, text="Blog")

        self.top_menu_editor = TopMenuEditor(self.notebook)
        self.notebook.add(self.top_menu_editor, text="Menu supérieur")

        self.side_menu_editor = SideMenuEditor(self.notebook)
        self.notebook.add(self.side_menu_editor, text="Menu latéral")

        self.render_tab, self.render_vars = _create_form_tab(
            self.notebook,
            [
                ("theme_name", "Nom thème", "default"),
                ("html_template", "Template page", "page.html"),
                ("post_template", "Template billet", "post.html"),
                ("home_template", "Template accueil", "home.html"),
                ("tei_to_html_xslt", "Fichier XSLT", "tei_to_html.xsl"),
                ("lightbox_engine", "Moteur lightbox", "fancybox"),
            ],
            bool_fields=[
                ("pretty_print_html", "HTML lisible", True),
                ("generate_tei_files", "Conserver TEI", True),
                ("enable_lightbox", "Activer lightbox", True),
            ],
        )
        self.notebook.add(self.render_tab, text="Rendu")

        self.media_panel = MediaPanel(self.notebook)
        self.notebook.add(self.media_panel, text="Médias")

        self.notes_panel = NotesPanel(self.notebook)
        self.notebook.add(self.notes_panel, text="Notes")

        self.footer_tab, self.footer_vars = _create_form_tab(
            self.notebook,
            [("text", "Texte footer", "")],
            bool_fields=[
                ("show_generation_info", "Afficher info génération", True),
                ("show_last_build_date", "Afficher date build", True),
            ],
        )
        self.notebook.add(self.footer_tab, text="Footer")

        self.build_tab, self.build_vars = _create_form_tab(
            self.notebook,
            [("pandoc_command", "Commande pandoc", "pandoc")],
            bool_fields=[
                ("clean_output_dir", "Nettoyer dossier de sortie", True),
                ("copy_assets", "Copier assets", True),
                ("fail_on_missing_assets", "Échouer si assets manquants", False),
                ("fail_on_invalid_config", "Échouer si config invalide", True),
            ],
        )
        self.notebook.add(self.build_tab, text="Génération")

    def _build_menu_bar(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Nouveau", command=self.new_config)
        file_menu.add_command(label="Charger JSON...", command=self.open_config_dialog)
        file_menu.add_command(label="Enregistrer", command=self.save_config_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Quitter", command=self.destroy)

        actions_menu = tk.Menu(menu, tearoff=False)
        actions_menu.add_command(label="Générer le site", command=self.stub_generate)
        actions_menu.add_command(label="Ouvrir dossier de sortie", command=self.stub_open_output)

        menu.add_cascade(label="Fichier", menu=file_menu)
        menu.add_cascade(label="Actions", menu=actions_menu)
        self.config(menu=menu)

    def new_config(self) -> None:
        self.current_config_path = None
        self._load_into_form(build_default_config())
        self._set_path_label()

    def open_config_dialog(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Charger une configuration",
            filetypes=[("JSON", "*.json"), ("Tous les fichiers", "*.*")],
        )
        if not file_path:
            return
        try:
            config = load_config(file_path)
        except (ConfigValidationError, OSError, ValueError) as exc:
            messagebox.showerror("Erreur", f"Chargement impossible:\n{exc}")
            return

        self.current_config_path = Path(file_path)
        self._load_into_form(config)
        self._set_path_label()

    def save_config_dialog(self) -> None:
        if self.current_config_path is None:
            destination = filedialog.asksaveasfilename(
                title="Enregistrer la configuration",
                defaultextension=".json",
                filetypes=[("JSON", "*.json"), ("Tous les fichiers", "*.*")],
            )
            if not destination:
                return
            self.current_config_path = Path(destination)

        try:
            config = self._collect_from_form()
            errors = validate_config_model(config)
            if errors:
                raise ConfigValidationError(errors)
            save_config(config, self.current_config_path)
        except (ConfigValidationError, OSError, ValueError) as exc:
            messagebox.showerror("Erreur", f"Enregistrement impossible:\n{exc}")
            return

        self._set_path_label()
        messagebox.showinfo("Configuration", "Configuration enregistrée.")

    def stub_generate(self) -> None:
        messagebox.showinfo(
            "Stub V1",
            "La génération de site n'est pas implémentée dans cette passe.",
        )

    def stub_open_output(self) -> None:
        messagebox.showinfo(
            "Stub V1",
            "L'ouverture du dossier de sortie n'est pas implémentée dans cette passe.",
        )

    def _set_path_label(self) -> None:
        if self.current_config_path is None:
            self.path_label.config(text="Configuration: (nouvelle)")
            return
        self.path_label.config(text=f"Configuration: {self.current_config_path}")

    def _load_into_form(self, config: ProjectConfig) -> None:
        _set_vars(self.site_vars, config.site)
        self.banner_panel.set_data(config.banner)
        _set_vars(self.paths_vars, config.paths)
        _set_vars(self.content_vars, config.content)
        _set_vars(self.home_vars, config.home)
        _set_vars(self.blog_vars, config.blog)
        self.top_menu_editor.set_items(config.menus.top)
        self.side_menu_editor.set_sections(config.menus.side)
        _set_vars(self.render_vars, config.render)
        self.media_panel.set_data(config.media_handling)
        self.notes_panel.set_data(config.notes_rendering)
        _set_vars(self.footer_vars, config.footer)
        _set_vars(self.build_vars, config.build)

    def _collect_from_form(self) -> ProjectConfig:
        site = SiteConfig(**_read_vars(self.site_vars))
        paths = PathsConfig(**_read_vars(self.paths_vars))
        content = ContentConfig(**_read_vars(self.content_vars))

        home_raw = _read_vars(self.home_vars)
        home_raw["recent_posts_count"] = int(home_raw["recent_posts_count"])
        home = HomeConfig(**home_raw)

        blog_raw = _read_vars(self.blog_vars)
        blog_raw["posts_per_page"] = int(blog_raw["posts_per_page"])
        blog = BlogConfig(**blog_raw)

        menus = MenusConfig(
            top=self.top_menu_editor.get_items(),
            side=self.side_menu_editor.get_sections(),
        )

        render = RenderConfig(**_read_vars(self.render_vars))
        footer = FooterConfig(**_read_vars(self.footer_vars))
        build = BuildConfig(**_read_vars(self.build_vars))

        return ProjectConfig(
            version="1.0",
            site=site,
            banner=self.banner_panel.get_data(),
            paths=paths,
            content=content,
            home=home,
            blog=blog,
            menus=menus,
            render=render,
            media_handling=self.media_panel.get_data(),
            notes_rendering=self.notes_panel.get_data(),
            footer=footer,
            build=build,
        )


def _create_form_tab(
    notebook: ttk.Notebook,
    text_fields: list[tuple[str, str, str]],
    bool_fields: list[tuple[str, str, bool]] | None = None,
) -> tuple[ttk.Frame, dict[str, tk.Variable]]:
    frame = ttk.Frame(notebook)
    vars_map: dict[str, tk.Variable] = {}

    row = 0
    for field_name, label, default in text_fields:
        var = tk.StringVar(value=default)
        vars_map[field_name] = var
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(frame, textvariable=var).grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        row += 1

    if bool_fields:
        for field_name, label, default in bool_fields:
            var = tk.BooleanVar(value=default)
            vars_map[field_name] = var
            ttk.Checkbutton(frame, text=label, variable=var).grid(
                row=row, column=0, columnspan=2, sticky="w", padx=8, pady=4
            )
            row += 1

    frame.grid_columnconfigure(1, weight=1)
    return frame, vars_map


def _set_vars(vars_map: dict[str, tk.Variable], source: object) -> None:
    for field_name, var in vars_map.items():
        value = getattr(source, field_name)
        var.set(value)


def _read_vars(vars_map: dict[str, tk.Variable]) -> dict[str, object]:
    return {field_name: variable.get() for field_name, variable in vars_map.items()}
