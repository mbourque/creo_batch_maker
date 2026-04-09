from __future__ import annotations

from collections import defaultdict
from collections.abc import MutableMapping
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
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
        self.geometry("760x560")
        self.resizable(False, False)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        # Keep a tiny PIL image around to establish Pillow usage
        # and provide an easy place to swap in a real icon later.
        self._placeholder_image = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
        self._settings_path = Path(__file__).resolve().parent / "app_settings.json"

        self._build_ui()
        self._load_settings()

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
        container.pack(fill="both", expand=True, padx=10, pady=10)

        title = ctk.CTkLabel(
            container,
            text="Creo Distributed Batch Maker",
            font=ctk.CTkFont(size=20, weight="normal"),
            text_color="#111111",
        )
        title.grid(row=0, column=0, columnspan=3, sticky="w", padx=32, pady=(16, 10))

        self.working_directory = ctk.StringVar(value="")
        self.creo_loadpoint = ctk.StringVar(value="")
        self.task = ctk.StringVar(value="")
        self._task_display_to_filename: dict[str, str] = {}
        self._task_filename_to_description: dict[str, str] = {}
        self.modelcheck_config_folder = ctk.StringVar(value="")
        self.creo_models_folder = ctk.StringVar(value="")
        self.distributed_batch_file = ctk.StringVar(value="")

        current_row = 1
        current_row = self._build_path_row(
            container,
            row=current_row,
            label_text="Working Directory",
            variable=self.working_directory,
            browse_kind="directory",
        )
        current_row = self._build_path_row(
            container,
            row=current_row,
            label_text="Creo Loadpoint",
            variable=self.creo_loadpoint,
            browse_kind="directory",
        )

        ctk.CTkLabel(
            container,
            text="Task",
            font=ctk.CTkFont(size=14),
            text_color="#111111",
        ).grid(row=current_row, column=0, columnspan=2, sticky="w", padx=32, pady=(0, 2))
        current_row += 1

        self.task_select = ttk.Combobox(
            container,
            textvariable=self.task,
            values=(),
            width=58,
            state="readonly",
            height=10,
            style="Task.TCombobox",
            font=("Segoe UI", 11),
        )
        self.task_select.grid(row=current_row, column=0, sticky="w", padx=32, pady=(0, 8))
        self.task_select.bind("<<ComboboxSelected>>", lambda _e: self._update_modelcheck_config_ui())
        current_row += 1

        self._mc_config_widgets: MutableMapping[str, object] = {}
        current_row = self._build_path_row(
            container,
            row=current_row,
            label_text="Modelcheck Config Folder",
            variable=self.modelcheck_config_folder,
            browse_kind="directory",
            widget_ref=self._mc_config_widgets,
        )
        current_row = self._build_path_row(
            container,
            row=current_row,
            label_text="Creo Models Folder",
            variable=self.creo_models_folder,
            browse_kind="directory",
        )

        ctk.CTkLabel(
            container,
            text="Distributed Batch File",
            font=ctk.CTkFont(size=14),
            text_color="#111111",
        ).grid(row=current_row, column=0, columnspan=2, sticky="w", padx=32, pady=(0, 2))
        current_row += 1

        batch_entry = ctk.CTkEntry(
            container,
            textvariable=self.distributed_batch_file,
            width=470,
            height=28,
            corner_radius=2,
            border_width=1,
            fg_color="#FFFFFF",
            border_color="#8F98A3",
            text_color="#1F1F1F",
            font=ctk.CTkFont(size=13),
        )
        batch_entry.grid(row=current_row, column=0, sticky="w", padx=32, pady=(0, 8))
        current_row += 1

        go_button = ctk.CTkButton(
            container,
            text="GO",
            width=120,
            height=30,
            corner_radius=6,
            border_width=0,
            fg_color="#3B8ED0",
            text_color="#FFFFFF",
            hover_color="#367DB6",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._on_go,
        )
        go_button.grid(row=current_row, column=2, sticky="e", padx=(12, 28), pady=(10, 8))

        launch_button = ctk.CTkButton(
            container,
            text="Open Batch",
            width=120,
            height=30,
            corner_radius=6,
            border_width=0,
            fg_color="#3B8ED0",
            text_color="#FFFFFF",
            hover_color="#367DB6",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._launch_ptcdbatch,
        )
        launch_button.grid(row=current_row, column=1, sticky="e", padx=(12, 8), pady=(10, 8))

        kill_button = ctk.CTkButton(
            container,
            text="Kill",
            width=120,
            height=30,
            corner_radius=6,
            border_width=0,
            fg_color="#3B8ED0",
            text_color="#FFFFFF",
            hover_color="#367DB6",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._run_kill_bat,
        )
        kill_button.grid(row=current_row, column=0, sticky="e", padx=(12, 8), pady=(10, 8))

        container.grid_columnconfigure(0, weight=1)
        container.grid_columnconfigure(1, weight=0)
        container.grid_columnconfigure(2, weight=0)

    def _update_modelcheck_config_ui(self) -> None:
        enabled = self._is_modelcheck_task(self.task.get() or "")
        gray = "#9CA3AF"
        normal = "#111111"
        entry = self._mc_config_widgets.get("entry")
        browse = self._mc_config_widgets.get("browse")
        label = self._mc_config_widgets.get("label")
        if isinstance(entry, ctk.CTkEntry):
            if enabled:
                entry.configure(state="normal", text_color="#1F1F1F", fg_color="#FFFFFF")
            else:
                entry.configure(state="disabled", text_color=gray, fg_color="#E5E7EB")
        if isinstance(browse, ctk.CTkButton):
            browse.configure(state="normal" if enabled else "disabled")
        if isinstance(label, ctk.CTkLabel):
            label.configure(text_color=normal if enabled else gray)

    def _build_path_row(
        self,
        parent: ctk.CTkFrame,
        row: int,
        label_text: str,
        variable: ctk.StringVar,
        browse_kind: str,
        widget_ref: MutableMapping[str, object] | None = None,
    ) -> int:
        row_label = ctk.CTkLabel(
            parent,
            text=label_text,
            font=ctk.CTkFont(size=14),
            text_color="#111111",
        )
        row_label.grid(row=row, column=0, columnspan=2, sticky="w", padx=32, pady=(0, 2))
        if widget_ref is not None:
            widget_ref["label"] = row_label

        row += 1
        entry = ctk.CTkEntry(
            parent,
            textvariable=variable,
            width=470,
            height=28,
            corner_radius=2,
            border_width=1,
            fg_color="#FFFFFF",
            border_color="#8F98A3",
            text_color="#1F1F1F",
            font=ctk.CTkFont(size=13),
        )
        entry.grid(row=row, column=0, sticky="w", padx=32, pady=(0, 8))
        if widget_ref is not None:
            widget_ref["entry"] = entry
        if variable is self.creo_loadpoint:
            entry.bind("<FocusOut>", lambda _e: self._refresh_task_options())
            entry.bind("<Return>", lambda _e: self._refresh_task_options())

        browse_button = ctk.CTkButton(
            parent,
            text="Browse...",
            width=88,
            height=28,
            corner_radius=6,
            border_width=0,
            fg_color="#3B8ED0",
            text_color="#FFFFFF",
            hover_color="#367DB6",
            font=ctk.CTkFont(size=13),
            command=lambda: self._browse_target(variable, browse_kind),
        )
        browse_button.grid(row=row, column=1, sticky="w", padx=(8, 0), pady=(0, 8))
        if widget_ref is not None:
            widget_ref["browse"] = browse_button

        return row + 1

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
        preferred = "modelcheck.ttd"
        preferred_rows = [(fn, lab) for fn, lab in labeled if fn.lower() == preferred]
        other_rows = [(fn, lab) for fn, lab in labeled if fn.lower() != preferred]
        other_rows.sort(key=lambda row: row[1].casefold())
        ordered = (preferred_rows[:1] + other_rows) if preferred_rows else other_rows

        self._task_display_to_filename = {lab: fn for fn, lab in ordered}
        display_values = [lab for _fn, lab in ordered]

        if not display_values:
            self._task_display_to_filename = {}
            self._task_filename_to_description = {}
            self.task_select.configure(values=())
            self.task.set("")
            self._update_modelcheck_config_ui()
            return

        self.task_select.configure(values=tuple(display_values))
        self.task.set(display_values[0])
        self._update_modelcheck_config_ui()

    def _load_settings(self) -> None:
        # Blank first-run behavior: if settings file doesn't exist, keep all fields blank.
        if not self._settings_path.exists():
            self._refresh_task_options()
            return

        try:
            data = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._refresh_task_options()
            return

        self.working_directory.set((data.get("working_directory") or "").strip())
        self.creo_loadpoint.set((data.get("creo_loadpoint") or "").strip())
        self.modelcheck_config_folder.set((data.get("modelcheck_config_folder") or "").strip())
        self.creo_models_folder.set((data.get("creo_models_folder") or "").strip())
        self.distributed_batch_file.set((data.get("distributed_batch_file") or "").strip())

        self._refresh_task_options()

        saved_task_filename = (data.get("task_filename") or "").strip()
        if saved_task_filename:
            for display, filename in self._task_display_to_filename.items():
                if filename.lower() == saved_task_filename.lower():
                    self.task.set(display)
                    break
            self._update_modelcheck_config_ui()

    def _save_settings(self, task_filename: str) -> None:
        payload = {
            "working_directory": self.working_directory.get().strip(),
            "creo_loadpoint": self.creo_loadpoint.get().strip(),
            "modelcheck_config_folder": self.modelcheck_config_folder.get().strip(),
            "creo_models_folder": self.creo_models_folder.get().strip(),
            "distributed_batch_file": self.distributed_batch_file.get().strip(),
            "task_filename": task_filename.strip(),
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

    def _on_go(self) -> None:
        working_dir_raw = (self.working_directory.get() or "").strip()
        batch_name_raw = (self.distributed_batch_file.get() or "").strip()
        models_dir_raw = (self.creo_models_folder.get() or "").strip()
        config_dir_raw = (self.modelcheck_config_folder.get() or "").strip()
        loadpoint_raw = (self.creo_loadpoint.get() or "").strip().rstrip("\\/")
        task_display_raw = (self.task.get() or "").strip()
        task_filename = self._task_filename_from_ui(task_display_raw)

        if not working_dir_raw:
            messagebox.showwarning("Missing Working Directory", "Please enter a working directory.")
            return
        if not batch_name_raw:
            messagebox.showwarning("Missing Batch File Name", "Please enter a distributed batch file name.")
            return
        if not models_dir_raw:
            messagebox.showwarning("Missing Creo Models Folder", "Please enter a Creo models folder.")
            return
        use_modelcheck_config = self._is_modelcheck_task(task_display_raw)
        if use_modelcheck_config and not config_dir_raw:
            messagebox.showwarning("Missing Modelcheck Config Folder", "Please enter a modelcheck config folder.")
            return
        if not loadpoint_raw:
            messagebox.showwarning("Missing Creo Loadpoint", "Please enter a Creo loadpoint.")
            return
        if not task_display_raw or not task_filename:
            messagebox.showwarning("Missing Task", "Please select a task.")
            return

        # User provides the base name; enforce .dxc output.
        batch_name = batch_name_raw.removesuffix(".dxc")
        dcx_file_path = Path(working_dir_raw) / f"{batch_name}.dxc"
        models_dir = Path(models_dir_raw)
        config_dir = Path(config_dir_raw) if config_dir_raw else None
        ttd_path = Path(loadpoint_raw) / "Common Files" / "text" / "ttds" / task_filename
        group_name = self._task_filename_to_description.get(task_filename) or self._read_ttd_description(
            ttd_path
        )
        group_name_attr = _xml_attr_escape(group_name)

        try:
            models_dir.mkdir(parents=True, exist_ok=True)
            if use_modelcheck_config and config_dir is not None:
                config_dir.mkdir(parents=True, exist_ok=True)
            scanned = self._scan_models_non_recursive(models_dir)
            latest_files = self._get_latest_model_files(scanned)
            config_files = self._scan_files_recursive(config_dir) if use_modelcheck_config and config_dir else []
            model_chunks = self._chunk_paths(latest_files, 10)
            if not model_chunks:
                model_chunks = [[]]

            dcx_file_path.parent.mkdir(parents=True, exist_ok=True)
            group_blocks: list[str] = []
            for chunk in model_chunks:
                group_lines = [
                    f'    <Group DSQM="_LOCAL" Name="{group_name_attr}" Output="2" '
                    f'OutputDir="{_xml_attr_escape(working_dir_raw)}" PrimaryContent="0" '
                    f'TTD="{_xml_attr_escape(str(ttd_path))}" VaultResults="0">'
                ]
                group_lines.extend(f"        <Object>{str(p)}</Object>" for p in chunk)
                if config_files:
                    group_lines.extend(f"        <ConfigFile>{str(p)}</ConfigFile>" for p in config_files)
                group_lines.append("    </Group>")
                group_blocks.append("\n".join(group_lines))

            data_block = "\n".join(group_blocks)
            if data_block:
                data_block += "\n"
            file_content = f"<DXC>\n    <Windchill/>\n{data_block}</DXC>\n"
            dcx_file_path.write_text(file_content, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Create File Failed", f"Could not create file:\n{dcx_file_path}\n\n{exc}")
            return

        messagebox.showinfo(
            "Success",
            f"Created file:\n{dcx_file_path}\n\n"
            f"Wrote {len(config_files)} config file(s) and {len(latest_files)} model object(s).",
        )
        self._save_settings(task_filename)

    def _launch_ptcdbatch(self) -> None:
        loadpoint_raw = (self.creo_loadpoint.get() or "").strip().rstrip("\\/")
        working_dir_raw = (self.working_directory.get() or "").strip()
        batch_name_raw = (self.distributed_batch_file.get() or "").strip()
        if not loadpoint_raw:
            messagebox.showwarning("Missing Creo Loadpoint", "Please enter a Creo loadpoint.")
            return
        if not working_dir_raw:
            messagebox.showwarning("Missing Working Directory", "Please enter a working directory.")
            return
        if not batch_name_raw:
            messagebox.showwarning("Missing Batch File Name", "Please enter a distributed batch file name.")
            return

        bat_path = Path(loadpoint_raw) / "Parametric" / "bin" / "ptcdbatch.bat"
        if not bat_path.exists():
            messagebox.showerror("File Not Found", f"Could not find:\n{bat_path}")
            return

        batch_name = batch_name_raw.removesuffix(".dxc")
        dxc_path = Path(working_dir_raw) / f"{batch_name}.dxc"
        if not dxc_path.exists():
            messagebox.showerror("File Not Found", f"Could not find:\n{dxc_path}\n\nCreate it with GO first.")
            return

        try:
            bat_ps = str(bat_path).replace("'", "''")
            dxc_ps = str(dxc_path).replace("'", "''")
            ps_exe = self._resolve_powershell_exe()
            if not ps_exe:
                messagebox.showerror("PowerShell Not Found", "Could not locate powershell.exe.")
                return
            subprocess.Popen(
                [
                    ps_exe,
                    "-NoExit",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    f"& '{bat_ps}' '{dxc_ps}'",
                ],
                cwd=str(bat_path.parent),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        except OSError as exc:
            messagebox.showerror(
                "Launch Failed",
                f"Could not launch:\n{bat_path}\n\nwith:\n{dxc_path}\n\n{exc}",
            )

    def _run_kill_bat(self) -> None:
        kill_path = Path(__file__).resolve().parent / "kill.bat"
        if not kill_path.exists():
            messagebox.showerror("File Not Found", f"Could not find:\n{kill_path}")
            return
        try:
            kill_ps = str(kill_path).replace("'", "''")
            ps_exe = self._resolve_powershell_exe()
            if not ps_exe:
                messagebox.showerror("PowerShell Not Found", "Could not locate powershell.exe.")
                return
            subprocess.Popen(
                [
                    ps_exe,
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    f"& '{kill_ps}'",
                ],
                cwd=str(kill_path.parent),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        except OSError as exc:
            messagebox.showerror("Launch Failed", f"Could not launch:\n{kill_path}\n\n{exc}")

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
