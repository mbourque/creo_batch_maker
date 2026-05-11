from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import json
import os
import re
import shutil
import sys
import subprocess
import webbrowser
import xml.etree.ElementTree as ET
import tkinter as tk
import tkinter.filedialog as fd
from tkinter import messagebox, ttk
import customtkinter as ctk
from PIL import Image

# Non-greedy inner; Creo files may contain multiple <DESCRIPTION> blocks — the first
# is sometimes legacy/comment junk; we pick the best candidate after cleaning.
DESCRIPTION_BLOCK_RE = re.compile(
    r"<DESCRIPTION>\s*(.*?)\s*</DESCRIPTION>",
    re.DOTALL | re.IGNORECASE,
)
XML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# Chunk .dxc files: working_dir / f"{CREO_BATCH_BASE}-1.dxc", "-2.dxc", ...
CREO_BATCH_BASE = "creo-batch"
# GO writes this driver next to the chunk .dxc files in the working directory.
CREO_BATCH_RUNNER_BASENAME = "creo-batch-run.ps1"
# Generated runner: max wait per phase for xtop.exe (appear / exit), in seconds.
XTOP_RUNNER_PHASE_TIMEOUT_SEC = 300
# When no Creo loadpoint / no .ttd list yet, File → New uses this default task (filename + UI label).
DEFAULT_MODELCHECK_TTD = "modelcheck.ttd"
DEFAULT_MODELCHECK_DISPLAY = "ModelCHECK"


