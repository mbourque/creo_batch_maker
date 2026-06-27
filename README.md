# PDSVISION Cad Assessment Tool

Windows app that runs Creo ModelCHECK, thumbnails, and a quality report on models in a folder.

## Quick start
**Download all files** - put in a new directory without spaces in the path like `c:\dev\creo_batch`
**No Python needed** — double-click `main.exe`, or from PowerShell:

```powershell
.\main.exe
```

**With Python** (3.10+):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python .\main.py
```

## Before you begin

- **Windows** with a Creo loadpoint (`Parametric\bin\ptcdbatch.bat` must exist).
- Choose a **working directory** with your `.prt`, `.asm`, and/or `.drw` files at the top level (not in subfolders).
- The working directory path must **not contain spaces** for batch steps.

Settings are saved in `app_settings.json` when you start a batch or use **File → Save**.

## The wizard

Work through the steps at the top of the window:

| Step | What it does |
|------|----------------|
| **Setup** | Pick working folder and Creo loadpoint. |
| **Scan Templates** | Optional — scan template models for parameters and layers. |
| **ModelCHECK** | Run ModelCHECK on your models. |
| **Thumbnails** | Create part, assembly, and drawing JPEG previews. |
| **Create Report** | Build `index.html` in the working folder. |

### Buttons you’ll use

- **Next >** — move forward. On batch steps, shows **Next >** only when every model has the required output; otherwise it shows **Run ModelCHECK >** or **Thumbnails >**.
- **Skip** — skip an optional step (Scan Templates, ModelCHECK, or Thumbnails) and continue.
- **< Back** — return to a previous step (disabled while **Waiting…**).
- **Waiting…** — a batch is running; wait until it finishes.

The stepper at the top shows which steps are done (✓) or skipped (—).

## Each step (short)

### Setup

Browse for your **working directory** and **Creo loadpoint**, then click **Next >**.

If `index.html` already exists, **Open Report** opens it in your browser.

### Scan Templates (optional)

Upload part / assembly / drawing templates if you use them, then **Scan Templates >**.

- **Skip** if you don’t need templates.
- If the scan fails, fix the issue and run **Scan Templates >** again. Automatic mode pauses until you continue.

### ModelCHECK

Click **Run ModelCHECK >** to batch your models. The app only processes models that still need output.

- Progress shows how many chunks are done.
- If models fail, a red **Failed (N)** line opens the timeout log in Notepad.
- **Next >** when every model has ModelCHECK XML and HTML.
- **Skip** to move on without running ModelCHECK.

### Thumbnails

Click **Thumbnails >**. The app runs part, assembly, and drawing passes when those model types exist. Each pass uses its own chunk files; progress bars reflect **this session’s** passes (not leftover files from an earlier run). When a pass finishes, its bar shows **100%** before the next pass starts.

Same ideas as ModelCHECK: **Waiting…**, **Failed (N)**, **Next >** when complete, or **Skip**.

### Create Report

Click **Create Report**. When finished, choose whether to open `index.html` in your browser.

If the report already exists, **Open Report** opens it without rebuilding.

## Settings (Setup step only)

Open **Settings** from the menu:

| Option | Purpose |
|--------|---------|
| **Batch settings…** | Models per chunk (default 10), output wait timeout, xtop timeout. |
| **Automatic mode** | Runs each step in sequence when the previous batch finishes. On **Thumbnails**, runs part, then assembly, then drawing (when those types exist) before moving on — even if some models failed. Manual **Next >** still requires all outputs. |
| **Debug** | Show batch console windows and keep log files (for troubleshooting). |

## File menu (common actions)

| Action | When to use |
|--------|-------------|
| **Open Working Directory** | Open the current folder in File Explorer. |
| **Stop** | Stop the running batch (keeps outputs already written). Pauses automatic mode until you continue. |
| **Start over…** | Clear batch outputs in the working folder and return to Setup. Keeps your Creo models. |
| **Zip report…** | Package `index.html` and related files into a zip (when a report exists). |
| **Save / Open…** | Save or load `app_settings.json`. |

**Configuration** opens ModelCHECK config files in Notepad (`configs\` folder).

## Tips

- After **Stop**, run the same step again — models that already have output are skipped.
- Large folders are split into chunks (see **Batch settings**). One full run may take a while.
- For more detail and troubleshooting, see the [documentation wiki](https://github.com/mbourque/creo_batch_maker/wiki/Documentation).
