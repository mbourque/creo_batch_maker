# Creo Distributed Batch Maker

Windows desktop utility for creating Creo distributed batch (`.dxc`) files and launching `ptcdbatch.bat` with the generated input.

## What this app does

- Provides a GUI to collect paths and batch settings.
- Reads Creo task definitions (`.ttd`) from your Creo loadpoint.
- Builds a `.dxc` file containing:
  - one or more `<Group>` blocks,
  - model objects (`.prt`, `.asm`, `.drw`, including versioned files),
  - optional modelcheck config files.
- Launches Creo's `ptcdbatch.bat` for the generated `.dxc`.

## Requirements

- Windows
- Python 3.10+ (recommended)
- A Creo installation/loadpoint containing:
  - `Common Files\text\ttds\*.ttd`
  - `Parametric\bin\ptcdbatch.bat`

## No Python Needed

```powershell
.\main.exe
```

Launch options:

- In File Explorer: double-click `main.exe`.
- In PowerShell (from project root): run `.\main.exe`.

Usage is the same as the Python version:

- Fill in the required folders and batch name.
- Click **GO** to generate the `.dxc`.
- Click **Open Batch** to launch Creo distributed batch.

## Install with Python

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Python dependencies:

- `customtkinter`
- `Pillow`
  
## Run

```powershell
python .\main.py
```

## Documentation

See the [documentation wiki page](https://github.com/mbourque/creo_batch_maker/wiki/Documentation) for how to use.
