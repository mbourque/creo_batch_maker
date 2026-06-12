# PDSVISION Cad Assessment Tool

Windows desktop utility for building Creo distributed batch (`.dxc`) files from models in a folder and running them through `Parametric\bin\ptcdbatch.bat` via a generated PowerShell runner.

## What this app does

- GUI for working directory, Creo loadpoint, and task (paths are set with Browse… only).
- Reads task labels from `modelcheck.ttd`, `solid-raster_write_jpg.ttd`, and `plot_jpeg_a-size.ttd` under your loadpoint’s `Common Files\text\ttds` (not every `.ttd` on disk), plus **Scan Templates** when at least one template model exists in `<working_directory>\templates` (upload via **Configuration → Templates…**; first in the Task list — not a separate `.ttd`; runs ModelCHECK on those templates), and **Create Report** when ModelCHECK result XML (`*.p.xml`, `*.a.xml`, `*.d.xml`) and at least one `.jpg` exist in the working folder (last in the Task list — not a `.ttd`). On startup (and when the task list is rebuilt with no prior selection), if template scan XML already exists in `templates\`, **Task** defaults to **ModelCHECK** instead of **Scan Templates**. **Report** is shown only for **Create Report**; **GO** is hidden for **Create Report**.
- **GO** (batch tasks only) clears any prior batch artifacts, writes `.dxc` file(s) and a task-specific runner (`creo-batch-modelcheck.ps1`, `creo-batch-jpeg3d.ps1`, `creo-batch-jpeg2d.ps1`, or `templates\creo-batch-scan-templates.ps1`), then launches that script in PowerShell automatically — no success dialog. **ModelCHECK** — chunk `.dxc` files in the working folder (models per chunk: **Settings → Chunk size…**, default 10, non-recursive scan) plus `creo-batch-modelcheck.ps1`; includes `.prt`, `.asm`, and `.drw` in the working directory; ModelCHECK outputs (XML, HTML, etc.) go in the working folder; references all files under `configs\` as `<ConfigFile>` entries. On **GO**, if template scan XML exists under `<working_directory>\templates\` (`part_template.p.xml`, `assembly_template.a.xml`, and/or `drawing_template.d.xml` from a prior **Scan Templates** run), the app updates **`configs\sample_start.mcs`** (PRT/ASM/DRW parameter and layer blocks; DRW symbols from ``SYMBOL_INFO``) before building and launching the batch. Sections with no template XML are reset to anchor comments only (``! PRT_PARAMETER``, etc.). Template extraction failures show an error dialog. **Scan Templates** — one `templates.dxc` and `creo-batch-scan-templates.ps1` in `<working_directory>\templates` (upload template models with **Configuration → Templates…** first; GO is blocked until at least one `.prt`, `.asm`, or `.drw` is there); runs ModelCHECK on those files in order **part → assembly → drawing**; ModelCHECK outputs go in `templates\` beside the template models (not the working-directory root); references `configs\templates\` only; GO runs the runner from `templates\`. **JPEG 3D** includes `.prt` and `.asm` only; **JPEG 2D Export to file, A Paper Size** includes `.drw` only.
- The PowerShell runner runs `ptcdbatch.bat -nographics -process` per chunk, polls for expected output files (inactivity timeout: **Settings → Timeout…**, default **120** seconds), runs `kill.bat`, then deletes the chunk `.dxc` files when finished. At the end it logs **Count of Files Success** and **Count of Files Timed Out** (per expected output file, including skips where outputs already existed).
- **Report** (Create Report task only) first merges ModelCHECK result XML (`*.p.xml`, `*.a.xml`, `*.d.xml`) into **`master.xml`** in the working folder and removes leftover batch runner `.ps1` files from the working folder and `templates\`, then runs in the background (button shows **Report…** while working). **Model Units for Length** on parts/assemblies comes from the Creo **`UNITS_LENGTH`** check in each `*.p.xml` / `*.a.xml` (not drawings). It copies `<creo_loadpoint>/Common Files/modchk` to `<working_directory>/modchk` and patches ModelCHECK `*.html` in the working folder (except **`index.html`**) so offline links work, then reads `master.xml` plus bundled **`model_checks.xml`** and **`report_template.html.j2`**, and writes **`index.html`** — a Model Quality Report with a **score dashboard** (visible issues and models with warnings/errors update when you remove items; files/parts/assemblies/drawings scanned and PASS check totals stay fixed from the batch so grades use warnings/errors as a percentage of all checks, not only remaining issues), **batch statistics** embedded under the score (sidebar **Statistics** jumps to that section on the same page; **At a glance** rows link to the matching check section and reset **Filter view** to show all), a left sidebar of checks that had **errors or warnings** (A–Z by check name; **Filter view** dropdown (show all, warnings, errors, flagged, unflagged, by model type — Parts / Assemblies / Drawings, or by category; options drop away as you remove sections)), and per-model detail (thumbnails, messages, links). Removing sections or models in the browser updates the adjusted score and category grades (Model Quality, Model Integrity, etc.) for what is still shown. After you remove items or flag models, the sidebar **Save** button appears. Use **Save index.html** in the dialog to write the current report (including flags, removals, and the active **Filter view**) over **`index.html`** in the working folder — browser **Ctrl+S** alone often does not keep those edits on a local report. If you remove or flag something in this browser session and try to refresh or close the tab without saving, the browser shows its standard “leave site?” warning (wording varies by browser). Large folders can take a few minutes; the window stays responsive. The only dialog at the end is **Open in browser?**. Same patch logic is available as `python patch.py` for development.
- **`make_html_statistics.py`** — optional standalone preview of batch statistics: `python make_html_statistics.py` (uses **`working_directory`** from `app_settings.json`, writes **`statistics.html`**). The same rollup is embedded in **`index.html`** when you run **Report**. Batch rollup: models skipped, top-level assembly, skeleton models, family tables, at a glance, model complexity (scan totals stay on the score dashboard).

## Requirements

- Windows
- A Creo loadpoint that contains `Parametric` (so `Parametric\bin\ptcdbatch.bat` exists) and the usual `Common Files\text\ttds` content
- In the same folder as the app you run (`main.exe` or `main.py`): `kill.bat`, `model_checks.xml`, and `report_template.html.j2` (for **Report**). For **ModelCHECK** jobs, a `configs` folder with the modelcheck files you want referenced in the `.dxc` (`<ConfigFile>` entries). For **Scan Templates**, `configs\templates\` (separate from the full `configs\` set). For **JPEG 3D** and **JPEG 2D** jobs, `configs\config.pro` is included as a single `<Config>` entry in each chunk `.dxc`.
- **Working directory** path must **not contain spaces** (required for **GO**). **Report** is not blocked by spaces.

## No Python needed

```powershell
.\main.exe
```

Launch options:

- In File Explorer: double-click `main.exe`.
- In PowerShell: run `.\main.exe` from the folder that contains the executable.

Usage:

- Use Browse… to set the working directory (models live there; outputs go there), Creo loadpoint, and task.
- **GO** generates the chunk `.dxc` files and the task-specific `.ps1` runner, launches PowerShell automatically, and updates `app_settings.json` when all checks pass. Run **GO** again after a finished batch run, because the runner deletes the `.dxc` file(s). When **GO** launches successfully, **Task** advances: **Scan Templates** → **ModelCHECK** → JPEG 3D → **Create Report** (when ModelCHECK XML and `.jpg` files are present). The app rechecks for **Create Report** after **GO**, while a batch is running, and when you return to the window — no restart needed.
- On **Create Report**, **Report** builds `master.xml` and generates `index.html` in one step.

## Menus

### File

- **New**, **Open…**, **Save**, **Save as…**, **Open Working Directory**, **Start over…**, **Exit** — working directory, loadpoint, chunk size, and timeout as JSON (`app_settings.json` or a file you choose; the selected **Task** is not stored). **Open Working Directory** opens the current working folder in File Explorer. **Start over…** asks for confirmation (Cancel is default), then removes prior scan and batch data from the working folder and `templates\` (if present), keeping only Creo models (`.prt`, `.asm`, `.drw`).

### Settings

Always visible. Values are stored in `app_settings.json` (also written on successful **GO** and **File → Save**).

- **Chunk size…** — models per `creo-batch-N.dxc` chunk (**1–10**, default **10**). JSON key: `chunk_size`. Run **GO** again after changing.
- **Timeout…** — seconds to wait for chunk output files with no new file appearing (**whole number ≥ 60**, default **120**). JSON key: `output_timeout_sec`. Run **GO** again after changing.

### Configuration

Opens bundled ModelCHECK files from the app’s `configs\` folder in Notepad (available for all tasks). This menu used to be named **Settings**; it was renamed to **Configuration** so **Settings** could hold app-wide options (chunk size, timeout, etc.).


- Model Checks…, Config.pro…, Angles…, GMC…, Modelcheck Config…, Defaults…, Designers…, Holes…, Inch Settings…, Metric Settings…, Sheetmetal Thickness…
- **Templates…** — **Part…**, **Assembly…**, and **Drawing…** copy a chosen Creo model into `<working_directory>\templates\` as `part_template.prt`, `assembly_template.asm`, or `drawing_template.drw` (requires a valid working directory). After a successful copy, **Task** is set to **Scan Templates**.
- **Open configurations…** — opens the `configs\` folder in File Explorer (formerly **Open settings…**).

### Help

- **About…** (creator and PDSVISION)

## Install with Python

Python 3.10+ recommended. Create a virtual environment and install packages from `requirements.txt`:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Those packages include `customtkinter` and `Pillow` for the current project.

## Run

```powershell
python .\main.py
```

## Documentation

See the [documentation wiki page](https://github.com/mbourque/creo_batch_maker/wiki/Documentation) for full usage, safety notes, and troubleshooting.
