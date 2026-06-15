# PDSVISION Cad Assessment Tool

Windows desktop utility for building Creo distributed batch (`.dxc`) files from models in a folder and running them through `Parametric\bin\ptcdbatch.bat` via a generated PowerShell runner.

## What this app does

- Wizard-style main window: **Setup → Scan Templates → ModelCHECK → JPEG 3D → Create Report**. Use **Next >**, **< Back**, **Skip** (where available), and step-specific actions (no Task dropdown). **Skip** is shown only before you run that step’s batch (when outputs already exist from a prior run); after a batch finishes, only **Next >** appears. **< Back** is disabled while a batch step shows **Waiting…**. A stepper at the top shows progress (✓ done, — skipped).
- **Setup** — working directory and Creo loadpoint (Browse… only). When **`index.html`** already exists in the working folder, a green status line and **Open Report** on the left open it in your browser. If the folder has no top-level `.prt`, `.asm`, or `.drw` files, a red status line appears and **Next >** shows a warning (zip files and subfolders are not scanned). **Next >** validates paths and continues only when models are present.
- **Scan Templates** (optional) — three **Browse…** rows copy templates to `part_template.prt`, `assembly_template.asm`, and `drawing_template.drw` under `<working_directory>\templates`. Assembly and drawing rows are shown only when the working folder contains top-level `.asm` or `.drw` files (or when that template is already uploaded). **Browse…** and **×** are disabled while a scan batch is running (**Waiting…**). A **×** next to **Browse…** removes that template and its ModelCHECK outputs (`.xml`, detail `.html`, related `.js`) from `templates\`. **Skip** when no templates are uploaded, or when template scan XML already exists from a prior run. **Scan Templates >** runs ModelCHECK on uploaded templates. **Next >** enables when the runner removes `templates.dxc` after that job finishes (including when outputs were already present); clicking **Next >** then removes ModelCHECK detail files (`.html`, `.js`, `.png`, `.css`) and `creo-batch-scan-templates.ps1` from `templates\`, keeping the template models and `.xml` files (skipped when **Settings → Debug** is on).
- **ModelCHECK** — **Run ModelCHECK >** writes chunk `.dxc` files and launches PowerShell. **Skip** when ModelCHECK result XML (`*.p.xml`, `*.a.xml`, `*.d.xml`) already exists in the working folder. **Waiting…** until `creo-batch-*.dxc` files are gone; then **Next >** advances one step. If any models fail (expected outputs never appear before the inactivity timeout), a red **Failed (N):** line under the progress bar lists every failed model as the batch run writes **`creo-batch-timeouts-modelcheck.txt`**. That log is removed when you start a new ModelCHECK run or use **Start over…**.
- **JPEG 3D** — **Run JPEG 3D >** same flow. **Skip** when `.jpg` files already exist in the working folder. **Next >** advances to **Create Report**. Failed models update live the same way (**`creo-batch-timeouts-jpeg3d.txt`**).
- **Create Report** — **Create Report** merges ModelCHECK XML into **`master.xml`**, removes leftover runner `.ps1` files (unless **Settings → Debug** is on), then builds **`index.html`** in the background (score dashboard, **Scan Information** rollup, filterable check sidebar including **Sort by issue count**; **Show flagged** / **Show unflagged** appear only when those items exist, per-model detail). Per-model warning/error lines use **`msgs_warning.png`** / **`msgs_error.png`** from the working folder (relative to **`index.html`**). Thumbnail links drag the Creo model file (`.prt`/`.asm`/`.drw`) into Creo, not the JPEG preview — open the report from the working folder so relative paths resolve. When **`index.html`** already exists, **Open Report** opens it in your browser without rebuilding. Only dialog after a new build: **Open in browser?**
- On every batch step (**Scan Templates**, **ModelCHECK**, **JPEG 3D**, and other chunk-based tasks such as **JPEG 2D**), the PowerShell runner runs `ptcdbatch.bat -nographics -process`, polls for expected output files (inactivity timeout: **Settings → Timeout…**, default **120** seconds; the timer **starts when `xtop.exe` first appears**, resets when a file appears or while **`xtop`** is still running), waits for **`xtop.exe`** to exit after outputs are done, then runs `kill.bat`, then removes that step’s `.dxc` when each chunk (or the single scan job) finishes so the wizard progress bar advances during the run. While waiting for outputs, if **`xtop.exe`** was running and then stays gone for **2** consecutive polls with no restart within **10** seconds (checked every **2** s), the runner treats the chunk like a timeout and moves on (logged as **`XTOP GONE:`** in red). **Next >** stays disabled (**Waiting…**) until every `.dxc` for that step is gone (the runner console may stay open so you can read the log). The runner opens in a **minimized** console (restore from the taskbar to read the log). While a batch step runs, a progress bar on that step tracks remaining `.dxc` files and stays at 100% once **Next >** is available. On **ModelCHECK** and **JPEG 3D**, the progress line shows **Estimating time…** as soon as the batch starts; after enough chunks finish (2+ for larger batches, 1 for a 1–2 chunk run), it shows a rough ETA (e.g. **~6 min remaining**) that **updates only when each chunk completes**, not while a chunk is still running. The runner console closes when you click **Next >** or **Skip** on that step.
- After JPEG 3D, the wizard moves to **Create Report** when ModelCHECK XML and `.jpg` files are present (also rechecked while a batch runs and when you return to the app).
- **`make_html_statistics.py`** — optional standalone preview of batch statistics: `python make_html_statistics.py` (uses **`working_directory`** from `app_settings.json`, writes **`statistics.html`**). The same rollup is embedded in **`index.html`** when you run **Create Report**. Batch rollup: models skipped, top-level assembly (with a full-width BOM table from that assembly’s `.a.xml` — model name, error count, warning count — when available), skeleton models, family tables, at a glance, model complexity (scan totals stay on the score dashboard). In **`index.html`**, BOM rows are clickable (same row-hover style as **At a glance**) and scroll to that model in the report.

## Requirements

- Windows
- A Creo loadpoint that contains `Parametric` (so `Parametric\bin\ptcdbatch.bat` exists) and the usual `Common Files\text\ttds` content
- In the same folder as the app you run (`main.exe` or `main.py`): `kill.bat`, `model_checks.xml`, and `report_template.html.j2` (for **Report**). **`kill.bat`** waits up to **30** seconds for **`xtop.exe`** to exit on its own (poll every **2** s), then force-kills Creo batch processes. For **ModelCHECK** jobs, a `configs` folder with the modelcheck files you want referenced in the `.dxc` (`<ConfigFile>` entries). For **Scan Templates**, `configs\templates\` (separate from the full `configs\` set). For **JPEG 3D** and **JPEG 2D** jobs, `configs\config.pro` is included as a single `<Config>` entry in each chunk `.dxc`.
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

- **New**, **Open…**, **Save**, **Save as…**, **Open Working Directory**, **Zip report…**, **Stop**, **Start over…**, **Exit** — working directory, loadpoint, chunk size, and timeout as JSON (`app_settings.json` or a file you choose; wizard step is not stored). **Open Working Directory** opens the current working folder in File Explorer. **Zip report…** (enabled on **Setup** and **Create Report** only, when **`index.html`** exists and no batch or report job is running) writes **`{folder-name}-report.zip`** there with a **`report\`** folder containing the report files (`index.html`, detail pages, images, top-level `.prt`/`.asm`/`.drw` models, etc.), plus **`modchk\`** and **`templates\`** when those folders exist in the working directory, and an **`Open Report.bat`** launcher beside it that opens **`report\index.html`** in your browser. **Stop** (enabled while a batch step is **Waiting…**) asks for confirmation, closes the PowerShell runner, runs `kill.bat`, and returns the wizard to a ready state on the current step — outputs already written are kept; run that step again to continue (the runner skips models whose outputs already exist). **Start over…** asks for confirmation (Cancel is default), then removes prior scan and batch data from the working folder and `templates\` (if present), including all batch failure logs (`creo-batch-timeouts-*.txt`, including `creo-batch-timeouts-modelcheck.txt` and `creo-batch-timeouts-jpeg3d.txt`), while keeping Creo models (`.prt`, `.asm`, `.drw`) in both places, and returns the wizard to **Setup**. **Stop** and **Exit** stay available during a batch (**Stop** only while **Waiting…**). Other **File** items, **Settings**, and **Configuration** are enabled only on the **Setup** step when no batch or report job is running (**Zip report…** is also on **Create Report** when a report exists — see above). **Help** stays available. **Exit** stops the PowerShell batch runner if any, then closes the app (same as the window **×** button).

### Settings

Enabled on the **Setup** step only (see **File** above). Values are stored in `app_settings.json` (also written on successful batch launch and **File → Save**).

- **Chunk size…** — models per `creo-batch-N.dxc` chunk (**1–10**, default **10**). JSON key: `chunk_size`. Re-run the ModelCHECK wizard step after changing.
- **Timeout…** — seconds to wait for chunk output files with no new file appearing (**whole number ≥ 60**, default **120**). JSON key: `output_timeout_sec`. Re-run the batch wizard step after changing.
- **Automatic mode** (checkbox) — after **Scan Templates >** finishes, automatically advances to **ModelCHECK** and starts that batch; when ModelCHECK finishes, advances to **JPEG 3D**, runs that batch, then **Create Report** when JPEG finishes. The **Open in browser?** dialog still appears when the report is done so you can choose whether to open it. While Automatic mode is on, the batch PowerShell runner is **hidden** (no taskbar console); with it off, the runner opens **minimized** so you can restore it to read the log. ModelCHECK and JPEG 3D steps show a blue **Automatic mode** note in the progress area. JSON key: `automatic_mode` (default **on**).
- **Debug** (checkbox, under Automatic mode) — when on, batch PowerShell runner windows are always shown (even in Automatic mode) and **never closed by the app** (after **Next >**, **Stop**, **Start over…**, **Exit**, or starting another batch — close them yourself). Generated **`creo-batch-*.ps1`** runners are **not deleted** (on **GO**, **Create Report**, or **Next >** after Scan Templates). **Next >** after Scan Templates also keeps ModelCHECK detail files (`.html`, `.js`, `.png`, `.css`) in **`templates\`**. After a successful **Create Report**, **`master.xml`** is kept; when off (default), **`master.xml`** is removed from the working folder once **`index.html`** is written. JSON key: `debug_mode` (default **off**).

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
