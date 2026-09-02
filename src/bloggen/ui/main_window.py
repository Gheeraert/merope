"""Main Tkinter window for MEROPE V1 configuration editing."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from bloggen.build.reports import format_build_report
from bloggen.build.site_builder import build_site, resolve_project_root
from bloggen.config.defaults import build_default_config
from bloggen.config.io import ConfigValidationError, load_config, save_config
from bloggen.config.scaffold import create_new_project
from bloggen.config.models import (
    BlogConfig,
    BuildConfig,
    ContentConfig,
    FooterConfig,
    FtpConfig,
    HomeConfig,
    MenusConfig,
    PathsConfig,
    ProjectConfig,
    RenderConfig,
    SearchConfig,
    SiteConfig,
)
from bloggen.config.validator import validate_config_model
from bloggen.content.writer import list_content_targets
from bloggen.ui.banner_panel import BannerPanel
from bloggen.ui.content_editor import ContentEditorWindow
from bloggen.ui.ftp_publish_dialog import FtpPublishDialog
from bloggen.ui.media_panel import MediaPanel
from bloggen.ui.menu_editor import SideMenuEditor, TopMenuEditor
from bloggen.ui.notes_panel import NotesPanel
from bloggen.ui.site_preview import SitePreviewServer
from bloggen.ui.tooltip import add_tooltip


class MainWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("MEROPE - Blog Static Generator")
        self.geometry("1100x760")
        self.current_config_path: Path | None = None
        self._site_preview_server = SitePreviewServer()
        self._ftp_config = FtpConfig()
        self._build_ui()
        self.new_config()

    def _build_ui(self) -> None:
        self._build_menu_bar()
        self._build_toolbar()

        self.path_label = ttk.Label(self, text="Configuration: (nouvelle)")
        self.path_label.pack(fill="x", padx=8, pady=(0, 2))

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
            intro=(
                "Identité générale du site : ce qui apparaît dans l'onglet du navigateur, "
                "l'en-tête des pages et les métadonnées (SEO, flux RSS)."
            ),
            help_texts={
                "title": (
                    "Nom du site, affiché dans l'onglet du navigateur et en haut de chaque page.\n"
                    "Obligatoire (ne peut pas être vide).\n"
                    "Exemple : Carnets de recherche"
                ),
                "subtitle": (
                    "Accroche courte affichée sous le titre, optionnelle.\n"
                    "Exemple : Notes de terrain et carnets d'enquête"
                ),
                "language": (
                    "Code de langue du contenu (norme ISO 639-1), utilisé dans le HTML "
                    "généré (attribut lang) et les flux RSS.\n"
                    "Obligatoire. Exemple : fr, en, es"
                ),
                "base_url": (
                    "Adresse complète où le site sera publié, sans slash final. "
                    "Sert à générer les liens absolus, le sitemap et le flux RSS.\n"
                    "Exemple : https://moncarnet.example.org"
                ),
                "author": (
                    "Nom affiché comme auteur du site (métadonnées, footer).\n"
                    "Exemple : Jeanne Dupont"
                ),
                "description": (
                    "Résumé en une phrase du contenu du site, utilisé pour le SEO "
                    "(balise meta description) et les aperçus de partage.\n"
                    "Exemple : Carnet de recherche sur les archives orales du XIXe siècle."
                ),
            },
        )
        self.notebook.add(self.site_tab, text="Site")

        self.banner_panel = BannerPanel(self.notebook, resolve_assets_root=self._resolve_assets_root)
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
            intro=(
                "Emplacements de tous les dossiers utilisés par le générateur. "
                "Les chemins sont relatifs à la « racine projet », sauf celle-ci qui peut être "
                "absolue. Ces dossiers n'ont pas besoin d'exister à l'avance : MEROPE les crée si besoin."
            ),
            help_texts={
                "project_root": (
                    "Dossier de base du projet : tous les autres chemins de cet onglet en "
                    "partent (sauf s'ils sont eux-mêmes absolus). Laissez « . » pour dire "
                    "« le dossier où se trouve le fichier de configuration ».\n"
                    "Exemple : . ou C:/Users/moi/mon-carnet"
                ),
                "content_dir": (
                    "Dossier qui regroupe l'ensemble du contenu source (pages + billets), "
                    "relatif à la racine projet.\n"
                    "Exemple : content"
                ),
                "pages_dir": (
                    "Dossier des pages statiques (à propos, contact...), généralement un "
                    "sous-dossier du dossier contenu.\n"
                    "Exemple : content/pages"
                ),
                "posts_dir": (
                    "Dossier des billets de blog (articles datés), généralement un "
                    "sous-dossier du dossier contenu.\n"
                    "Exemple : content/posts"
                ),
                "assets_dir": (
                    "Dossier des fichiers annexes à copier tels quels vers le site généré "
                    "(images, PDF, etc.).\n"
                    "Exemple : assets"
                ),
                "theme_dir": (
                    "Dossier du thème graphique (contient les templates et le CSS/JS).\n"
                    "Exemple : theme"
                ),
                "templates_dir": (
                    "Sous-dossier du thème contenant les fichiers de gabarit HTML "
                    "(page.html, post.html...).\n"
                    "Exemple : theme/templates"
                ),
                "xslt_dir": (
                    "Sous-dossier du thème contenant les feuilles de style XSLT utilisées "
                    "pour transformer le TEI en HTML.\n"
                    "Exemple : theme/xslt"
                ),
                "output_dir": (
                    "Dossier où le site HTML final est généré. Peut être nettoyé "
                    "automatiquement à chaque génération (voir onglet Génération).\n"
                    "Exemple : site"
                ),
                "tei_dir": (
                    "Dossier intermédiaire où les fichiers TEI (XML) générés depuis le "
                    "Markdown sont conservés, utile pour inspection/débogage.\n"
                    "Exemple : build/tei"
                ),
            },
            dir_fields={
                "project_root",
                "content_dir",
                "pages_dir",
                "posts_dir",
                "assets_dir",
                "theme_dir",
                "templates_dir",
                "xslt_dir",
                "output_dir",
                "tei_dir",
            },
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
            intro=(
                "Comment MEROPE doit lire et interpréter vos fichiers sources (Markdown) "
                "avant de les transformer en pages web."
            ),
            help_texts={
                "source_format": (
                    "Format des fichiers sources à importer. Actuellement seul le Markdown "
                    "est pris en charge.\n"
                    "Valeur attendue : markdown"
                ),
                "markdown_origin": (
                    "Outil d'où proviennent vos fichiers Markdown, pour adapter le nettoyage "
                    "et la conversion (ex. suppression des artefacts d'export Google Docs).\n"
                    "Exemple : google_docs_export"
                ),
                "default_page_layout": (
                    "Nom du template utilisé par défaut pour une page qui ne précise pas "
                    "de layout dans son en-tête (front matter).\n"
                    "Exemple : page (correspond à theme/templates/page.html)"
                ),
                "default_post_layout": (
                    "Nom du template utilisé par défaut pour un billet qui ne précise pas "
                    "de layout dans son en-tête (front matter).\n"
                    "Exemple : post (correspond à theme/templates/post.html)"
                ),
                "slugify_mode": (
                    "Méthode de fabrication des identifiants d'URL (slugs) à partir des "
                    "titres : « ascii » translittère les accents (é -> e) pour des URL "
                    "sans accents ni caractères spéciaux.\n"
                    "Exemple : ascii"
                ),
                "use_front_matter": (
                    "Si activé, MEROPE lit les métadonnées (titre, date, layout...) placées "
                    "en tête de chaque fichier Markdown, entre deux lignes « --- »."
                ),
                "copy_linked_assets": (
                    "Si activé, les images et fichiers référencés depuis vos billets/pages "
                    "sont automatiquement copiés dans le site généré."
                ),
            },
        )
        self.notebook.add(self.content_tab, text="Contenus")

        self.home_tab, self.home_vars = _create_form_tab(
            self.notebook,
            [
                ("source", "Source accueil", "content/pages/accueil.md"),
                ("layout", "Layout accueil", "home"),
            ],
            bool_fields=[
                ("enabled", "Activer accueil", True),
            ],
            intro="Configuration de la page d'accueil du site (index.html).",
            help_texts={
                "source": (
                    "Chemin (relatif à la racine projet) du fichier Markdown utilisé comme "
                    "contenu de la page d'accueil.\n"
                    "Exemple : content/pages/accueil.md"
                ),
                "layout": (
                    "Nom du template HTML utilisé pour la page d'accueil.\n"
                    "Exemple : home (correspond à theme/templates/home.html)"
                ),
                "enabled": "Si désactivé, aucune page d'accueil n'est générée.",
            },
            file_fields={"source": [("Markdown", "*.md")]},
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
            intro=(
                "Comportement de la section « blog » : liste chronologique des billets "
                "et page d'archive."
            ),
            help_texts={
                "posts_per_page": (
                    "Nombre de billets affichés par page d'archive avant pagination "
                    "(nombre entier).\n"
                    "Exemple : 10"
                ),
                "archive_title": (
                    "Titre affiché en haut de la page listant tous les billets.\n"
                    "Exemple : Billets"
                ),
                "archive_path": (
                    "Segment d'URL de la page d'archive, sans slash de début ni de fin.\n"
                    "Exemple : billets (donnera /billets/index.html)"
                ),
                "enabled": "Si désactivé, aucune page de blog ni d'archive n'est générée.",
                "generate_archive_page": (
                    "Si activé, une page listant tous les billets est générée à l'adresse "
                    "définie par « Chemin archive »."
                ),
                "sort_descending_by_date": (
                    "Si activé, les billets les plus récents apparaissent en premier "
                    "dans les listes (archive, accueil, RSS)."
                ),
            },
        )
        self.notebook.add(self.blog_tab, text="Blog")

        self.top_menu_editor = TopMenuEditor(self.notebook, get_content_targets=self._list_menu_link_targets)
        self.notebook.add(self.top_menu_editor, text="Menu supérieur")

        self.side_menu_editor = SideMenuEditor(self.notebook, get_content_targets=self._list_menu_link_targets)
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
            intro=(
                "Quels fichiers de thème utiliser pour transformer le contenu en pages HTML, "
                "et options d'affichage des images (lightbox)."
            ),
            help_texts={
                "theme_name": (
                    "Nom du thème actif, à titre indicatif/documentaire (n'affecte pas "
                    "directement les chemins, définis dans l'onglet Chemins).\n"
                    "Exemple : default"
                ),
                "html_template": (
                    "Nom de fichier du gabarit HTML utilisé pour les pages, cherché dans "
                    "le dossier templates (onglet Chemins).\n"
                    "Exemple : page.html"
                ),
                "post_template": (
                    "Nom de fichier du gabarit HTML utilisé pour les billets.\n"
                    "Exemple : post.html"
                ),
                "home_template": (
                    "Nom de fichier du gabarit HTML utilisé pour la page d'accueil.\n"
                    "Exemple : home.html"
                ),
                "tei_to_html_xslt": (
                    "Nom de fichier de la feuille XSLT qui transforme le TEI intermédiaire "
                    "en HTML, cherché dans le dossier XSLT (onglet Chemins).\n"
                    "Exemple : tei_to_html.xsl"
                ),
                "lightbox_engine": (
                    "Bibliothèque JavaScript utilisée pour agrandir les images cliquées.\n"
                    "Exemple : fancybox"
                ),
                "pretty_print_html": (
                    "Si activé, le HTML généré est indenté et lisible (plus volumineux mais "
                    "plus facile à relire/déboguer)."
                ),
                "generate_tei_files": (
                    "Si activé, les fichiers TEI intermédiaires sont conservés dans le "
                    "dossier TEI au lieu d'être supprimés après génération."
                ),
                "enable_lightbox": (
                    "Si activé, les images des articles s'ouvrent en grand dans une visionneuse "
                    "au clic plutôt que de simplement s'afficher en ligne."
                ),
            },
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
            intro="Contenu affiché en bas de chaque page du site.",
            help_texts={
                "text": (
                    "Texte libre affiché dans le pied de page (copyright, mentions légales...).\n"
                    "Exemple : © 2026 Jeanne Dupont — Tous droits réservés"
                ),
                "show_generation_info": (
                    "Si activé, une mention « généré avec MEROPE » est ajoutée dans le pied "
                    "de page."
                ),
                "show_last_build_date": (
                    "Si activé, la date de la dernière génération du site est affichée dans "
                    "le pied de page."
                ),
            },
        )
        self.notebook.add(self.footer_tab, text="Footer")

        self.build_tab, self.build_vars = _create_form_tab(
            self.notebook,
            [
                ("pandoc_command", "Commande pandoc", "pandoc"),
                ("search_excerpt_length", "Longueur de l'extrait de recherche (car.)", "160"),
            ],
            bool_fields=[
                ("clean_output_dir", "Nettoyer dossier de sortie", True),
                ("copy_assets", "Copier assets", True),
                ("fail_on_missing_assets", "Échouer si assets manquants", False),
                ("fail_on_invalid_config", "Échouer si config invalide", True),
                ("search_enabled", "Activer la recherche sur le site", True),
            ],
            intro=(
                "Réglages du processus de génération du site, déclenché via le menu "
                "Actions > Générer le site."
            ),
            help_texts={
                "pandoc_command": (
                    "Commande ou chemin complet vers l'exécutable Pandoc, utilisé pour "
                    "certaines conversions. Laissez « pandoc » si l'outil est déjà dans le "
                    "PATH du système.\n"
                    "Exemple : pandoc ou C:/Program Files/Pandoc/pandoc.exe"
                ),
                "clean_output_dir": (
                    "Si activé, le dossier de sortie (onglet Chemins) est entièrement vidé "
                    "avant chaque génération, pour éviter les fichiers obsolètes."
                ),
                "copy_assets": (
                    "Si activé, le dossier assets (onglet Chemins) est copié vers la sortie "
                    "à chaque génération."
                ),
                "fail_on_missing_assets": (
                    "Si activé, la génération s'arrête en erreur lorsqu'un fichier "
                    "(image, PDF...) référencé dans le contenu est introuvable. Si désactivé, "
                    "un avertissement est affiché mais la génération continue."
                ),
                "fail_on_invalid_config": (
                    "Si activé, la génération est bloquée tant que la configuration contient "
                    "des erreurs de validation (voir les messages d'erreur affichés)."
                ),
                "search_enabled": (
                    "Si activé, un index de recherche (JSON) est généré et une case de "
                    "recherche apparaît sur chaque page du site, permettant de retrouver "
                    "des pages/billets directement dans le navigateur (sans serveur)."
                ),
                "search_excerpt_length": (
                    "Nombre de caractères affichés sous chaque résultat de recherche.\n"
                    "Exemple : 160"
                ),
            },
        )
        self.notebook.add(self.build_tab, text="Génération")

    def _build_menu_bar(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Nouveau", command=self.new_config)
        file_menu.add_command(label="Nouveau projet...", command=self.new_project_dialog)
        file_menu.add_command(label="Charger JSON...", command=self.open_config_dialog, accelerator="Ctrl+O")
        file_menu.add_command(label="Enregistrer", command=self.save_config_dialog, accelerator="Ctrl+S")
        file_menu.add_command(
            label="Enregistrer sous...", command=self.save_config_as_dialog, accelerator="Ctrl+Shift+S"
        )
        file_menu.add_separator()
        file_menu.add_command(label="Quitter", command=self.destroy)

        actions_menu = tk.Menu(menu, tearoff=False)
        actions_menu.add_command(label="Générer le site", command=self.generate_site)
        actions_menu.add_command(label="Ouvrir dossier de sortie", command=self.stub_open_output)

        menu.add_cascade(label="Fichier", menu=file_menu)
        menu.add_cascade(label="Actions", menu=actions_menu)
        self.config(menu=menu)

        self.bind_all("<Control-o>", lambda _e: self.open_config_dialog())
        self.bind_all("<Control-s>", lambda _e: self.save_config_dialog())
        self.bind_all("<Control-S>", lambda _e: self.save_config_as_dialog())

    def _build_toolbar(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=8, pady=(8, 0))

        new_project_button = ttk.Button(
            toolbar, text="Nouveau projet...", command=self.new_project_dialog
        )
        new_project_button.pack(side="left", padx=(0, 6))
        add_tooltip(
            new_project_button,
            "Crée un nouveau dossier de projet tout équipé : structure de dossiers, "
            "une page et un billet de bienvenue, et une configuration prête à l'emploi. "
            "Vous pourrez ensuite changer les dossiers librement dans l'onglet Chemins.",
        )

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=6)

        load_button = ttk.Button(toolbar, text="Charger...", command=self.open_config_dialog)
        load_button.pack(side="left", padx=(0, 6))
        add_tooltip(
            load_button,
            "Ouvre un fichier de configuration JSON existant et remplit le formulaire "
            "avec son contenu.",
        )

        save_button = ttk.Button(toolbar, text="Enregistrer", command=self.save_config_dialog)
        save_button.pack(side="left", padx=(0, 6))
        add_tooltip(
            save_button,
            "Enregistre la configuration actuelle dans le fichier JSON en cours "
            "(demande un emplacement si aucun fichier n'est encore défini).",
        )

        save_as_button = ttk.Button(
            toolbar, text="Enregistrer sous...", command=self.save_config_as_dialog
        )
        save_as_button.pack(side="left", padx=(0, 6))
        add_tooltip(
            save_as_button,
            "Enregistre la configuration actuelle dans un nouveau fichier JSON, "
            "en demandant toujours l'emplacement.",
        )

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=6)

        editor_button = ttk.Button(
            toolbar, text="Éditeur de contenu...", command=self.open_content_editor
        )
        editor_button.pack(side="left", padx=(0, 6))
        add_tooltip(
            editor_button,
            "Ouvre l'éditeur pour rédiger ou modifier des pages et des billets "
            "directement, sans quitter MEROPE.",
        )

        generate_button = ttk.Button(toolbar, text="Générer le site", command=self.generate_site)
        generate_button.pack(side="left", padx=(0, 6))
        add_tooltip(
            generate_button,
            "Construit le site HTML à partir de la configuration actuelle et du "
            "contenu présent dans les dossiers configurés (équivalent à Actions > "
            "Générer le site).",
        )

        publish_button = ttk.Button(
            toolbar, text="Publier (FTP)...", command=self.publish_site_ftp
        )
        publish_button.pack(side="left")
        add_tooltip(
            publish_button,
            "Transfère le site déjà généré vers un serveur distant par FTP ou "
            "FTPS. Le site doit avoir été généré au préalable avec « Générer "
            "le site ».",
        )

    def new_config(self) -> None:
        self.current_config_path = None
        self._load_into_form(build_default_config())
        self._set_path_label()

    def new_project_dialog(self) -> None:
        directory = filedialog.askdirectory(title="Choisir le dossier du nouveau projet")
        if not directory:
            return

        root = Path(directory)
        if any(root.iterdir()) and not messagebox.askyesno(
            "Nouveau projet",
            f"Le dossier « {root} » n'est pas vide. Créer le projet ici quand même ?",
        ):
            return

        try:
            config_path = create_new_project(root)
            config = load_config(config_path)
        except (ConfigValidationError, OSError, ValueError) as exc:
            messagebox.showerror("Nouveau projet", f"Impossible de créer le projet :\n{exc}")
            return

        self.current_config_path = config_path
        self._load_into_form(config)
        self._set_path_label()
        messagebox.showinfo(
            "Nouveau projet",
            f"Projet créé dans {root}.\n\nUne page et un billet de bienvenue ont été "
            "ajoutés pour vous aider à démarrer.",
        )

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
            self.save_config_as_dialog()
            return
        self._write_config_to(self.current_config_path)

    def save_config_as_dialog(self) -> None:
        destination = filedialog.asksaveasfilename(
            title="Enregistrer la configuration sous...",
            defaultextension=".json",
            initialfile=self.current_config_path.name if self.current_config_path else "config.json",
            filetypes=[("JSON", "*.json"), ("Tous les fichiers", "*.*")],
        )
        if not destination:
            return
        self._write_config_to(Path(destination))

    def _write_config_to(self, destination: Path) -> None:
        try:
            config = self._collect_from_form()
            errors = validate_config_model(config)
            if errors:
                raise ConfigValidationError(errors)
            save_config(config, destination)
        except (ConfigValidationError, OSError, ValueError) as exc:
            messagebox.showerror("Erreur", f"Enregistrement impossible:\n{exc}")
            return

        self.current_config_path = destination
        self._set_path_label()
        messagebox.showinfo("Configuration", "Configuration enregistrée.")

    def generate_site(self) -> None:
        try:
            config = self._collect_from_form()
            errors = validate_config_model(config)
            if errors:
                raise ConfigValidationError(errors)
            report = build_site(config, config_path=self.current_config_path)
        except (ConfigValidationError, OSError, ValueError) as exc:
            messagebox.showerror("Erreur de génération", str(exc))
            return

        details = format_build_report(report)
        if not report.success:
            messagebox.showerror("Génération échouée", details)
            return

        title = "Génération terminée (avec avertissements)" if report.warnings else "Génération terminée"
        prompt = f"{details}\n\nOuvrir le site dans le navigateur ?"
        if messagebox.askyesno(title, prompt):
            self._open_site_in_browser(report.output_dir)

    def _open_site_in_browser(self, output_dir: Path) -> None:
        try:
            self._site_preview_server.open_in_browser(output_dir)
        except OSError as exc:
            messagebox.showerror(
                "Aperçu du site",
                f"Impossible de démarrer le serveur local pour l'aperçu :\n{exc}",
            )

    def publish_site_ftp(self) -> None:
        try:
            config = self._collect_from_form()
            errors = validate_config_model(config)
            if errors:
                raise ConfigValidationError(errors)
        except (ConfigValidationError, OSError, ValueError) as exc:
            messagebox.showerror("Erreur de configuration", str(exc))
            return

        project_root = resolve_project_root(config, self.current_config_path)
        output_dir = (project_root / config.paths.output_dir).resolve()
        if not output_dir.is_dir() or not any(output_dir.iterdir()):
            messagebox.showwarning(
                "Publier le site",
                "Aucun site généré n'a été trouvé. Utilisez d'abord « Générer le "
                "site », puis publiez-le.",
            )
            return

        def on_ftp_config_changed(ftp_config: FtpConfig) -> None:
            self._ftp_config = ftp_config
            if self.current_config_path is not None:
                try:
                    save_config(self._collect_from_form(), self.current_config_path)
                except (ConfigValidationError, OSError, ValueError):
                    pass

        FtpPublishDialog(
            self,
            ftp_config=self._ftp_config,
            output_dir=output_dir,
            on_config_changed=on_ftp_config_changed,
        )

    def _list_menu_link_targets(self) -> list[tuple[str, str]]:
        """Fresh (label, url) pairs for the menu-entry dialog's internal-link
        picker, re-scanned on every call since the Paths/Blog tabs can change
        at any time (unlike ``ContentEditorWindow``, these editors are built
        once at startup, not on demand)."""
        paths = PathsConfig(**_read_vars(self.paths_vars))
        project_root = resolve_project_root(ProjectConfig(paths=paths), self.current_config_path)
        pages_dir = (project_root / paths.pages_dir).resolve()
        posts_dir = (project_root / paths.posts_dir).resolve()
        archive_path = self.blog_vars["archive_path"].get().strip() or "billets"
        return list_content_targets(pages_dir, posts_dir, archive_path=archive_path)

    def _resolve_assets_root(self) -> tuple[Path, str]:
        """(project_root, assets_dir) for the banner picker's "copy into the
        project" step — resolved lazily (see ``BannerPanel``), same pattern
        as ``_list_menu_link_targets``.
        """
        paths = PathsConfig(**_read_vars(self.paths_vars))
        project_root = resolve_project_root(ProjectConfig(paths=paths), self.current_config_path)
        return project_root, paths.assets_dir

    def open_content_editor(self) -> None:
        paths = PathsConfig(**_read_vars(self.paths_vars))
        project_root = resolve_project_root(ProjectConfig(paths=paths), self.current_config_path)
        pages_dir = (project_root / paths.pages_dir).resolve()
        posts_dir = (project_root / paths.posts_dir).resolve()
        images_dir = (project_root / self.media_panel.images_dir_var.get()).resolve()
        slugify_mode = self.content_vars["slugify_mode"].get().strip() or "ascii"

        ContentEditorWindow(
            self,
            pages_dir=pages_dir,
            posts_dir=posts_dir,
            images_dir=images_dir,
            slugify_mode=slugify_mode,
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
        self.side_menu_editor.set_title(config.menus.side_title)
        _set_vars(self.render_vars, config.render)
        self.media_panel.set_data(config.media_handling)
        self.notes_panel.set_data(config.notes_rendering)
        _set_vars(self.footer_vars, config.footer)
        _set_vars_partial(self.build_vars, config.build)
        self.build_vars["search_enabled"].set(config.search.enabled)
        self.build_vars["search_excerpt_length"].set(str(config.search.excerpt_length))
        self._ftp_config = config.ftp

    def _collect_from_form(self) -> ProjectConfig:
        site = SiteConfig(**_read_vars(self.site_vars))
        paths = PathsConfig(**_read_vars(self.paths_vars))
        content = ContentConfig(**_read_vars(self.content_vars))

        home_raw = _read_vars(self.home_vars)
        home = HomeConfig(**home_raw)

        blog_raw = _read_vars(self.blog_vars)
        blog_raw["posts_per_page"] = int(blog_raw["posts_per_page"])
        blog = BlogConfig(**blog_raw)

        menus = MenusConfig(
            top=self.top_menu_editor.get_items(),
            side=self.side_menu_editor.get_sections(),
            side_title=self.side_menu_editor.get_title(),
        )

        render = RenderConfig(**_read_vars(self.render_vars))
        footer = FooterConfig(**_read_vars(self.footer_vars))

        build_raw = _read_vars(self.build_vars)
        search = SearchConfig(
            enabled=bool(build_raw.pop("search_enabled")),
            excerpt_length=int(build_raw.pop("search_excerpt_length")),
        )
        build = BuildConfig(**build_raw)

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
            search=search,
            ftp=self._ftp_config,
        )


_FIELD_WIDTH = 55  # caractères : évite que les champs ne s'étirent à l'infini quand la fenêtre s'agrandit


def _create_form_tab(
    notebook: ttk.Notebook,
    text_fields: list[tuple[str, str, str]],
    bool_fields: list[tuple[str, str, bool]] | None = None,
    intro: str | None = None,
    help_texts: dict[str, str] | None = None,
    dir_fields: set[str] | None = None,
    file_fields: dict[str, list[tuple[str, str]]] | None = None,
) -> tuple[ttk.Frame, dict[str, tk.Variable]]:
    """Build a simple grid form tab.

    ``dir_fields`` marks field names that get a "Parcourir..." button opening a
    folder picker. ``file_fields`` marks field names that get a button opening
    a file picker, mapped to the filetypes list passed to the dialog.
    """
    frame = ttk.Frame(notebook)
    vars_map: dict[str, tk.Variable] = {}
    help_texts = help_texts or {}
    dir_fields = dir_fields or set()
    file_fields = file_fields or {}

    row = 0
    if intro:
        ttk.Label(
            frame, text=intro, wraplength=680, justify="left", foreground="#444444"
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=8, pady=(4, 10))
        row += 1

    for field_name, label, default in text_fields:
        var = tk.StringVar(value=default)
        vars_map[field_name] = var
        label_widget = ttk.Label(frame, text=label)
        label_widget.grid(row=row, column=0, sticky="w", padx=8, pady=4)
        entry = ttk.Entry(frame, textvariable=var, width=_FIELD_WIDTH)
        entry.grid(row=row, column=1, sticky="w", padx=8, pady=4)
        help_text = help_texts.get(field_name)
        if help_text:
            add_tooltip(label_widget, help_text)
            add_tooltip(entry, help_text)
        if field_name in dir_fields:
            browse = ttk.Button(
                frame, text="Parcourir...", command=lambda v=var: _browse_directory(v)
            )
            browse.grid(row=row, column=2, sticky="w", padx=(0, 8), pady=4)
            add_tooltip(browse, "Ouvre un sélecteur pour choisir un dossier existant sur le disque.")
        elif field_name in file_fields:
            filetypes = file_fields[field_name]
            browse = ttk.Button(
                frame, text="Parcourir...", command=lambda v=var, ft=filetypes: _browse_file(v, ft)
            )
            browse.grid(row=row, column=2, sticky="w", padx=(0, 8), pady=4)
            add_tooltip(browse, "Ouvre un sélecteur pour choisir un fichier existant sur le disque.")
        row += 1

    if bool_fields:
        for field_name, label, default in bool_fields:
            var = tk.BooleanVar(value=default)
            vars_map[field_name] = var
            checkbutton = ttk.Checkbutton(frame, text=label, variable=var)
            checkbutton.grid(row=row, column=0, columnspan=2, sticky="w", padx=8, pady=4)
            help_text = help_texts.get(field_name)
            if help_text:
                add_tooltip(checkbutton, help_text)
            row += 1

    frame.grid_columnconfigure(3, weight=1)
    return frame, vars_map


def _browse_directory(var: tk.StringVar) -> None:
    selected = filedialog.askdirectory(title="Choisir un dossier", initialdir=var.get() or ".")
    if selected:
        var.set(selected)


def _browse_file(var: tk.StringVar, filetypes: list[tuple[str, str]]) -> None:
    selected = filedialog.askopenfilename(
        title="Choisir un fichier",
        initialdir=Path(var.get()).parent if var.get() else ".",
        filetypes=[*filetypes, ("Tous les fichiers", "*.*")],
    )
    if selected:
        var.set(selected)


def _set_vars(vars_map: dict[str, tk.Variable], source: object) -> None:
    for field_name, var in vars_map.items():
        value = getattr(source, field_name)
        var.set(value)


def _set_vars_partial(vars_map: dict[str, tk.Variable], source: object) -> None:
    """Like ``_set_vars``, but silently skips keys not present on ``source``.

    Used for form tabs that mix fields from more than one config dataclass
    (e.g. the "Génération" tab combines ``BuildConfig`` and ``SearchConfig``).
    """
    for field_name, var in vars_map.items():
        if not hasattr(source, field_name):
            continue
        var.set(getattr(source, field_name))


def _read_vars(vars_map: dict[str, tk.Variable]) -> dict[str, object]:
    return {field_name: variable.get() for field_name, variable in vars_map.items()}