def _app_bundle_dir() -> Path:
    """Folder beside ``main.py`` (dev) or beside ``.exe`` (PyInstaller); not ``_MEIPASS``."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _default_app_settings_path() -> Path:
    """Sibling ``app_settings.json`` next to the app (dev: script; frozen: executable)."""
    return _app_bundle_dir() / "app_settings.json"


def _xml_attr_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
    )


class CreoDistributedBatchMakerApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Creo Distributed Batch Maker")
        self.geometry("584x310")
        self.resizable(False, False)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        # Keep a tiny PIL image around to establish Pillow usage
        # and provide an easy place to swap in a real icon later.
        self._placeholder_image = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
        self._settings_path = _default_app_settings_path()
        self._configs_dir = _app_bundle_dir() / "configs"
        self._settings_menu: tk.Menu | None = None
        self._menubar: tk.Menu | None = None
        self._settings_options = [
            "Model Checks...",
            "Config.pro...",
            "Angles...",
            "GMC...",
            "Defaults...",
            "Designers...",
            "Holes...",
            "Inch Settings...",
            "Metric Settings...",
            "Sheetmetal Thickness...",
        ]
        self._settings_config_relative: dict[str, str] = {
            "Model Checks...": "default_checks.mch",
            "Config.pro...": "config.pro",
            "Angles...": "angles.txt",
            "GMC...": "config.gmc",
            "Defaults...": "default_start.mcs",
            "Designers...": "designers.txt",
            "Holes...": "holes.txt",
            "Inch Settings...": "inch.mcn",
            "Metric Settings...": "mm.mcn",
            "Sheetmetal Thickness...": "thick.txt",
        }

        self._build_ui()
        self._build_menu_bar()
        # Load last saved app_settings.json after the window exists.
        self.after(0, self._load_settings)
        self.protocol("WM_DELETE_WINDOW", self._on_exit)

    def _is_modelcheck_task(self, task_display: str) -> bool:
        filename = self._task_filename_from_ui(task_display)
        if not filename:
            return False
        return Path(filename).stem.lower() == "modelcheck"

    def _task_filename_from_ui(self, task_display: str) -> str:
        key = (task_display or "").strip()
        return self._task_display_to_filename.get(key, "")

    def _clean_description_inner(self, inner: str) -> str:
        """Remove XML comments and junk; collapse to a single display line."""
        text = inner
        # Strip <!-- ... --> repeatedly (handles nested/overlapping poorly; run until stable)
        for _ in range(20):
            new_text = XML_COMMENT_RE.sub("", text)
            if new_text == text:
                break
            text = new_text
        # Drop common Creo/comment artifacts left inside the tag
        text = re.sub(r"^[\s\-:>]+", "", text)
        text = re.sub(r"[\s\-:>]+$", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _description_looks_usable(self, text: str) -> bool:
        if not text or len(text) > 200:
            return False
        if "-->" in text or "<!--" in text or text.strip().startswith("--"):
            return False
        if "<" in text or ">" in text:
            return False
        return True

    @staticmethod
    def _xml_local_name(tag: str) -> str:
        if tag.startswith("{"):
            return tag.split("}", 1)[-1]
        return tag

    def _description_from_ttd_element(self, ttd: ET.Element) -> str | None:
        """Creo .ttd files are XML: <TTD><DESCRIPTION>...</DESCRIPTION>...</TTD>."""
        for child in ttd:
            if self._xml_local_name(child.tag) != "DESCRIPTION":
                continue
            text = (child.text or "").strip()
            if text:
                return re.sub(r"\s+", " ", text)
        for el in ttd.iter():
            if self._xml_local_name(el.tag) == "DESCRIPTION":
                text = (el.text or "").strip()
                if text:
                    return re.sub(r"\s+", " ", text)
        return None

    def _read_ttd_description(self, ttd_path: Path) -> str:
        try:
            raw = ttd_path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return ttd_path.name

        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return self._read_ttd_description_regex_fallback(ttd_path, raw)

        ttd_el = root
        if self._xml_local_name(root.tag) != "TTD":
            ttd_el = next(
                (el for el in root.iter() if self._xml_local_name(el.tag) == "TTD"),
                root,
            )

        desc = self._description_from_ttd_element(ttd_el)
        if desc:
            return desc

        return self._read_ttd_description_regex_fallback(ttd_path, raw)

    def _read_ttd_description_regex_fallback(self, ttd_path: Path, raw: str) -> str:
        """Non-XML or unusual files: best-effort regex (may be noisy)."""
        blocks = DESCRIPTION_BLOCK_RE.findall(raw)
        if not blocks:
            return ttd_path.name

        cleaned = [self._clean_description_inner(b) for b in blocks]
        for c in cleaned:
            if self._description_looks_usable(c):
                return c
        for c in cleaned:
            if c:
                return c
        return ttd_path.name

    @staticmethod
    def _unique_task_labels(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """pairs: (filename, description). Returns (filename, unique dropdown label)."""
        desc_counts: dict[str, int] = {}
        for _fn, disp in pairs:
            desc_counts[disp] = desc_counts.get(disp, 0) + 1
        out: list[tuple[str, str]] = []
        for fn, disp in pairs:
            if desc_counts.get(disp, 0) > 1:
                label = f"{disp} ({fn})"
            else:
                label = disp
            out.append((fn, label))
        return out

    def _build_ttk_styles(self) -> None:
        style = ttk.Style(self)
        style.configure(
            "Task.TCombobox",
            fieldbackground="#FFFFFF",
            background="#D2D5DA",
            foreground="#1F1F1F",
            bordercolor="#8F98A3",
            lightcolor="#8F98A3",
            darkcolor="#8F98A3",
            arrowsize=14,
            padding=2,
            font=("Segoe UI", 11),
        )

    def _build_ui(self) -> None:
        self._build_ttk_styles()
        container = ctk.CTkFrame(self, corner_radius=0, fg_color="#ECECEC")
        container.pack(fill="both", expand=True, padx=8, pady=8)

        title = ctk.CTkLabel(
            container,
            text="Creo Distributed Batch Maker",
            font=ctk.CTkFont(size=18, weight="normal"),
            text_color="#111111",
        )
        title.pack(anchor="w", padx=32, pady=(6, 4))

        self.working_directory = ctk.StringVar(value="")
        self.creo_loadpoint = ctk.StringVar(value="")
        self.task = ctk.StringVar(value="")
        self._task_display_to_filename: dict[str, str] = {}
        self._task_filename_to_description: dict[str, str] = {}

        self._build_path_row(
            container,
            label_text="Working Directory",
            variable=self.working_directory,
            browse_kind="directory",
        )
        self._build_path_row(
            container,
            label_text="Creo Loadpoint",
            variable=self.creo_loadpoint,
            browse_kind="directory",
        )

        ctk.CTkLabel(
            container,
            text="Task",
            font=ctk.CTkFont(size=13),
            text_color="#111111",
        ).pack(anchor="w", padx=32, pady=(0, 1))

        task_line = ctk.CTkFrame(container, fg_color="transparent")
        task_line.pack(fill="x", padx=32, pady=(0, 4))
        self.task_select = ttk.Combobox(
            task_line,
            textvariable=self.task,
            values=(),
            width=10,
            state="readonly",
            height=6,
            style="Task.TCombobox",
            font=("Segoe UI", 11),
        )
        self.task_select.pack(fill="x", expand=True)
        self.task_select.bind("<<ComboboxSelected>>", lambda _e: self._refresh_settings_menu())

        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", padx=32, pady=(29, 6))
        btn_bar = ctk.CTkFrame(btn_row, fg_color="transparent")
        btn_bar.pack(side="right")
        go_button = ctk.CTkButton(
            btn_bar,
            text="GO",
            width=120,
            height=28,
            corner_radius=6,
            border_width=0,
            fg_color="#3B8ED0",
            text_color="#FFFFFF",
            hover_color="#367DB6",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._on_go,
        )
        launch_button = ctk.CTkButton(
            btn_bar,
            text="Open Batch",
            width=120,
            height=28,
            corner_radius=6,
            border_width=0,
            fg_color="#3B8ED0",
            text_color="#FFFFFF",
            hover_color="#367DB6",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._launch_ptcdbatch,
        )
        go_button.pack(side="right", padx=(8, 0))
        launch_button.pack(side="right", padx=(0, 0))

    def _build_path_row(
        self,
        parent: ctk.CTkFrame,
        label_text: str,
        variable: ctk.StringVar,
        browse_kind: str,
    ) -> None:
        block = ctk.CTkFrame(parent, fg_color="transparent")
        block.pack(fill="x")

        row_label = ctk.CTkLabel(
            block,
            text=label_text,
            font=ctk.CTkFont(size=13),
            text_color="#111111",
        )
        row_label.pack(anchor="w", padx=32, pady=(0, 1))

        line = ctk.CTkFrame(block, fg_color="transparent")
        line.pack(fill="x", padx=32, pady=(0, 5))

        browse_button = ctk.CTkButton(
            line,
            text="Browse...",
            width=88,
            height=26,
            corner_radius=6,
            border_width=0,
            fg_color="#3B8ED0",
            text_color="#FFFFFF",
            hover_color="#367DB6",
            font=ctk.CTkFont(size=13),
            command=lambda: self._browse_target(variable, browse_kind),
        )
        browse_button.pack(side="right")

        entry = ctk.CTkEntry(
            line,
            textvariable=variable,
            height=26,
            corner_radius=2,
            border_width=1,
            fg_color="#FFFFFF",
            border_color="#8F98A3",
            text_color="#1F1F1F",
            font=ctk.CTkFont(size=13),
        )
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        if variable is self.creo_loadpoint:
            entry.bind("<FocusOut>", lambda _e: self._refresh_task_options())
            entry.bind("<Return>", lambda _e: self._refresh_task_options())

    def _build_menu_bar(self) -> None:
        menubar = tk.Menu(self)
        self._menubar = menubar

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New", command=self._on_file_menu_new)
        file_menu.add_command(label="Open...", command=self._on_file_menu_open)
        file_menu.add_command(label="Save", command=self._on_file_menu_save)
        file_menu.add_command(label="Save as...", command=self._on_file_menu_save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_exit)
        menubar.add_cascade(label="File", menu=file_menu)

        self._settings_menu = tk.Menu(menubar, tearoff=0)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Documentation...", command=self._open_documentation)
        help_menu.add_command(label="About...", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.configure(menu=menubar)
        self._refresh_settings_menu()

    @staticmethod
    def _menubar_cascade_index(menubar: tk.Menu, label: str) -> int | None:
        try:
            end = menubar.index("end")
        except tk.TclError:
            return None
        if end is None:
            return None
        for i in range(end + 1):
            try:
                if menubar.type(i) == "cascade" and menubar.entrycget(i, "label") == label:
                    return i
            except tk.TclError:
                continue
        return None

    def _refresh_settings_menu(self) -> None:
        if self._settings_menu is None or self._menubar is None:
            return
        self._settings_menu.delete(0, "end")
        is_mc = self._is_modelcheck_task(self.task.get() or "")
        settings_idx = self._menubar_cascade_index(self._menubar, "Settings")

        if is_mc:
            if settings_idx is None:
                help_idx = self._menubar_cascade_index(self._menubar, "Help")
                if help_idx is not None:
                    self._menubar.insert_cascade(help_idx, label="Settings", menu=self._settings_menu)
                else:
                    self._menubar.add_cascade(label="Settings", menu=self._settings_menu)
            for option in self._settings_options:
                self._settings_menu.add_command(
                    label=option,
                    command=lambda o=option: self._on_settings_config_item(o),
                )
        else:
            if settings_idx is not None:
                self._menubar.delete(settings_idx)

    def _settings_fields_ready(self) -> tuple[bool, str]:
        if not (self.working_directory.get() or "").strip():
            return False, "Working directory cannot be empty."
        if not (self.creo_loadpoint.get() or "").strip():
            return False, "Creo loadpoint cannot be empty."
        if not self._task_filename_from_ui(self.task.get() or ""):
            return False, "Task cannot be empty. Set Creo loadpoint to list TTDs, or use File → New."
        return True, ""

    def _on_exit(self) -> None:
        """Save settings to the active JSON when the form is complete, then close."""
        self._write_current_settings_to_disk()
        self.destroy()

    def _on_file_menu_new(self) -> None:
        self._settings_path = _default_app_settings_path()
        self.working_directory.set("")
        self.creo_loadpoint.set("")
        self._refresh_task_options()

    def _write_current_settings_to_disk(self) -> tuple[bool, str]:
        """Validate fields and write JSON to ``self._settings_path``. Returns (ok, error message)."""
        ok, err = self._settings_fields_ready()
        if not ok:
            return False, err
        task_filename = self._task_filename_from_ui(self.task.get() or "")
        self._save_settings(task_filename)
        return True, ""

    def _on_file_menu_save(self) -> None:
        ok, err = self._write_current_settings_to_disk()
        if not ok:
            messagebox.showwarning("Save", err)
            return
        messagebox.showinfo("Save", f"Settings saved to:\n{self._settings_path.resolve()}")

    def _on_file_menu_save_as(self) -> None:
        ok, err = self._settings_fields_ready()
        if not ok:
            messagebox.showwarning("Save As", err)
            return
        initial_dir = str(self._settings_path.parent)
        if not Path(initial_dir).is_dir():
            initial_dir = str(_app_bundle_dir())
        initial_file = self._settings_path.name
        path = fd.asksaveasfilename(
            title="Save settings as (JSON)",
            initialdir=initial_dir,
            initialfile=initial_file,
            defaultextension=".json",
            filetypes=[("JSON settings", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        p = Path(path).resolve()
        if p.suffix.lower() != ".json":
            p = p.with_suffix(".json")
        self._settings_path = p
        ok2, err2 = self._write_current_settings_to_disk()
        if not ok2:
            messagebox.showwarning("Save As", err2)
            return
        messagebox.showinfo("Save As", f"Settings saved to:\n{self._settings_path.resolve()}")

    def _on_file_menu_open(self) -> None:
        initial_dir = str(self._settings_path.parent)
        if not Path(initial_dir).is_dir():
            initial_dir = str(_app_bundle_dir())
        path = fd.askopenfilename(
            title="Open settings (JSON)",
            initialdir=initial_dir,
            filetypes=[("JSON settings", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        p = Path(path).resolve()
        try:
            raw = p.read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Open", f"Could not read:\n{p}\n\n{exc}")
            return
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            messagebox.showerror("Open", f"Invalid JSON in:\n{p}\n\n{exc}")
            return
        if not isinstance(data, dict):
            messagebox.showerror("Open", "Settings file must contain a JSON object at the top level.")
            return
        self._settings_path = p
        self._apply_settings_data(data)
        # Success case is intentionally quiet; errors are still shown.

    @staticmethod
    def _open_file_in_notepad(target: Path) -> None:
        """Open a file in Notepad (avoids Windows 'choose an app' for unknown extensions)."""
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        notepad = Path(system_root) / "System32" / "notepad.exe"
        if not notepad.is_file():
            notepad = Path(system_root) / "notepad.exe"
        subprocess.Popen([str(notepad), str(target)], close_fds=True)

    def _on_settings_config_item(self, option: str) -> None:
        rel = self._settings_config_relative.get(option)
        if not rel:
            messagebox.showerror("Settings", f"No file mapping for:\n{option}")
            return
        target = (self._configs_dir / rel).resolve()
        if not target.is_file():
            messagebox.showerror(
                "File not found",
                f"Expected sample config at:\n{target}\n\n(Relative to configs/ next to the app.)",
            )
            return
        try:
            self._open_file_in_notepad(target)
        except OSError as exc:
            messagebox.showerror("Open failed", f"Could not open in Notepad:\n{target}\n\n{exc}")

    def _open_documentation(self) -> None:
        webbrowser.open(
            "https://github.com/mbourque/creo_batch_maker/wiki/Documentation"
        )

    def _show_about(self) -> None:
        webbrowser.open("https://github.com/mbourque/creo_batch_maker")

    def _browse_target(self, target_variable: ctk.StringVar, browse_kind: str) -> None:
        initial = target_variable.get() or str(Path.home())
        selected_path = ""

        if browse_kind == "directory":
            selected_path = fd.askdirectory(initialdir=initial)
        elif browse_kind == "file":
            selected_path = fd.askopenfilename(initialdir=initial)

        if selected_path:
            target_variable.set(selected_path)
            if target_variable is self.creo_loadpoint:
                self._refresh_task_options()

    @staticmethod
    def _task_allowed_for_dropdown(filename: str, display_label: str) -> bool:
        """Only ModelCHECK and JPEG 3D… style tasks appear in the Task combobox."""
        if filename.lower() == "modelcheck.ttd":
            return True
        dl = display_label.casefold()
        if "jpeg" in dl and "3d" in dl:
            return True
        stem = Path(filename).stem.casefold()
        if "jpeg" in stem and "3d" in stem:
            return True
        return False

    def _refresh_task_options(self) -> None:
        loadpoint = (self.creo_loadpoint.get() or "").strip().rstrip("\\/")
        ttd_folder = Path(loadpoint) / "Common Files" / "text" / "ttds" if loadpoint else None

        filenames: list[str] = []
        if ttd_folder and ttd_folder.exists() and ttd_folder.is_dir():
            filenames = sorted(
                [p.name for p in ttd_folder.iterdir() if p.is_file() and p.suffix.lower() == ".ttd"],
                key=str.lower,
            )

        pairs: list[tuple[str, str]] = []
        for name in filenames:
            desc = self._read_ttd_description(ttd_folder / name) if ttd_folder else name
            pairs.append((name, desc))

        self._task_filename_to_description = {name: desc for name, desc in pairs}

        labeled = self._unique_task_labels(pairs)
        allowed = [(fn, lab) for fn, lab in labeled if self._task_allowed_for_dropdown(fn, lab)]
        preferred = "modelcheck.ttd"
        preferred_rows = [(fn, lab) for fn, lab in allowed if fn.lower() == preferred]
        other_rows = [(fn, lab) for fn, lab in allowed if fn.lower() != preferred]
        other_rows.sort(key=lambda row: row[1].casefold())
        ordered = (preferred_rows[:1] + other_rows) if preferred_rows else other_rows

        self._task_display_to_filename = {lab: fn for fn, lab in ordered}
        display_values = [lab for _fn, lab in ordered]

        if not display_values:
            self._task_display_to_filename = {DEFAULT_MODELCHECK_DISPLAY: DEFAULT_MODELCHECK_TTD}
            self._task_filename_to_description = {DEFAULT_MODELCHECK_TTD: DEFAULT_MODELCHECK_DISPLAY}
            self.task_select.configure(values=(DEFAULT_MODELCHECK_DISPLAY,))
            self.task.set(DEFAULT_MODELCHECK_DISPLAY)
            self._refresh_settings_menu()
            return

        self.task_select.configure(values=tuple(display_values))
        self.task.set(display_values[0])
        self._refresh_settings_menu()

    def _apply_settings_data(self, data: dict[str, object]) -> None:
        """Apply settings from a dict (same keys as app_settings.json). Refreshes task list and menu."""
        self.working_directory.set(str(data.get("working_directory") or "").strip())
        self.creo_loadpoint.set(str(data.get("creo_loadpoint") or "").strip())

        self._refresh_task_options()

        saved_task_filename = str(data.get("task_filename") or "").strip()
        if saved_task_filename:
            for display, filename in self._task_display_to_filename.items():
                if filename.lower() == saved_task_filename.lower():
                    self.task.set(display)
                    break
        self._refresh_settings_menu()

    def _load_settings(self) -> None:
        """Load working directory, Creo loadpoint, and task from self._settings_path (JSON)."""
        if not self._settings_path.exists():
            # Create default app_settings.json next to the app when missing (empty fields).
            if self._settings_path.resolve() == _default_app_settings_path().resolve():
                empty = {"working_directory": "", "creo_loadpoint": "", "task_filename": ""}
                try:
                    self._settings_path.write_text(json.dumps(empty, indent=2), encoding="utf-8")
                except OSError:
                    self._refresh_task_options()
                    return
            else:
                self._refresh_task_options()
                return

        try:
            data = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._refresh_task_options()
            return

        if not isinstance(data, dict):
            self._refresh_task_options()
            return

        self._apply_settings_data(data)

    def _save_settings(self, task_filename: str) -> None:
        working_directory = self.working_directory.get().strip()
        creo_loadpoint = self.creo_loadpoint.get().strip()
        task_fn = task_filename.strip()
        if not working_directory or not creo_loadpoint or not task_fn:
            return
        payload = {
            "working_directory": working_directory,
            "creo_loadpoint": creo_loadpoint,
            "task_filename": task_fn,
        }
        try:
            self._settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            # Keep GO success path non-blocking if settings save fails.
            pass

    def _scan_models_non_recursive(self, directory: Path) -> dict[Path, list[str]]:
        patterns = [
            r".*\.prt(\.\d+)?$",
            r".*\.asm(\.\d+)?$",
            r".*\.drw(\.\d+)?$",
        ]
        files: dict[Path, list[str]] = defaultdict(list)
        for entry in directory.iterdir():
            if not entry.is_file():
                continue
            for pattern in patterns:
                if re.match(pattern, entry.name, re.IGNORECASE):
                    files[directory].append(entry.name)
                    break
        return files

    def _get_latest_model_files(self, files_dict: dict[Path, list[str]]) -> list[Path]:
        latest_files: list[Path] = []
        for root, versions in files_dict.items():
            base_files: dict[str, list[str]] = defaultdict(list)
            for version in versions:
                base_name = re.sub(r"\.\d+$", "", version)
                base_files[base_name].append(version)

            for version_list in base_files.values():
                if all(re.match(r".*\.\d+$", v) is None for v in version_list):
                    latest_file = version_list[0]
                else:
                    latest_file = max(
                        version_list,
                        key=lambda x: int(x.split(".")[-1]) if re.match(r".*\.\d+$", x) else 0,
                    )
                latest_files.append(root / latest_file)

        def model_sort_key(path: Path) -> tuple[int, str]:
            lower_name = path.name.lower()
            match = re.search(r"\.(prt|drw|asm)(?:\.\d+)?$", lower_name)
            ext = match.group(1) if match else ""
            rank = {"prt": 0, "drw": 1, "asm": 2}.get(ext, 3)
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            return (rank, size, lower_name)

        return sorted(latest_files, key=model_sort_key)

    def _scan_files_recursive(self, directory: Path) -> list[Path]:
        files: list[Path] = []
        for entry in directory.rglob("*"):
            if entry.is_file():
                files.append(entry)
        return sorted(files, key=lambda p: str(p).lower())

    def _chunk_paths(self, items: list[Path], chunk_size: int) -> list[list[Path]]:
        if chunk_size <= 0:
            return [items]
        return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]

    @staticmethod
    def _ps_single_quoted_literal(path: Path) -> str:
        """Single-quoted PowerShell string literal for a filesystem path."""
        s = str(path.resolve())
        return "'" + s.replace("'", "''") + "'"

    @classmethod
    def _build_chunk_runner_ps1(
        cls,
        ptcdbatch_bat: Path,
        working_dir: Path,
        kill_bat: Path,
        num_chunks: int,
    ) -> str:
        """PowerShell: each chunk runs ptcdbatch -nographics -process, waits on xtop.exe, runs kill.bat."""
        ptc = cls._ps_single_quoted_literal(ptcdbatch_bat)
        wd = cls._ps_single_quoted_literal(working_dir)
        kb = cls._ps_single_quoted_literal(kill_bat)
        n = int(num_chunks)
        base = CREO_BATCH_BASE.replace("'", "''")
        lines = [
            "$ErrorActionPreference = 'Continue'",
            f"$PtcDbatch = {ptc}",
            f"$WorkDir = {wd}",
            f"$KillBat = {kb}",
            f"$NumChunks = {n}",
            f"$ChunkBase = '{base}'",
            "",
            "function Write-ChLog {",
            "    param([string]$Message)",
            "    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'",
            '    Write-Host "[$ts] $Message"',
            "}",
            "",
            r'Write-ChLog "Runner starting. $NumChunks chunk(s). Close other Creo sessions if xtop waits misbehave."',
            r'Write-ChLog "ptcdbatch: $PtcDbatch"',
            r'Write-ChLog "Working directory: $WorkDir"',
            r'Write-ChLog "kill.bat: $KillBat"',
            "",
            "for ($chunk = 1; $chunk -le $NumChunks; $chunk++) {",
            r'    Write-ChLog "---------- Chunk $chunk / $NumChunks ----------"',
            '    $dxc = Join-Path -Path $WorkDir -ChildPath ("{0}-{1}.dxc" -f $ChunkBase, $chunk)',
            r'    Write-ChLog "DXC path: $dxc"',
            "    if (-not (Test-Path -LiteralPath $dxc)) {",
            r'        Write-ChLog "ERROR: DXC file missing. Skipping this chunk."',
            "        continue",
            "    }",
            "",
            "    $batParent = [System.IO.Path]::GetDirectoryName($PtcDbatch)",
            r'    Write-ChLog "Launching ptcdbatch (hidden window): -nographics -process $dxc"',
            "    try {",
            "        $null = Start-Process -FilePath $PtcDbatch -WorkingDirectory $batParent `",
            "            -ArgumentList @('-nographics', '-process', $dxc) `",
            "            -WindowStyle Hidden -ErrorAction Stop",
            "    } catch {",
            r'        Write-ChLog ("ERROR: failed to start ptcdbatch: " + $_.Exception.Message)',
            "        continue",
            "    }",
            "",
            r'    Write-ChLog "WAITING: for xtop.exe to appear (poll every 1s)."',
            "    $waitStart = Get-Date",
            "    $xtopAtStart = $null",
            "    while ($true) {",
            "        $xtopAtStart = @(Get-Process -Name 'xtop' -ErrorAction SilentlyContinue)",
            "        if ($xtopAtStart.Count -gt 0) { break }",
            "        $elapsed = [int][math]::Floor(((Get-Date) - $waitStart).TotalSeconds)",
            f"        if ($elapsed -ge {XTOP_RUNNER_PHASE_TIMEOUT_SEC}) {{",
            r'            Write-ChLog "TIMEOUT: 5 min waiting for xtop.exe to start; continuing to kill step."',
            "            break",
            "        }",
            "        if ($elapsed -le 2 -or ($elapsed % 15 -eq 0)) {",
            r'            Write-ChLog "WAITING: xtop.exe not in process list yet (${elapsed}s elapsed)."',
            "        }",
            "        Start-Sleep -Seconds 1",
            "    }",
            "    if ($xtopAtStart -and $xtopAtStart.Count -gt 0) {",
            "        $ids = ($xtopAtStart | ForEach-Object { $_.Id }) -join ', '",
            r'        Write-ChLog "FOUND: xtop.exe is running (PID(s): $ids)."',
            "    } else {",
            r'        Write-ChLog "WARNING: xtop.exe never appeared before timeout (or exited instantly)."',
            "    }",
            "",
            r'    Write-ChLog "WAITING: for xtop.exe to exit (poll every 2s)."',
            "    $waitEnd = Get-Date",
            "    while ($true) {",
            "        $xtopRunning = @(Get-Process -Name 'xtop' -ErrorAction SilentlyContinue)",
            "        if ($xtopRunning.Count -eq 0) { break }",
            "        $elapsed = [int][math]::Floor(((Get-Date) - $waitEnd).TotalSeconds)",
            f"        if ($elapsed -ge {XTOP_RUNNER_PHASE_TIMEOUT_SEC}) {{",
            r'            Write-ChLog "TIMEOUT: 5 min waiting for xtop.exe to exit; stopping exit-wait loop."',
            "            break",
            "        }",
            "        if ($elapsed -le 4 -or ($elapsed % 20 -eq 0)) {",
            "            $ids = ($xtopRunning | ForEach-Object { $_.Id }) -join ', '",
            r'            Write-ChLog "WAITING: xtop.exe still running (PID(s): $ids), ${elapsed}s since exit-wait started."',
            "        }",
            "        Start-Sleep -Seconds 2",
            "    }",
            "    $xtopAfter = @(Get-Process -Name 'xtop' -ErrorAction SilentlyContinue)",
            "    if ($xtopAfter.Count -eq 0) {",
            r'        Write-ChLog "CLOSED: xtop.exe is no longer in the process list."',
            "    } else {",
            "        $ids = ($xtopAfter | ForEach-Object { $_.Id }) -join ', '",
            r'        Write-ChLog "WARNING: xtop.exe still present (PID(s): $ids); exit wait may have timed out."',
            "    }",
            "",
            "    $killParent = [System.IO.Path]::GetDirectoryName($KillBat)",
            r'    Write-ChLog "Running kill.bat (wait)..."',
            "    try {",
            "        $kp = Start-Process -FilePath $KillBat -WorkingDirectory $killParent `",
            "            -Wait -PassThru -NoNewWindow -ErrorAction Stop",
            r'        Write-ChLog ("kill.bat exit code: " + $kp.ExitCode)',
            "    } catch {",
            r'        Write-ChLog ("ERROR: kill.bat failed: " + $_.Exception.Message)',
            "    }",
            "}",
            "",
            r'Write-ChLog "Runner finished all chunks."',
        ]
        return "\n".join(lines) + "\n"

    def _on_go(self) -> None:
        working_dir_raw = (self.working_directory.get() or "").strip()
        loadpoint_raw = (self.creo_loadpoint.get() or "").strip().rstrip("\\/")
        task_display_raw = (self.task.get() or "").strip()
        task_filename = self._task_filename_from_ui(task_display_raw)

        if not working_dir_raw:
            messagebox.showwarning("Missing Working Directory", "Please enter a working directory.")
            return
        use_modelcheck_config = self._is_modelcheck_task(task_display_raw)
        if use_modelcheck_config and not self._configs_dir.is_dir():
            messagebox.showerror(
                "Missing configs",
                f"Modelcheck task requires the configs folder next to the app:\n{self._configs_dir}",
            )
            return
        if not loadpoint_raw:
            messagebox.showwarning("Missing Creo Loadpoint", "Please enter a Creo loadpoint.")
            return
        if not task_display_raw or not task_filename:
            messagebox.showwarning("Missing Task", "Please select a task.")
            return

        working_dir = Path(working_dir_raw)
        models_dir = working_dir
        ttd_path = Path(loadpoint_raw) / "Common Files" / "text" / "ttds" / task_filename
        group_name = self._task_filename_to_description.get(task_filename) or self._read_ttd_description(
            ttd_path
        )
        group_name_attr = _xml_attr_escape(group_name)
        ptcdbatch_bat = Path(loadpoint_raw) / "Parametric" / "bin" / "ptcdbatch.bat"
        kill_bat = _app_bundle_dir() / "kill.bat"
        runner_ps1_path = working_dir / CREO_BATCH_RUNNER_BASENAME

        if not ptcdbatch_bat.is_file():
            messagebox.showerror("File Not Found", f"Could not find:\n{ptcdbatch_bat}")
            return
        if not kill_bat.is_file():
            messagebox.showerror(
                "File Not Found",
                f"Could not find:\n{kill_bat}\n\nPlace kill.bat next to this application.",
            )
            return

        try:
            models_dir.mkdir(parents=True, exist_ok=True)
            scanned = self._scan_models_non_recursive(models_dir)
            latest_files = self._get_latest_model_files(scanned)
            config_files = (
                self._scan_files_recursive(self._configs_dir) if use_modelcheck_config else []
            )
            model_chunks = self._chunk_paths(latest_files, 10)
            if not model_chunks:
                model_chunks = [[]]

            working_dir.mkdir(parents=True, exist_ok=True)
            for idx, chunk in enumerate(model_chunks, start=1):
                chunk_path = working_dir / f"{CREO_BATCH_BASE}-{idx}.dxc"
                group_lines = [
                    f'    <Group DSQM="_LOCAL" Name="{group_name_attr}" Output="2" '
                    f'OutputDir="{_xml_attr_escape(working_dir_raw)}" PrimaryContent="0" '
                    f'TTD="{_xml_attr_escape(str(ttd_path))}" VaultResults="0">'
                ]
                group_lines.extend(f"        <Object>{str(p)}</Object>" for p in chunk)
                if config_files:
                    group_lines.extend(f"        <ConfigFile>{str(p)}</ConfigFile>" for p in config_files)
                group_lines.append("    </Group>")
                data_block = "\n".join(group_lines) + "\n"
                file_content = f"<DXC>\n    <Windchill/>\n{data_block}</DXC>\n"
                chunk_path.write_text(file_content, encoding="utf-8")

            num_chunks = len(model_chunks)
            runner_text = self._build_chunk_runner_ps1(ptcdbatch_bat, working_dir, kill_bat, num_chunks)
            runner_ps1_path.write_text(runner_text, encoding="utf-8-sig")
        except OSError as exc:
            messagebox.showerror(
                "Create File Failed",
                f"Could not create chunk .dxc or runner script in:\n{working_dir}\n\n{exc}",
            )
            return

        messagebox.showinfo(
            "Success",
            f"Created {num_chunks} chunk file(s): {CREO_BATCH_BASE}-1.dxc … "
            f"{CREO_BATCH_BASE}-{num_chunks}.dxc\n"
            f"Runner: {runner_ps1_path}\n\n"
            f"Use Open Batch to run {CREO_BATCH_RUNNER_BASENAME} in PowerShell (logs each step; xtop.exe waits; kill.bat per chunk).\n"
            f"Wrote {len(config_files)} config file(s) and {len(latest_files)} model object(s) "
            f"(.prt/.asm/.drw in working directory).",
        )
        self._save_settings(task_filename)

    def _launch_ptcdbatch(self) -> None:
        loadpoint_raw = (self.creo_loadpoint.get() or "").strip().rstrip("\\/")
        working_dir_raw = (self.working_directory.get() or "").strip()
        if not loadpoint_raw:
            messagebox.showwarning("Missing Creo Loadpoint", "Please enter a Creo loadpoint.")
            return
        if not working_dir_raw:
            messagebox.showwarning("Missing Working Directory", "Please enter a working directory.")
            return

        bat_path = Path(loadpoint_raw) / "Parametric" / "bin" / "ptcdbatch.bat"
        if not bat_path.exists():
            messagebox.showerror("File Not Found", f"Could not find:\n{bat_path}")
            return

        working_dir = Path(working_dir_raw).resolve()
        runner_ps1 = working_dir / CREO_BATCH_RUNNER_BASENAME
        if not runner_ps1.is_file():
            messagebox.showerror(
                "File Not Found",
                f"Could not find:\n{runner_ps1}\n\nRun GO first to create chunk .dxc files and the runner script.",
            )
            return

        ps_exe = self._resolve_powershell_exe()
        if not ps_exe:
            messagebox.showerror("PowerShell Not Found", "Could not locate powershell.exe.")
            return
        try:
            subprocess.Popen(
                [
                    ps_exe,
                    "-NoExit",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(runner_ps1.resolve()),
                ],
                cwd=str(working_dir),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        except OSError as exc:
            messagebox.showerror(
                "Launch Failed",
                f"Could not start:\n{runner_ps1}\n\n{exc}",
            )

    @staticmethod
    def _resolve_powershell_exe() -> str | None:
        # Try PATH first.
        candidate = shutil.which("powershell.exe")
        if candidate:
            return candidate
        # Typical Windows locations.
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        fallbacks = [
            Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe",
            Path(system_root) / "SysWOW64" / "WindowsPowerShell" / "v1.0" / "powershell.exe",
        ]
        for path in fallbacks:
            if path.exists():
                return str(path)
        return None


def main() -> None:
    app = CreoDistributedBatchMakerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
