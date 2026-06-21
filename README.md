# PDSVISION Cad Assessment Tool

Windows desktop utility for building Creo distributed batch (`.dxc`) files from models in a folder and running them through `Parametric\bin\ptcdbatch.bat` via a generated PowerShell runner.

## What this app does

- Wizard-style main window: **Setup → Scan Templates → ModelCHECK → Thumbnails → Create Report**. Use **Next >**, **< Back**, **Skip** (where available), and step-specific actions (no Task dropdown). **Skip** on **Scan Templates** follows the rules below. **Skip** on **ModelCHECK** and **Thumbnails** is always shown except while **Waiting…** (you do not need to restart the app). After a batch finishes, **Next >** advances; **Skip** also advances without re-running. **< Back** is disabled while a batch step shows **Waiting…**. A stepper at the top shows progress (✓ done, — skipped).
- **Setup** — working directory and Creo loadpoint (Browse… only). When **`index.html`** already exists in the working folder, a green status line and **Open Report** on the left open it in your browser. If the folder has no top-level `.prt`, `.asm`, or `.drw` files, a red status line appears and **Next >** shows a warning (zip files and subfolders are not scanned). **Next >** validates paths and continues only when models are present.
- **Scan Templates** (optional) — three **Browse…** rows copy templates to `part_template.prt`, `assembly_template.asm`, and `drawing_template.drw` under `<working_directory>\templates`. Assembly and drawing rows are shown only when the working folder contains top-level `.asm` or `.drw` files (or when that template is already uploaded). **Browse…** and **×** are disabled while a scan batch is running (**Waiting…**). A **×** next to **Browse…** removes that template and its ModelCHECK outputs (`.xml`, detail `.html`, related `.js`) from `templates\`. **Skip** when no templates are uploaded, or when template scan XML already exists from a prior run — **Skip** clears extracted template parameters/layers from **`configs\sample_start.mcs`** (anchor comments only). ModelCHECK **GO** will not re-apply template XML unless you completed **Scan Templates** in this run. The MCS file lives next to the app (`main.py` / `main.exe`), not in the working directory. **Scan Templates >** always runs ModelCHECK on uploaded templates (even when template `.xml` files already exist); **Next >** appears only after that batch finishes successfully in the current session. Use **< Back** to return to Scan Templates and run **Scan Templates >** again (no app restart needed). If scan fails, **Automatic mode stops**, the wizard stays on Scan Templates, and you must fix the issue and run **Scan Templates >** again. Clicking **Next >** removes ModelCHECK detail files (`.html`, `.js`, `.png`, `.css`) and `creo-batch-scan-templates.ps1` from `templates\`, keeping the template models and `.xml` files (skipped when **Settings → Debug** is on).
- **ModelCHECK** — **Run ModelCHECK >** scans the working folder first and builds `.dxc` chunks only for models still missing ModelCHECK XML (`*.p.xml`, `*.a.xml`, `*.d.xml`). **Waiting…** until `creo-batch-*.dxc` files are gone. **Next >** appears only when every model has ModelCHECK XML (not merely when the last batch run finished). If a run completes with models still missing output, **Run ModelCHECK >** stays available so you can continue. If any models fail, a red **Failed (N): Click here to review files** line under the progress bar opens **`creo-batch-timeouts-modelcheck.txt`** in Notepad. Failure logs are cleared when **Run ModelCHECK >** or **Thumbnails >** writes new `.dxc` files for that phase only (`creo-batch-timeouts-modelcheck.txt`, `creo-batch-timeouts-jpeg3d_part.txt`, `creo-batch-timeouts-jpeg3d_asm.txt`, or `creo-batch-timeouts-jpeg2d.txt` — other steps' logs are untouched). The red **Failed (N)** line then reflects only failures from the current run; each chunk appends new timeouts (**Stop**, inactivity, **XTOP GONE**). Logs are removed entirely only by **Start over…**. While a batch runs, the failed count updates from the log. When a failure log still lists models missing output and you run **Run ModelCHECK >** again (manual or **Automatic mode**), the app runs **failed models only**: **Retry failed only (one model per batch)** (default — one `.dxc` per failed model) or **Retry failed only (normal chunking)** (failed models only, Settings chunk size). **Cancel** aborts GO. With no pending failures, GO batches only models still missing XML. **Skip** is always available on this step (except while **Waiting…**) to advance without running ModelCHECK.
- **Thumbnails** — Three sequential passes when the working folder has matching models: **parts** (`.prt` → `*.part.jpg`), **assemblies** (`.asm` → `*.assembly.jpg`), then **drawings** (`.drw` → `*.drawing.jpg`). Each pass has its own progress bar; passes with no matching models are skipped. When one pass’s batch run finishes, the next pass starts automatically (even if some models failed in the prior pass). Same output-first rules and failed-only retry as ModelCHECK. Failure logs: **`creo-batch-timeouts-jpeg3d_part.txt`**, **`creo-batch-timeouts-jpeg3d_asm.txt`**, **`creo-batch-timeouts-jpeg2d.txt`** (legacy **`jpeg3d.txt`** is still read). Creo batch `*.jpg` files are renamed after each pass. The report uses type-specific thumbnails and falls back to legacy **`*.model.jpg`** when present. **Skip** is always available (except while **Waiting…**).
- **Create Report** — **Create Report** merges ModelCHECK XML into **`master.xml`**, removes leftover runner `.ps1` files (unless **Settings → Debug** is on), then builds **`index.html`** in the background (score dashboard, **Scan Information** rollup — including **Templates scanned (one/two/all three):** part, assembly, and/or drawing only when **Scan Templates** completed in this run (not **Skip**); a small **`templates\creo-batch-template-scan.json`** records that outcome, filterable check sidebar including **Sort by issue count**; **Show flagged** / **Show unflagged** appear only when those items exist, per-model detail). Per-model warning/error lines use **`msgs_warning.png`** / **`msgs_error.png`** from the working folder (relative to **`index.html`**). Thumbnail links drag the Creo model file (`.prt`/`.asm`/`.drw`) into Creo, not the JPEG preview — open the report from the working folder so relative paths resolve. When **`index.html`** already exists, **Open Report** opens it in your browser without rebuilding. If ModelCHECK or **Thumbnails** had failed models, the report step lists each with a count and a **here** link to open **`creo-batch-timeouts-modelcheck.txt`** or **`creo-batch-timeouts-jpeg3d.txt`** in Notepad. Only dialog after a new build: **Open in browser?**
- On every batch step (**Scan Templates**, **ModelCHECK**, **Thumbnails**, and other chunk-based tasks such as **JPEG 2D**), the PowerShell runner runs `ptcdbatch.bat -nographics -process`, polls for expected output files (inactivity timeout: **Settings → Timeout…**, default **120** seconds; the timer **starts when a new `xtop.exe` appears for that chunk** — any `xtop` still running from the prior chunk is ignored until it exits — and resets when a **new output file** appears or when **`xtop` restarts** between models), then runs **`kill.bat`** when each chunk (or the single scan job) finishes or times out (brief settle only when every expected file is already present and **`xtop.exe`** has exited), then removes that step’s `.dxc` so the wizard progress bar advances during the run. **ModelCHECK** and **Thumbnails** `.dxc` files include only models still missing output (the runner still **SKIP**s a chunk if every expected file is already present). **Thumbnails** jobs treat Creo’s native **`stem.jpg`** or the renamed **`stem.part.jpg`**, **`stem.assembly.jpg`**, or **`stem.drawing.jpg`** (legacy **`stem.model.jpg`** counts for skip checks) as already present. If **`xtop.exe`** never appears within **60 s** after launch, the chunk fails (**`XTOP NEVER STARTED:`** in red). If **`xtop.exe`** stays gone for the **Settings → Xtop gone timeout…** limit after it had started (default **20** s; a returning `xtop` logs **`XTOP RESTART:`** and resets the inactivity timer), the runner treats the chunk as failed (**`XTOP GONE:`** in red). **Next >** stays disabled (**Waiting…**) until every `.dxc` for that step is gone. While a batch step runs, a progress bar tracks remaining `.dxc` files. On **ModelCHECK** and **Thumbnails**, the progress line may show a rough ETA after enough chunks finish.
- After **Thumbnails**, the wizard moves to **Create Report** when ModelCHECK XML and the required thumbnail files (`*.part.jpg`, `*.assembly.jpg`, `*.drawing.jpg` as applicable) are present (also rechecked while a batch runs and when you return to the app).
- **`make_html_statistics.py`** — optional standalone preview of batch statistics: `python make_html_statistics.py` (uses **`working_directory`** from `app_settings.json`, writes **`statistics.html`**). The same rollup is embedded in **`index.html`** when you run **Create Report**. Batch rollup: models skipped, top-level assembly (with a full-width BOM table from that assembly’s `.a.xml` — model name, error count, warning count — when available), skeleton models, family tables, at a glance, model complexity (scan totals stay on the score dashboard). In **`index.html`**, BOM rows are clickable (same row-hover style as **At a glance**) and scroll to that model in the report.

## Requirements

- Windows
- A Creo loadpoint that contains `Parametric` (so `Parametric\bin\ptcdbatch.bat` exists) and the usual `Common Files\text\ttds` content
- In the same folder as the app you run (`main.exe` or `main.py`): `kill.bat`, `model_checks.xml`, and `report_template.html.j2` (for **Report**). **`kill.bat`** force-kills Creo batch processes (`xtop`, `dbatchs`, `dsq`, etc.) immediately. For **ModelCHECK** jobs, a `configs` folder with the modelcheck files you want referenced in the `.dxc` (`<ConfigFile>` entries). For **Scan Templates**, `configs\templates\` (separate from the full `configs\` set). For **JPEG 3D** and **JPEG 2D** jobs, `configs\config.pro` is included as a single `<Config>` entry in each chunk `.dxc`.
- **Working directory** path must **not contain spaces** (required for batch steps). **Create report** is not blocked by spaces.

## No Python needed

```powershell
.\main.exe
```

Launch options:

- In File Explorer: double-click `main.exe`.
- In PowerShell: run `.\main.exe` from the folder that contains the executable.

Usage:

- Follow the wizard: **Setup** → optional **Scan Templates** → **ModelCHECK** → **Thumbnails** → **Create Report**. Use **< Back** to revisit an earlier step (batch outputs on disk are not undone). Run a batch step again after a finished run if needed — the runner deletes `.dxc` file(s). Settings are saved to `app_settings.json` on successful batch launch and via **File → Save**.

## Menus

### File

- **New**, **Open…**, **Save**, **Save as…**, **Open Working Directory**, **Zip report…**, **Stop**, **Start over…**, **Exit** — working directory, loadpoint, chunk size, and timeout as JSON (`app_settings.json` or a file you choose; wizard step is not stored). **Open Working Directory** opens the current working folder in File Explorer (enabled on any wizard step when a working directory is set and exists on disk). **Zip report…** (enabled on **Setup** and **Create Report** only, when **`index.html`** exists and no batch or report job is running) writes **`{folder-name}-report.zip`** there with a **`report\`** folder containing the report files (`index.html`, detail pages, images, top-level `.prt`/`.asm`/`.drw` models, etc.), plus **`modchk\`** and **`templates\`** when those folders exist in the working directory, and an **`Open Report.bat`** launcher beside it that opens **`report\index.html`** in your browser. **Stop** (enabled while a batch step is **Waiting…**) asks for confirmation, runs `kill.bat`, and returns the wizard to a ready state on the current step — outputs already written are kept; run that step again to continue (the runner skips models whose outputs already exist). In normal mode, **Stop** also closes the PowerShell runner; in **Debug** mode the runner window stays open so you can read the log. **Start over…** asks for confirmation (Cancel is default), then removes prior scan and batch data from the working folder, **deletes the entire `templates\` folder** (including **`templates\creo-batch-template-scan.json`** and other scan-template files), **removes `modchk\`**, and removes batch runners and outputs (`.ps1`, `.dxc`, `.xml`, `.html`, `.jpg`, `.log`, `.crc`, `.txt`, `.out`, `.tmp`, and related sidecars), including all batch failure logs (`creo-batch-timeouts-*.txt`), while keeping Creo models (`.prt`, `.asm`, `.drw`) in the **working folder only**, and returns the wizard to **Setup**. **Stop** and **Exit** stay available during a batch (**Stop** only while **Waiting…**). Other **File** items, **Settings**, and **Configuration** are enabled only on the **Setup** step when no batch or report job is running (**Open Working Directory** and **Zip report…** are exceptions — see above). **Help** stays available. **Exit** stops the PowerShell batch runner if any, then closes the app (same as the window **×** button).

### Settings

Enabled on the **Setup** step only (see **File** above). Values are stored in `app_settings.json` (also written on successful batch launch and **File → Save**).

- **Chunk size…** — models per `creo-batch-N.dxc` chunk (**1–100**, default **10**). JSON key: `chunk_size`. Re-run the ModelCHECK wizard step after changing.
- **Timeout…** — seconds to wait for chunk output files with no new file appearing (**whole number ≥ 60**, default **120**). JSON key: `output_timeout_sec`. Re-run the batch wizard step after changing.
- **Xtop gone timeout…** — seconds to wait for `xtop.exe` to return after it exits mid-chunk (**XTOP GONE**); **whole number ≥ 5**, default **20**. JSON key: `xtop_timeout_sec`. Waiting for `xtop` to **start** after launch is fixed at **60 s** (**XTOP NEVER STARTED**). Re-run the batch wizard step after changing.
- **Automatic mode** (checkbox) — after **Scan Templates >** finishes, automatically advances to **ModelCHECK** and starts that batch; when the ModelCHECK batch run finishes, advances to **Thumbnails** (even if some models still lack XML), runs part thumbnails then assembly thumbnails and (when applicable) drawing thumbnails as separate batch runs, then **Create Report** when those batch run(s) finish — again even if some thumbnails failed. Manual **Next >** still requires all outputs on ModelCHECK and Thumbnails. The **Open in browser?** dialog still appears when the report is done so you can choose whether to open it. While Automatic mode is on, the batch PowerShell runner is **hidden** (no taskbar console); with it off, the runner opens **minimized** so you can restore it to read the log. ModelCHECK and **Thumbnails** steps show a blue **Automatic mode** note in the progress area. JSON key: `automatic_mode` (default **on**).
- **Debug** (checkbox, under Automatic mode) — when on, batch PowerShell runner windows are always shown (even in Automatic mode) and **never closed by the app** (after **Next >**, **Stop**, **Start over…**, **Exit**, or starting another batch — close them yourself). Each runner also writes a matching **`.log`** next to its **`.ps1`** (e.g. **`creo-batch-modelcheck.log`**, **`templates\creo-batch-scan-templates.log`**) with the same **`Write-ChLog`** lines shown in the console. Generated **`creo-batch-*.ps1`** runners are **not deleted** (on **GO**, **Create Report**, or **Next >** after Scan Templates). **Next >** after Scan Templates also keeps ModelCHECK detail files (`.html`, `.js`, `.png`, `.css`) in **`templates\`**. After a successful **Create Report**, **`master.xml`** is kept; when off (default), **`master.xml`** is removed from the working folder once **`index.html`** is written. JSON key: `debug_mode` (default **off**).

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
