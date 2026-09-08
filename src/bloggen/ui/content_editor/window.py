"""The content editor window: assembles all the mixins below into the
single ``ContentEditorWindow`` class, owns widget construction, and wires
keyboard shortcuts to the methods each mixin provides.
"""

from __future__ import annotations

from pathlib import Path
from tkinter import font as tkfont, ttk
import tkinter as tk
from typing import Callable, TYPE_CHECKING

from bloggen.markdown.rich_text_model import InlineRun
from bloggen.ui import toolbar_icons
from bloggen.ui.tooltip import add_tooltip

from . import undo_redo
from .autosave import AutosaveMixin
from .blocks import BlocksMixin
from .dialogs import FindReplaceDialog
from .file_ops import FileOpsMixin
from .find_replace import FindReplaceMixin
from .formatting import FormattingMixin
from .notes import NotesMixin
from .paste import PasteMixin
from .preview import PreviewMixin
from .typography import TypographyMixin
from .undo_redo import UndoRedoMixin

if TYPE_CHECKING:
    from bloggen.config.models import ProjectConfig


class ContentEditorWindow(
    AutosaveMixin,
    PreviewMixin,
    UndoRedoMixin,
    FindReplaceMixin,
    NotesMixin,
    TypographyMixin,
    PasteMixin,
    FileOpsMixin,
    FormattingMixin,
    BlocksMixin,
    tk.Toplevel,
):
    """WYSIWYG content editor: create/edit pages and posts as real Markdown
    files.

    The Tk ``Text`` widget only ever holds display text plus tags; all
    Markdown knowledge lives in :mod:`bloggen.markdown.rich_text_model`,
    :mod:`bloggen.markdown.rich_text_export` and
    :mod:`bloggen.markdown.rich_text_import`. This class (spread across the
    mixins above by concern — autosave, undo/redo, notes, typography,
    paste, file operations, formatting commands, and the Block/InlineRun
    bridge) is the thin bridge between the two: it walks the widget's tags
    to build a ``Block`` list on save, and walks a ``Block`` list to
    populate the widget on load.
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        pages_dir: Path,
        posts_dir: Path,
        images_dir: Path,
        slugify_mode: str,
        project_root: Path | None = None,
        get_config: Callable[[], "ProjectConfig | None"] | None = None,
    ) -> None:
        super().__init__(master)
        self.title("Éditeur de contenu")
        self.geometry("1200x760")

        self.pages_dir = Path(pages_dir)
        self.posts_dir = Path(posts_dir)
        self.images_dir = Path(images_dir)
        self.slugify_mode = slugify_mode
        # Falls back to pages_dir's grandparent (content/pages -> project
        # root) when not given explicitly — matches every caller's actual
        # layout without forcing one on callers that don't care (tests).
        self.project_root = Path(project_root) if project_root is not None else self.pages_dir.parent.parent

        self.current_path: Path | None = None
        self.current_kind: str | None = None
        self.metadata: dict[str, str] = {}
        self.footnote_definitions: dict[str, list[InlineRun]] = {}
        self.link_data: dict[str, str] = {}
        self.footnote_ref_data: dict[str, str] = {}
        self._tag_counter = 0
        self._file_entries: list[tuple[str, Path]] = []  # (kind, path)
        self._note_link_data: dict[str, str] = {}
        self._footnote_text_widgets: dict[str, tk.Text] = {}
        self._footnote_rows: dict[str, ttk.Frame] = {}
        self._note_font_refs: list[tkfont.Font] = []
        self._quote_parity_opening = True
        self._note_quote_parity: dict[str, bool] = {}
        # Tk garbage-collects a PhotoImage/Font once its last Python
        # reference disappears, even though the button still displays it —
        # toolbar icons and their bold/italic/strikethrough label fonts are
        # kept alive here for the editor window's lifetime.
        self._toolbar_icon_refs: list[tk.PhotoImage] = []
        self._toolbar_fonts: list[tkfont.Font] = []
        self._char_format_vars: dict[str, tk.BooleanVar] = {}
        self._block_format_vars: dict[str, tk.BooleanVar] = {}
        self._find_dialog: FindReplaceDialog | None = None

        # -- unified undo/redo (see _on_text_modified / _perform_undo) -----
        # Tk's own ``-undo`` mechanism only tracks insert/delete, never
        # tag_add/tag_remove — so a pure formatting change (bold, heading,
        # alignment...) is otherwise silently impossible to undo. This
        # stack sits alongside Tk's, recording either an opaque "text"
        # marker (delegated to text.edit_undo/edit_redo) or an explicit
        # ("format", undo_fn, redo_fn) entry pushed by the formatting
        # toggles below, so Ctrl+Z/Ctrl+Y walk both kinds of change in the
        # single chronological order the user actually made them.
        self._undo_stack: list[tuple] = []
        self._redo_stack: list[tuple] = []
        self._current_edit_kind: str | None = None
        self._last_char_count = 0
        self._suppress_undo_tracking = False
        self._dirty = False
        self._autosave_after_id: str | None = None
        self._init_preview(get_config)

        self._build_ui()
        self._refresh_file_list()
        self.protocol("WM_DELETE_WINDOW", self._on_close_request)
        self._offer_crash_recovery()
        self._schedule_autosave()

        # Every stdlib dialog this editor opens (simpledialog.askstring,
        # messagebox, filedialog, ContentMetadataDialog — all built on
        # tkinter.simpledialog.Dialog) hands keyboard focus back to
        # *this* Toplevel when it closes: Dialog.cancel() calls
        # ``self.parent.focus_set()``, and the parent passed everywhere
        # is this window, never ``self.text`` itself. Tk then has no
        # focused text widget at all, so the blinking insertion caret
        # simply stops being drawn anywhere — it looks like the cursor
        # vanished, "randomly" from the user's point of view since it's
        # only ever noticed a moment after closing some unrelated dialog
        # (insert link/image/note, metadata, an error popup...). Catch
        # that hand-back and redirect it to the text widget, which is
        # where editing resumes in the vast majority of cases; call
        # sites that want a different widget focused (e.g. a footnote's
        # own editor) explicitly focus_set() it afterwards, which wins
        # since it runs after this redirect.
        self.bind("<FocusIn>", self._on_toplevel_focus_in)
        self.text.focus_set()

    def _on_toplevel_focus_in(self, event: tk.Event) -> None:
        if event.widget is self:
            self.text.focus_set()

    # -- autosave / crash recovery ------------------------------------------

    def _build_ui(self) -> None:
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        left = ttk.Frame(paned)
        paned.add(left, weight=1)
        self._build_file_list(left)

        right = ttk.Frame(paned)
        paned.add(right, weight=4)
        self._build_editor(right)

    def _build_file_list(self, master: tk.Misc) -> None:
        ttk.Label(
            master,
            text="Pages et billets existants. Double-cliquez pour ouvrir.",
            wraplength=220,
            justify="left",
        ).pack(fill="x", pady=(0, 6))

        self.file_listbox = tk.Listbox(master, exportselection=False)
        self.file_listbox.pack(fill="both", expand=True)
        self.file_listbox.bind("<Double-Button-1>", lambda _e: self._open_selected())

        buttons = [
            ("Nouvelle page", lambda: self._new_document("page"), "Crée une page vierge."),
            ("Nouveau billet", lambda: self._new_document("post"), "Crée un billet vierge."),
            ("Ouvrir", self._open_selected, "Ouvre le fichier sélectionné dans la liste."),
            (
                "Importer...",
                self._import_markdown_file,
                "Importe un fichier Markdown existant (venant d'ailleurs que ce projet) "
                "dans l'éditeur, pour compléter ses métadonnées et l'enregistrer ici.",
            ),
            (
                "Convertir en page/billet",
                self._convert_selected_kind,
                "Transforme le fichier sélectionné de page en billet (ou l'inverse) : le "
                "déplace vers le bon dossier, ajuste son nom de fichier (les billets sont "
                "préfixés par leur date) et met à jour son type dans le front matter. "
                "L'URL du contenu change en conséquence — les liens existants vers "
                "l'ancienne adresse ne sont pas mis à jour automatiquement.",
            ),
            ("Supprimer", self._delete_selected, "Supprime définitivement le fichier sélectionné."),
            ("Actualiser", self._refresh_file_list, "Recharge la liste depuis le disque."),
        ]
        for label, command, tip in buttons:
            button = ttk.Button(master, text=label, command=command)
            button.pack(fill="x", pady=2)
            add_tooltip(button, tip)

    def _build_editor(self, master: tk.Misc) -> None:
        toolbar_row1 = ttk.Frame(master)
        toolbar_row1.pack(fill="x", pady=(0, 2))
        toolbar_row2 = ttk.Frame(master)
        toolbar_row2.pack(fill="x", pady=(0, 4))

        toolbar_icons.configure_colors(
            self._resolve_color("SystemButtonFace", "#f0f0f0"),
            self._resolve_color("SystemButtonText", "#1e1e1e"),
        )

        # Bold/italic/strikethrough keep their existing single-letter labels
        # (French initials: G-ras, I-talique, S-barré) but rendered in the
        # style they apply, same convention as Word's B/I/U buttons — no
        # icon reads as clearly as the real thing.
        default_font = tkfont.nametofont("TkDefaultFont")
        bold_font = tkfont.Font(
            family=default_font.cget("family"), size=default_font.cget("size"), weight="bold"
        )
        italic_font = tkfont.Font(
            family=default_font.cget("family"), size=default_font.cget("size"), slant="italic"
        )
        strike_font = tkfont.Font(
            family=default_font.cget("family"), size=default_font.cget("size"), overstrike=1
        )
        self._toolbar_fonts.extend([bold_font, italic_font, strike_font])
        # ttk widgets take their font from a named style, not a direct
        # "font" option (unlike classic tk.Button) — one throwaway style
        # per button is the simplest way to give each its own font.
        style = ttk.Style(self)
        style.configure("ToolbarBold.Toolbutton", font=bold_font)
        style.configure("ToolbarItalic.Toolbutton", font=italic_font)
        style.configure("ToolbarStrike.Toolbutton", font=strike_font)

        char_buttons = [
            ("G", "bold", "ToolbarBold.Toolbutton", "Gras (Ctrl+B)."),
            ("I", "italic", "ToolbarItalic.Toolbutton", "Italique (Ctrl+I)."),
            ("S", "strike", "ToolbarStrike.Toolbutton", "Barré (Ctrl+Maj+S)."),
            (
                "x²",
                "superscript",
                "Toolbutton",
                "Exposant (ex. 2e, XXe, notes de calcul). Raccourci : Ctrl+Maj+= (Ctrl++).",
            ),
        ]
        # Checkbuttons styled as "Toolbutton" (a themed ttk style that reads
        # as a flat toggle) rather than plain Buttons, so each one visually
        # reflects whether the selection/cursor already carries that
        # formatting — kept in sync by :meth:`_update_toolbar_char_state`.
        for label, tag, button_style, tip in char_buttons:
            var = tk.BooleanVar(value=False)
            self._char_format_vars[tag] = var
            b = ttk.Checkbutton(
                toolbar_row1,
                text=label,
                width=3,
                style=button_style,
                variable=var,
                command=lambda t=tag: self._activate_char_format(t),
            )
            b.pack(side="left", padx=1)
            add_tooltip(b, tip)

        ttk.Separator(toolbar_row1, orient="vertical").pack(side="left", fill="y", padx=4)

        for level in range(1, 5):
            tag = f"h{level}"
            var = tk.BooleanVar(value=False)
            self._block_format_vars[tag] = var
            # Checkbutton like the char-format buttons above, so it lights
            # up when the cursor sits on a line already at that heading
            # level — kept in sync by :meth:`_update_toolbar_block_state`.
            b = ttk.Checkbutton(
                toolbar_row1,
                text=f"H{level}",
                width=3,
                style="Toolbutton",
                variable=var,
                command=lambda t=tag: self._activate_block_format(t),
            )
            b.pack(side="left", padx=1)
            add_tooltip(b, f"Titre de niveau {level} pour la ligne courante.")

        p_button = ttk.Button(toolbar_row1, text="P", width=3, command=self._set_paragraph_normal)
        p_button.pack(side="left", padx=1)
        add_tooltip(
            p_button,
            "Paragraphe normal : retire la mise en forme de titre, citation ou liste "
            "de la ligne courante (ou de la sélection) pour revenir à un paragraphe "
            "simple.",
        )

        ttk.Separator(toolbar_row1, orient="vertical").pack(side="left", fill="y", padx=4)

        blockquote_icon = toolbar_icons.icon_blockquote()
        self._toolbar_icon_refs.append(blockquote_icon)
        blockquote_var = tk.BooleanVar(value=False)
        self._block_format_vars["blockquote"] = blockquote_var
        blockquote_button = ttk.Checkbutton(
            toolbar_row1,
            image=blockquote_icon,
            style="Toolbutton",
            variable=blockquote_var,
            command=lambda: self._activate_block_format("blockquote"),
        )
        blockquote_button.pack(side="left", padx=1)
        add_tooltip(blockquote_button, "Citation : transforme la ligne en citation.")

        list_buttons = [
            (
                toolbar_icons.icon_bullet_list(),
                lambda: self._toggle_line_tag("bullet_item"),
                "Liste à puces : transforme la ligne en élément de liste à puces.",
            ),
            (
                toolbar_icons.icon_ordered_list(),
                lambda: self._toggle_line_tag("ordered_item"),
                "Liste numérotée : transforme la ligne en élément de liste numérotée.",
            ),
        ]
        for icon, command, tip in list_buttons:
            self._toolbar_icon_refs.append(icon)
            b = ttk.Button(toolbar_row1, image=icon, command=command)
            b.pack(side="left", padx=1)
            add_tooltip(b, tip)

        ttk.Separator(toolbar_row1, orient="vertical").pack(side="left", fill="y", padx=4)

        align_buttons = [
            (toolbar_icons.icon_align_left(), "left", "Aligne le paragraphe à gauche (par défaut)."),
            (toolbar_icons.icon_align_center(), "center", "Centre le paragraphe."),
            (toolbar_icons.icon_align_right(), "right", "Aligne le paragraphe à droite."),
            (
                toolbar_icons.icon_align_justify(),
                "justify",
                "Justifié : texte étiré pour toucher les deux marges. "
                "Rendu réel uniquement sur le site généré : l'aperçu dans cet éditeur "
                "affiche un alignement à gauche par simplification. "
                "Raccourci : Alt+J (bascule entre gauche et justifié, comme sous WordPress).",
            ),
        ]
        for icon, alignment, tip in align_buttons:
            self._toolbar_icon_refs.append(icon)
            b = ttk.Button(toolbar_row1, image=icon, command=lambda a=alignment: self._set_alignment(a))
            b.pack(side="left", padx=1)
            add_tooltip(b, tip)

        insert_buttons = [
            (
                "␣",
                None,
                self._insert_nbsp,
                "Espace insécable : insère une espace insécable au curseur (empêche la "
                "coupure entre deux mots, ex. avant « : » ou dans « 10 km »). Déjà posée "
                "automatiquement par la typographie française avant ; : ! ? et dans les "
                "guillemets. Raccourci : Alt+Espace.",
            ),
            (None, toolbar_icons.icon_link(), self._insert_link, "Lien : transforme la sélection en lien hypertexte."),
            (None, toolbar_icons.icon_image(), self._insert_image, "Image : insère une image depuis un fichier existant."),
            (
                "📋",
                None,
                self._paste_image_button,
                "Coller une image : insère l'image actuellement dans le presse-papiers "
                "(capture d'écran, image copiée depuis un navigateur ou l'Explorateur...), "
                "centrée et redimensionnée pour un affichage immédiat. "
                "Raccourci : Ctrl+V (avec le curseur dans le texte).",
            ),
            (
                "📄",
                None,
                self._paste_as_plain_text,
                "Coller en texte brut : insère le texte du presse-papiers sans sa mise en "
                "forme (gras, liens, tableaux...), utile pour coller depuis Word/un "
                "navigateur sans en récupérer le style. Raccourci : Ctrl+Maj+V.",
            ),
            (None, toolbar_icons.icon_table(), self._insert_table, "Tableau : insère un tableau simple."),
            ("†", None, self._insert_footnote, "Note : insère une note de bas de page."),
        ]
        for label, icon, command, tip in insert_buttons:
            if icon is not None:
                self._toolbar_icon_refs.append(icon)
                b = ttk.Button(toolbar_row2, image=icon, command=command)
            else:
                b = ttk.Button(toolbar_row2, text=label, width=3, command=command)
            b.pack(side="left", padx=1)
            add_tooltip(b, tip)

        ttk.Separator(toolbar_row2, orient="vertical").pack(side="left", fill="y", padx=4)

        typo_button = ttk.Button(
            toolbar_row2, text="Aa", width=3, command=self._apply_typography_to_selection
        )
        typo_button.pack(side="left", padx=1)
        add_tooltip(
            typo_button,
            "Corriger la typographie : applique aux guillemets et à la ponctuation "
            "double ( ; : ! ? ) de la sélection les mêmes règles typographiques que la "
            "saisie en direct (guillemets français, espaces insécables). Utile après un "
            "collage. La mise en forme (gras, italique, citations...) de la sélection "
            "est conservée.",
        )

        ttk.Separator(toolbar_row2, orient="vertical").pack(side="left", fill="y", padx=4)

        find_button = ttk.Button(toolbar_row2, text="🔍", width=3, command=self._open_find)
        find_button.pack(side="left", padx=1)
        add_tooltip(find_button, "Rechercher (Ctrl+F).")

        replace_button = ttk.Button(toolbar_row2, text="🔍↔", width=4, command=self._open_replace)
        replace_button.pack(side="left", padx=1)
        add_tooltip(replace_button, "Rechercher et remplacer (Ctrl+H).")

        ttk.Separator(toolbar_row2, orient="vertical").pack(side="left", fill="y", padx=4)

        meta_button = ttk.Button(toolbar_row2, text="⚙", width=3, command=self._edit_metadata)
        meta_button.pack(side="left", padx=1)
        add_tooltip(meta_button, "Métadonnées : titre, slug, date, auteur, description...")

        save_icon = toolbar_icons.icon_save()
        self._toolbar_icon_refs.append(save_icon)
        save_button = ttk.Button(
            toolbar_row2, text="Enregistrer", image=save_icon, compound="left", command=self._save
        )
        save_button.pack(side="right", padx=1)
        add_tooltip(save_button, "Enregistrer : écrit ce contenu dans son fichier Markdown.")

        self._preview_live_var = tk.BooleanVar(value=False)
        live_preview_check = ttk.Checkbutton(
            toolbar_row2,
            text="Aperçu en direct",
            variable=self._preview_live_var,
            command=self._toggle_live_preview,
        )
        live_preview_check.pack(side="right", padx=(4, 8))
        add_tooltip(
            live_preview_check,
            "Régénère automatiquement l'aperçu HTML quelques instants après chaque "
            "modification. Nécessite pywebview (voir le bouton « Aperçu » si absent).",
        )

        preview_button = ttk.Button(toolbar_row2, text="Aperçu", command=self._show_preview)
        preview_button.pack(side="right", padx=1)
        add_tooltip(
            preview_button,
            "Aperçu HTML : ouvre (ou rafraîchit) une fenêtre montrant ce contenu rendu "
            "comme sur le site publié, sans rien écrire dans le dossier de sortie réel.",
        )

        vertical_paned = ttk.PanedWindow(master, orient="vertical")
        vertical_paned.pack(fill="both", expand=True)

        text_frame = ttk.Frame(vertical_paned)
        vertical_paned.add(text_frame, weight=5)
        self.text = tk.Text(
            # Live attribute access (not a plain value-copying import) so a
            # test can monkeypatch undo_redo._MAX_UNDO_HISTORY and have it
            # actually take effect here too — see that module's own comment.
            text_frame,
            wrap="word",
            undo=True,
            maxundo=undo_redo._MAX_UNDO_HISTORY,
            font=("TkDefaultFont", 11),
        )
        # Clicking a toolbar button moves keyboard focus away from the text
        # widget, and Tk's default "inactiveselectbackground" is pale/absent
        # on most themes — the selection is still there, it just visually
        # looks deselected right when the user applies a format to it. Keep
        # it exactly as visible whether or not the widget has focus.
        self.text.configure(inactiveselectbackground=self.text.cget("selectbackground"))
        text_scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=text_scrollbar.set)
        text_scrollbar.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        add_tooltip(text_scrollbar, "Fait défiler le texte vers le haut ou le bas.")
        add_tooltip(
            self.text,
            "Ctrl+molette : agrandit/réduit le texte et les notes. "
            "Raccourcis : Ctrl+B (gras), Ctrl+I (italique), Ctrl+Maj+S (barré), "
            "Ctrl+Maj+= (exposant), Alt+Espace (espace insécable), "
            "Alt+J (bascule gauche/justifié).",
        )
        self._configure_tags()
        self._init_zoom()
        self.text.bind("<KeyRelease>", self._on_key_release, add="+")
        self.text.bind("<<Modified>>", self._on_text_modified)
        self.text.bind("<<Modified>>", self._mark_preview_stale, add="+")
        self.text.bind("<<Paste>>", self._on_paste)
        self.text.bind("<Control-Shift-V>", self._shortcut_paste_plain)
        self.text.bind("<ButtonRelease-1>", self._update_toolbar_char_state, add="+")
        self.text.bind("<ButtonRelease-1>", self._update_toolbar_block_state, add="+")
        self.text.bind("<Control-MouseWheel>", self._on_ctrl_mousewheel)
        self.text.bind("<Control-b>", self._shortcut_bold)
        self.text.bind("<Control-i>", self._shortcut_italic)
        self.text.bind("<Control-Shift-S>", self._shortcut_strike)
        self.text.bind("<Control-plus>", self._shortcut_superscript)
        self.text.bind("<Alt-space>", self._shortcut_nbsp)
        self.text.bind("<Alt-j>", self._shortcut_toggle_justify)
        self.text.bind("<Control-f>", self._shortcut_find)
        self.text.bind("<Control-h>", self._shortcut_replace)
        self.text.bind("<Control-z>", self._shortcut_undo)
        self.text.bind("<Control-y>", self._shortcut_redo)
        self.text.bind("<Control-Shift-Z>", self._shortcut_redo)
        self.bind("<Control-f>", self._shortcut_find)
        self.bind("<Control-h>", self._shortcut_replace)

        notes_frame = ttk.Frame(vertical_paned)
        vertical_paned.add(notes_frame, weight=1)
        self._build_notes_panel(notes_frame)

    def _configure_tags(self) -> None:
        text = self.text
        text.tag_configure("h1", font=("TkDefaultFont", 20, "bold"))
        text.tag_configure("h2", font=("TkDefaultFont", 17, "bold"))
        text.tag_configure("h3", font=("TkDefaultFont", 14, "bold"))
        text.tag_configure("h4", font=("TkDefaultFont", 12, "bold"))
        text.tag_configure("blockquote", lmargin1=24, lmargin2=24, foreground="#555555")
        text.tag_configure("bullet_item", lmargin1=20, lmargin2=32, spacing1=2, spacing3=2)
        text.tag_configure("ordered_item", lmargin1=20, lmargin2=32, spacing1=2, spacing3=2)
        text.tag_configure("list_marker", font=("TkDefaultFont", 11, "bold"), foreground="#444444")
        text.tag_configure("table_source", font=("Courier New", 10), background="#f5f5f5")
        text.tag_configure("verbatim", font=("Courier New", 10), background="#fff3cd")
        text.tag_configure("align_left", justify="left")
        text.tag_configure("align_center", justify="center")
        text.tag_configure("align_right", justify="right")
        # Tk's Text widget has no true "justify" (fill) rendering; "left" is
        # the closest visual approximation. The chosen alignment is still
        # tracked and exported correctly (real CSS text-align: justify on
        # the generated site, see resources/css/site.css).
        text.tag_configure("align_justify", justify="left")
        text.tag_configure("bold", font=("TkDefaultFont", 11, "bold"))
        text.tag_configure("italic", font=("TkDefaultFont", 11, "italic"))
        text.tag_configure("strike", overstrike=True)
        text.tag_configure("superscript", offset=6, font=("TkDefaultFont", 8))
        text.tag_configure("link_style", foreground="#1a73e8", underline=True)
        text.tag_configure("image_style", background="#e8f0fe")
        text.tag_configure("image_center", justify="center")
        text.tag_configure("footnote_style", foreground="#1a73e8")
        text.tag_configure("search_match", background="#ffe08a")
        for tag in ("bold", "italic", "strike", "superscript", "link_style", "image_style", "footnote_style"):
            text.tag_raise(tag)

    # -- zoom (Ctrl+molette) -------------------------------------------------

    def _init_zoom(self) -> None:
        self._zoom_scale = 1.0
        # Reference ("100%") sizes matching _configure_tags above.
        self._base_font_sizes = {
            "h1": 20,
            "h2": 17,
            "h3": 14,
            "h4": 12,
            "body": 11,
            "mono": 10,
            "superscript": 8,
            "superscript_offset": 6,
        }
        self._notes_font = tkfont.Font(family="TkDefaultFont", size=self._base_font_sizes["body"])

    def _on_ctrl_mousewheel(self, event: tk.Event) -> str:
        step = 0.1 if event.delta > 0 else -0.1
        self._zoom_scale = min(3.0, max(0.5, self._zoom_scale + step))
        self._apply_zoom()
        return "break"

    def _apply_zoom(self) -> None:
        scale = self._zoom_scale
        sizes = {key: max(6, round(value * scale)) for key, value in self._base_font_sizes.items()}
        text = self.text
        text.configure(font=("TkDefaultFont", sizes["body"]))
        text.tag_configure("h1", font=("TkDefaultFont", sizes["h1"], "bold"))
        text.tag_configure("h2", font=("TkDefaultFont", sizes["h2"], "bold"))
        text.tag_configure("h3", font=("TkDefaultFont", sizes["h3"], "bold"))
        text.tag_configure("h4", font=("TkDefaultFont", sizes["h4"], "bold"))
        text.tag_configure("bold", font=("TkDefaultFont", sizes["body"], "bold"))
        text.tag_configure("italic", font=("TkDefaultFont", sizes["body"], "italic"))
        text.tag_configure("table_source", font=("Courier New", sizes["mono"]))
        text.tag_configure("verbatim", font=("Courier New", sizes["mono"]))
        text.tag_configure(
            "superscript", offset=sizes["superscript_offset"], font=("TkDefaultFont", sizes["superscript"])
        )
        self._notes_font.configure(size=sizes["body"])

    # -- keyboard shortcuts ---------------------------------------------------

    def _shortcut_bold(self, _event: tk.Event) -> str:
        self._toggle_char_tag("bold")
        return "break"

    def _shortcut_italic(self, _event: tk.Event) -> str:
        self._toggle_char_tag("italic")
        return "break"

    def _shortcut_strike(self, _event: tk.Event) -> str:
        self._toggle_char_tag("strike")
        return "break"

    def _shortcut_superscript(self, _event: tk.Event) -> str:
        self._toggle_char_tag("superscript")
        return "break"

    def _shortcut_nbsp(self, _event: tk.Event) -> str:
        self._insert_nbsp()
        return "break"

    def _shortcut_find(self, _event: tk.Event) -> str:
        self._open_find()
        return "break"

    def _shortcut_replace(self, _event: tk.Event) -> str:
        self._open_replace()
        return "break"

    def _shortcut_undo(self, _event: tk.Event) -> str:
        self._perform_undo()
        return "break"

    def _shortcut_redo(self, _event: tk.Event) -> str:
        self._perform_redo()
        return "break"

    # -- unified undo/redo ---------------------------------------------------

    def _shortcut_toggle_justify(self, _event: tk.Event) -> str:
        """Alt+J: toggle the current paragraph between left and justify,
        the same two-state shortcut convention as WordPress/Gutenberg."""
        current = self._line_alignment(self._current_line())
        self._set_alignment("left" if current == "justify" else "justify")
        return "break"
