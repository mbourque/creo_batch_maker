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
- Includes a `Kill` action that runs `kill.bat` to stop common distributed batch related processes.

## Requirements

- Windows
- Python 3.10+ (recommended)
- A Creo installation/loadpoint containing:
  - `Common Files\text\ttds\*.ttd`
  - `Parametric\bin\ptcdbatch.bat`

Python dependencies:

- `customtkinter`
- `Pillow`

## No Python Needed

```powershell
.\main.exe
```

The packaged executable is located at `dist\main.exe`.

Launch options:

- In File Explorer: double-click `main.exe`.
- In PowerShell (from project root): run `.\main.exe`.

Usage is the same as the Python version:

- Fill in the required folders and batch name.
- Click **GO** to generate the `.dxc`.
- Click **Open Batch** to launch Creo distributed batch.

### Distribution notes

- Move `dist\main.exe` to the project main folder before running it.
- `main.exe` must be in the same folder as `kill.bat` for the app to work correctly.
- If you move the EXE to another folder, copy `kill.bat` into that same folder.
- `app_settings.json` is created next to the EXE when **GO** succeeds.

## Install with Python

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

See the [documentation wiki page](https://github.com/mbourque/creo_batch_maker/wiki/Documentation) for how to use.

## Output details

- The app chunks model objects into groups of up to 10 objects per `<Group>`.
- Group name is derived from the selected task description.
- Generated XML structure:

```xml
<DXC>
    <Windchill/>
    <Group ...>
        <Object>...</Object>
        <ConfigFile>...</ConfigFile>
    </Group>
</DXC>
```
