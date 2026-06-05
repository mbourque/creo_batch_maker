# Creo Distributed Batch Maker

Windows desktop utility for building Creo distributed batch (`.dxc`) files from models in a folder and running them through `Parametric\bin\ptcdbatch.bat` via a generated PowerShell runner.

## What this app does

- GUI for working directory, Creo loadpoint, and task (paths are set with Browse… only).
- Reads task labels from `modelcheck.ttd`, `solid-raster_write_jpg.ttd`, and `plot_jpeg_a-size.ttd` under your loadpoint’s `Common Files\text\ttds` (not every `.ttd` on disk).
- GO clears any prior `creo-batch-*.dxc` / `creo-batch-run.ps1` in the working folder, then writes chunk `.dxc` files (models per chunk: **Settings → Chunk size…**, default 10, non-recursive scan) plus `creo-batch-run.ps1`. **ModelCHECK** includes `.prt`, `.asm`, and `.drw`; **JPEG 3D** includes `.prt` and `.asm` only; **JPEG 2D Export to file, A Paper Size** includes `.drw` only.
- Open Batch opens that script in PowerShell; the script runs `ptcdbatch.bat -nographics -process` per chunk, polls for expected output files (inactivity timeout: **Settings → Timeout…**, default **120** seconds), runs `kill.bat`, then deletes the chunk `.dxc` files when finished. At the end it logs **Count of Files Success** and **Count of Files Timed Out** (per expected output file, including skips where outputs already existed).
- **Build** scans the working directory for ModelCHECK result XML (`*.p.xml`, `*.a.xml`, `*.d.xml`) and merges them into **`master.xml`** in that folder (run after batch output exists). **Model Units for Length** on parts/assemblies comes from the Creo **`UNITS_LENGTH`** check in each `*.p.xml` / `*.a.xml` (not drawings).
- **Report** runs in the background (button shows **Report…** while working). It copies `<creo_loadpoint>/Common Files/modchk` to `<working_directory>/modchk` and patches ModelCHECK `*.html` in the working folder (except **`index.html`**) so offline links work, then reads `master.xml` plus bundled **`model_checks.xml`** and **`report_template.html.j2`**, and writes **`index.html`** — a Model Quality Report with a **score dashboard** (visible issues; updates when you remove items), a left sidebar of checks that had **errors or warnings** (A–Z by check name; **Filter view** dropdown (show all, warnings, errors, flagged, or unflagged)), and per-model detail (thumbnails, messages, links). Removing sections or models in the browser updates the adjusted score and category grades (Model Quality, Model Integrity, etc.) for what is still shown. Large folders can take a few minutes; the window stays responsive. Optionally opens the report in your browser when done. Same patch logic is available as `python patch.py` for development.

## Requirements

- Windows
- A Creo loadpoint that contains `Parametric` (so `Parametric\bin\ptcdbatch.bat` exists) and the usual `Common Files\text\ttds` content
- In the same folder as the app you run (`main.exe` or `main.py`): `kill.bat`, `model_checks.xml`, and `report_template.html.j2` (for **Report**). For ModelCHECK jobs, a `configs` folder with the modelcheck files you want referenced in the `.dxc` (`<ConfigFile>` entries). For **JPEG 3D** and **JPEG 2D** jobs, `configs\config.pro` is included as a single `<Config>` entry in each chunk `.dxc`.
- **Working directory** path must **not contain spaces** (required for **GO** / **Open Batch**). **Build** and **Report** are not blocked by spaces.

## No Python needed

```powershell
.\main.exe
```

Launch options:

- In File Explorer: double-click `main.exe`.
- In PowerShell: run `.\main.exe` from the folder that contains the executable.

Usage:

- Use Browse… to set the working directory (models live there; outputs go there), Creo loadpoint, and task.
- GO generates the chunk `.dxc` files and `creo-batch-run.ps1` (and updates `app_settings.json` when all GO checks pass).
- Open Batch starts the runner in PowerShell when `creo-batch-run.ps1` and at least one `creo-batch-*.dxc` are in the working folder (run GO again after a finished run, because the runner deletes the chunk `.dxc` files).

## Menus

### File

- **New**, **Open…**, **Save**, **Save as…**, **Exit** — working-directory / loadpoint / task settings as JSON (`app_settings.json` or a file you choose).

### Settings

Always visible. Values are stored in `app_settings.json` (also written on successful **GO** and **File → Save**).

- **Chunk size…** — models per `creo-batch-N.dxc` chunk (**1–10**, default **10**). JSON key: `chunk_size`. Run **GO** again after changing.
- **Timeout…** — seconds to wait for chunk output files with no new file appearing (**whole number ≥ 60**, default **120**). JSON key: `output_timeout_sec`. Run **GO** again after changing.

### Configuration

Shown only when the selected task is **ModelCHECK** (hidden for JPEG/raster tasks). This menu used to be named **Settings**; it was renamed to **Configuration** so **Settings** could hold app-wide options (chunk size, timeout, etc.).

Opens bundled ModelCHECK files from the app’s `configs\` folder in Notepad:

- Model Checks…, Config.pro…, Angles…, GMC…, Modelcheck Config…, Defaults…, Designers…, Holes…, Inch Settings…, Metric Settings…, Sheetmetal Thickness…
- **Open configurations…** — opens the `configs\` folder in File Explorer (formerly **Open settings…**).

### Help

- **Documentation…**, **Check for updates…**, **About…** (creator info)

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
