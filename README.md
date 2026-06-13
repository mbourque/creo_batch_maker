# PDSVISION Cad Assessment Tool

Windows desktop utility for building Creo distributed batch (`.dxc`) files from models in a folder and running them through `Parametric\bin\ptcdbatch.bat` via a generated PowerShell runner.

## What this app does

- Wizard-style main window: **Setup → Scan Templates → ModelCHECK → JPEG 3D → Create Report**. Use **Next >**, **< Back**, **Skip** (where available), and step-specific actions (no Task dropdown). **Skip** is shown only before you run that step’s batch (when outputs already exist from a prior run); after a batch finishes, only **Next >** appears. **< Back** is disabled while a batch step shows **Waiting…**. A stepper at the top shows progress (✓ done, — skipped).
- **Setup** — working directory and Creo loadpoint (Browse… only). When **`index.html`** already exists in the working folder, a green status line and **Open Report** on the left open it in your browser. Browsing the working folder here does not warn about missing models or templates. **Next >** validates paths and continues.
- **Scan Templates** (optional) — three **Browse…** rows copy templates to `part_template.prt`, `assembly_template.asm`, and `drawing_template.drw` under `<working_directory>\templates`. Assembly and drawing rows are shown only when the working folder contains top-level `.asm` or `.drw` files (or when that template is already uploaded). **Browse…** and **×** are disabled while a scan batch is running (**Waiting…**). A **×** next to **Browse…** removes that template and its ModelCHECK outputs (`.xml`, detail `.html`, related `.js`) from `templates\`. **Skip** when no templates are uploaded, or when template scan XML already exists from a prior run. **Scan Templates >** runs ModelCHECK on uploaded templates. **Next >** enables when the runner removes `templates.dxc` after that job finishes (including when outputs were already present).
- **ModelCHECK** — **Run ModelCHECK >** writes chunk `.dxc` files and launches PowerShell. **Skip** when ModelCHECK result XML (`*.p.xml`, `*.a.xml`, `*.d.xml`) already exists in the working folder. **Waiting…** until `creo-batch-*.dxc` files are gone; then **Next >** advances one step.
- **JPEG 3D** — **Run JPEG 3D >** same flow. **Skip** when `.jpg` files already exist in the working folder. **Next >** advances to **Create Report**.
- **Create Report** — **Create Report** merges ModelCHECK XML into **`master.xml`**, removes leftover runner `.ps1` files, then builds **`index.html`** in the background (score dashboard, batch statistics, filterable check sidebar including **Sort by issue count**; **Show flagged** / **Show unflagged** appear only when those items exist, per-model detail). Thumbnail links drag the Creo model file (`.prt`/`.asm`/`.drw`) into Creo, not the JPEG preview — open the report from the working folder so relative paths resolve. When **`index.html`** already exists, **Open Report** opens it in your browser without rebuilding. Only dialog after a new build: **Open in browser?**
- On every batch step (**Scan Templates**, **ModelCHECK**, **JPEG 3D**, and other chunk-based tasks such as **JPEG 2D**), the PowerShell runner runs `ptcdbatch.bat -nographics -process`, polls for expected output files (inactivity timeout: **Settings → Timeout…**, default **120** seconds), runs `kill.bat`, then removes that step’s `.dxc` when each chunk (or the single scan job) finishes so the wizard progress bar advances during the run. **Next >** stays disabled (**Waiting…**) until every `.dxc` for that step is gone (the runner console may stay open so you can read the log). The runner opens in a **minimized** console (restore from the taskbar to read the log). While a batch step runs, a progress bar on that step tracks remaining `.dxc` files and stays at 100% once **Next >** is available. The runner console closes when you click **Next >** or **Skip** on that step.
- After JPEG 3D, the wizard moves to **Create Report** when ModelCHECK XML and `.jpg` files are present (also rechecked while a batch runs and when you return to the app).
- **`make_html_statistics.py`** — optional standalone preview of batch statistics: `python make_html_statistics.py` (uses **`working_directory`** from `app_settings.json`, writes **`statistics.html`**). The same rollup is embedded in **`index.html`** when you run **Create Report**. Batch rollup: models skipped, top-level assembly, skeleton models, family tables, at a glance, model complexity (scan totals stay on the score dashboard).

## Requirements

- Windows
- A Creo loadpoint that contains `Parametric` (so `Parametric\bin\ptcdbatch.bat` exists) and the usual `Common Files\text\ttds` content
- In the same folder as the app you run (`main.exe` or `main.py`): `kill.bat`, `model_checks.xml`, and `report_template.html.j2` (for **Report**). For **ModelCHECK** jobs, a `configs` folder with the modelcheck files you want referenced in the `.dxc` (`<ConfigFile>` entries). For **Scan Templates**, `configs\templates\` (separate from the full `configs\` set). For **JPEG 3D** and **JPEG 2D** jobs, `configs\config.pro` is included as a single `<Config>` entry in each chunk `.dxc`.
- **Working directory** path must **not contain spaces** (required for batch steps). **Create report** is not blocked by spaces.

## No Python needed

```powershell
.\main.exe
```

Launch options:

- In File Explorer: double-click `main.exe`.
- In PowerShell: run `.\main.exe` from the folder that contains the executable.

Usage:

- Follow the wizard: **Setup** → optional **Scan Templates** → **ModelCHECK** → **JPEG 3D** → **Create Report**. Use **< Back** to revisit an earlier step (batch outputs on disk are not undone). Run a batch step again after a finished run if needed — the runner deletes `.dxc` file(s). Settings are saved to `app_settings.json` on successful batch launch and via **File → Save**.

## Menus

### File

- **New**, **Open…**, **Save**, **Save as…**, **Open Working Directory**, **Start over…**, **Exit** — working directory, loadpoint, chunk size, and timeout as JSON (`app_settings.json` or a file you choose; wizard step is not stored). **Open Working Directory** opens the current working folder in File Explorer. **Start over…** asks for confirmation (Cancel is default), then removes prior scan and batch data from the working folder and `templates\` (if present), while keeping Creo models (`.prt`, `.asm`, `.drw`) in both places, and returns the wizard to **Setup**.

### Settings

Always visible. Values are stored in `app_settings.json` (also written on successful batch launch and **File → Save**).

- **Chunk size…** — models per `creo-batch-N.dxc` chunk (**1–10**, default **10**). JSON key: `chunk_size`. Re-run the ModelCHECK wizard step after changing.
- **Timeout…** — seconds to wait for chunk output files with no new file appearing (**whole number ≥ 60**, default **120**). JSON key: `output_timeout_sec`. Re-run the batch wizard step after changing.

### Configuration

Opens bundled ModelCHECK files from the app’s `configs\` folder in Notepad (available for all tasks). This menu used to be named **Settings**; it was renamed to **Configuration** so **Settings** could hold app-wide options (chunk size, timeout, etc.).


- Model Checks…, Config.pro…, Angles…, GMC…, Modelcheck Config…, Defaults…, Designers…, Holes…, Inch Settings…, Metric Settings…, Sheetmetal Thickness…
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
