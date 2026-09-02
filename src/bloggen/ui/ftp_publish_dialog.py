"""Dialog for configuring FTP/FTPS credentials and publishing the generated
site, with a progress gauge and a closing link to the freshly published
site."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk

from bloggen.config.models import FtpConfig
from bloggen.publish.ftp_publisher import FtpPublishError, publish_directory
from bloggen.ui.tooltip import add_tooltip


class FtpPublishDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        ftp_config: FtpConfig,
        output_dir: Path,
        on_config_changed: Callable[[FtpConfig], None],
    ) -> None:
        super().__init__(parent)
        self.title("Publier le site (FTP)")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._output_dir = output_dir
        self._on_config_changed = on_config_changed
        self._queue: queue.Queue[tuple] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._cancel_event = threading.Event()

        self.host_var = tk.StringVar(value=ftp_config.host)
        self.port_var = tk.StringVar(value=str(ftp_config.port or 21))
        self.username_var = tk.StringVar(value=ftp_config.username)
        self.password_var = tk.StringVar(value=ftp_config.password)
        self.remote_dir_var = tk.StringVar(value=ftp_config.remote_dir or "/")
        self.use_tls_var = tk.BooleanVar(value=ftp_config.use_tls)
        self.passive_mode_var = tk.BooleanVar(value=ftp_config.passive_mode)
        self.site_url_var = tk.StringVar(value=ftp_config.site_url)
        self.status_var = tk.StringVar(value="")

        self._build_form()

    def _build_form(self) -> None:
        form = ttk.Frame(self, padding=10)
        form.pack(fill="both", expand=True)

        rows: list[tuple[str, tk.StringVar, str]] = [
            ("Hôte FTP", self.host_var, "Adresse du serveur FTP, ex. ftp.monsite.fr"),
            ("Port", self.port_var, "Port de connexion (21 par défaut)."),
            ("Utilisateur", self.username_var, "Identifiant de connexion FTP."),
            ("Mot de passe", self.password_var, "Mot de passe FTP (enregistré en clair dans le fichier de configuration local)."),
            ("Dossier distant", self.remote_dir_var, "Dossier distant dans lequel transférer le site, ex. /www ou public_html/monsite."),
            ("URL du site publié", self.site_url_var, "Adresse à ouvrir une fois la publication terminée, ex. https://monsite.fr"),
        ]
        self._entries: list[ttk.Entry] = []
        for row_index, (label_text, var, tip) in enumerate(rows):
            label = ttk.Label(form, text=label_text)
            label.grid(row=row_index, column=0, sticky="w", padx=4, pady=4)
            show = "*" if var is self.password_var else ""
            entry = ttk.Entry(form, textvariable=var, width=42, show=show)
            entry.grid(row=row_index, column=1, sticky="ew", padx=4, pady=4)
            add_tooltip(label, tip)
            add_tooltip(entry, tip)
            self._entries.append(entry)

        checks_row = len(rows)
        self._tls_check = ttk.Checkbutton(
            form, text="Connexion sécurisée (FTPS)", variable=self.use_tls_var
        )
        self._tls_check.grid(row=checks_row, column=0, columnspan=2, sticky="w", padx=4, pady=(4, 0))
        add_tooltip(self._tls_check, "Chiffre la connexion et le transfert (FTP sur TLS).")

        self._passive_check = ttk.Checkbutton(
            form, text="Mode passif", variable=self.passive_mode_var
        )
        self._passive_check.grid(row=checks_row + 1, column=0, columnspan=2, sticky="w", padx=4, pady=(0, 4))
        add_tooltip(
            self._passive_check,
            "Recommandé dans la plupart des cas (compatible avec les pare-feux et NAT).",
        )

        self.progress = ttk.Progressbar(form, orient="horizontal", mode="determinate", length=360)
        self.progress.grid(row=checks_row + 2, column=0, columnspan=2, sticky="ew", padx=4, pady=(8, 2))

        self.status_label = ttk.Label(form, textvariable=self.status_var, foreground="#555555")
        self.status_label.grid(row=checks_row + 3, column=0, columnspan=2, sticky="w", padx=4)

        form.columnconfigure(1, weight=1)

        button_row = ttk.Frame(self, padding=(10, 0, 10, 10))
        button_row.pack(fill="x")
        self._publish_button = ttk.Button(button_row, text="Publier", command=self._start_publish)
        self._publish_button.pack(side="right", padx=(6, 0))
        self._close_button = ttk.Button(button_row, text="Fermer", command=self._on_close)
        self._close_button.pack(side="right")
        self._cancel_button = ttk.Button(button_row, text="Annuler le transfert", command=self._cancel)

    def _collect_config(self) -> FtpConfig | None:
        host = self.host_var.get().strip()
        username = self.username_var.get().strip()
        if not host or not username:
            messagebox.showerror(
                "Publier le site", "L'hôte et l'utilisateur FTP sont obligatoires.", parent=self
            )
            return None
        try:
            port = int(self.port_var.get().strip() or "21")
        except ValueError:
            messagebox.showerror("Publier le site", "Le port doit être un nombre.", parent=self)
            return None

        return FtpConfig(
            host=host,
            port=port,
            username=username,
            password=self.password_var.get(),
            remote_dir=self.remote_dir_var.get().strip() or "/",
            use_tls=bool(self.use_tls_var.get()),
            passive_mode=bool(self.passive_mode_var.get()),
            site_url=self.site_url_var.get().strip(),
        )

    def _start_publish(self) -> None:
        config = self._collect_config()
        if config is None:
            return
        self._on_config_changed(config)

        self._set_inputs_enabled(False)
        self._cancel_event.clear()
        self.progress.configure(mode="determinate", maximum=100, value=0)
        self.status_var.set("Connexion au serveur...")
        self._publish_button.pack_forget()
        self._cancel_button.pack(side="right", padx=(6, 0))

        def progress_callback(done: int, total: int, relative_path: str) -> None:
            self._queue.put(("progress", done, total, relative_path))

        def should_cancel() -> bool:
            return self._cancel_event.is_set()

        def run() -> None:
            try:
                count = publish_directory(
                    self._output_dir,
                    config,
                    progress=progress_callback,
                    should_cancel=should_cancel,
                )
                self._queue.put(("done", count))
            except FtpPublishError as exc:
                self._queue.put(("error", str(exc)))

        self._worker = threading.Thread(target=run, daemon=True)
        self._worker.start()
        self.after(100, self._poll_queue)

    def _cancel(self) -> None:
        self._cancel_event.set()
        self.status_var.set("Annulation en cours...")

    def _poll_queue(self) -> None:
        try:
            while True:
                message = self._queue.get_nowait()
                kind = message[0]
                if kind == "progress":
                    _, done, total, relative_path = message
                    self.progress.configure(maximum=max(total, 1), value=done)
                    self.status_var.set(f"Transfert : {relative_path} ({done}/{total})")
                elif kind == "done":
                    self._on_publish_finished(message[1])
                    return
                elif kind == "error":
                    self._on_publish_failed(message[1])
                    return
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _on_publish_finished(self, file_count: int) -> None:
        self.status_var.set(f"Publication terminée : {file_count} fichier(s) transféré(s).")
        self._set_inputs_enabled(True)
        self._cancel_button.pack_forget()
        self._publish_button.pack(side="right", padx=(6, 0))

        site_url = self.site_url_var.get().strip()
        if site_url and messagebox.askyesno(
            "Publication terminée",
            f"{file_count} fichier(s) transféré(s) avec succès.\n\nOuvrir {site_url} ?",
            parent=self,
        ):
            webbrowser.open(site_url)
        else:
            messagebox.showinfo(
                "Publication terminée", f"{file_count} fichier(s) transféré(s) avec succès.", parent=self
            )

    def _on_publish_failed(self, error_message: str) -> None:
        was_cancelled = self._cancel_event.is_set()
        self.status_var.set("Transfert annulé." if was_cancelled else "Échec de la publication.")
        self._set_inputs_enabled(True)
        self._cancel_button.pack_forget()
        self._publish_button.pack(side="right", padx=(6, 0))
        if not was_cancelled:
            messagebox.showerror("Publication échouée", error_message, parent=self)

    def _set_inputs_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for entry in self._entries:
            entry.configure(state=state)
        self._tls_check.configure(state=state)
        self._passive_check.configure(state=state)
        self._publish_button.configure(state=state)
        self._close_button.configure(state=state)

    def _on_close(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            self._cancel_event.set()
            return
        self.grab_release()
        self.destroy()
