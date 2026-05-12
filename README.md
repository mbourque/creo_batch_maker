# Creo Distributed Batch Maker

Windows desktop utility for building Creo distributed batch (`.dxc`) files from models in a folder and running them through **`Parametric\bin\ptcdbatch.bat`** via a generated PowerShell runner.

## What this app does

- GUI for **working directory**, **Creo loadpoint**, and **task** (paths are set with **Browse…** only).
- Reads task labels from **`modelcheck.ttd`** and **`solid-raster_write_jpg.ttd`** under your loadpoint’s **`Common Files\text\ttds`** (not every `.ttd` on disk).
- **GO** clears any prior **`creo-batch-*.dxc`** / **`creo-batch-run.ps1`** in the working folder, then writes **chunk `.dxc` files** (up to 10 models each, non-recursive scan) plus **`creo-batch-run.ps1`**.
- **Open Batch** opens that script in **PowerShell**; the script runs **`ptcdbatch.bat -nographics -process`** per chunk, waits on **`xtop.exe`**, runs **`kill.bat`**, then deletes the chunk **`.dxc`** files when finished.

## Requirements

- **Windows**
- A **Creo loadpoint** that contains **`Parametric`** (so **`Parametric\bin\ptcdbatch.bat`** exists) and the usual **`Common Files\text\ttds`** content
- In the **same folder as the app you run** (**`main.exe`** or **`main.py`**): **`kill.bat`** (needed for **GO** and for the PowerShell runner after each chunk). For **ModelCHECK** jobs, a **`configs`** folder there with the modelcheck files you want referenced in the `.dxc`.

## No Python needed

```powershell
.\main.exe
```

The packaged build is typically **`dist\main.exe`**. Copy **`main.exe`** together with **`kill.bat`** (and **`configs`** if you use **ModelCHECK**) into the folder you run from; see **Requirements** above.

Launch options:

- In File Explorer: double-click **`main.exe`**.
- In PowerShell: run **`.\main.exe`** from the folder that contains the executable.

Usage:

- Use **Browse…** to set the working directory (models live there; outputs go there), Creo loadpoint, and task.
- **GO** generates the chunk **`.dxc`** files and **`creo-batch-run.ps1`** (and updates **`app_settings.json`** when all **GO** checks pass).
- **Open Batch** starts the runner in PowerShell so you can follow the log output.

## Install with Python

**Python 3.10+** recommended. Create a virtual environment and install packages from **`requirements.txt`**:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
python .\main.py
```

## Documentation

See the [documentation wiki page](https://github.com/mbourque/creo_batch_maker/wiki/Documentation) for full usage, safety notes, and troubleshooting.
