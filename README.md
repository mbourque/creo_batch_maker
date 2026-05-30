# Creo Distributed Batch Maker

Windows desktop utility for building Creo distributed batch (`.dxc`) files from models in a folder and running them through `Parametric\bin\ptcdbatch.bat` via a generated PowerShell runner.

## What this app does

- GUI for working directory, Creo loadpoint, and task (paths are set with Browse… only).
- Reads task labels from `modelcheck.ttd` and `solid-raster_write_jpg.ttd` under your loadpoint’s `Common Files\text\ttds` (not every `.ttd` on disk).
- GO clears any prior `creo-batch-*.dxc` / `creo-batch-run.ps1` in the working folder, then writes chunk `.dxc` files (models per chunk: **Settings → Chunk size…**, default 10, non-recursive scan) plus `creo-batch-run.ps1`.
- Open Batch opens that script in PowerShell; the script runs `ptcdbatch.bat -nographics -process` per chunk, polls for expected output files (inactivity timeout: **Settings → Timeout…**, default **120** seconds), runs `kill.bat`, then deletes the chunk `.dxc` files when finished.
- **Build** merges per-model check XML into `master.xml`; **Report** writes an HTML model quality report (sidebar lists failing checks A–Z by check name).

## Requirements

- Windows
- A Creo loadpoint that contains `Parametric` (so `Parametric\bin\ptcdbatch.bat` exists) and the usual `Common Files\text\ttds` content
- In the same folder as the app you run (`main.exe` or `main.py`): `kill.bat`, `model_checks.xml`, and `report_template.html.j2` (for **Report**). For ModelCHECK jobs, a `configs` folder with the modelcheck files you want referenced in the `.dxc`.

## No Python needed

```powershell
.\main.exe
```

The packaged build is `main.exe` in the project folder (`pyinstaller main.spec`). Copy `main.exe` together with the sidecar files above (and `configs\` if you use ModelCHECK) into the folder you run from.

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
- **Timeout…** — seconds to wait for chunk output files with no new file appearing (**whole number ≥ 1**, default **120**). JSON key: `output_timeout_sec`. Run **GO** again after changing.

### Configuration

Shown only when the selected task is **ModelCHECK** (hidden for JPEG/raster tasks). This menu used to be named **Settings**; it was renamed to **Configuration** so **Settings** could hold app-wide options (chunk size, timeout, etc.).

Opens bundled ModelCHECK files from the app’s `configs\` folder in Notepad:

- Model Checks…, Config.pro…, Angles…, GMC…, Modelcheck Config…, Defaults…, Designers…, Holes…, Inch Settings…, Metric Settings…, Sheetmetal Thickness…
- **Open configurations…** — opens the `configs\` folder in File Explorer (formerly **Open settings…**).

### Help

- **Documentation…**, **About…**

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
