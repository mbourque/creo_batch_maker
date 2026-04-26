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

## GUI workflow

1. **Working Directory**  
   Folder where the output `.dxc` file is written.

2. **Creo Loadpoint**  
   Root Creo install/loadpoint. The app uses this to:
   - discover tasks from `Common Files\text\ttds`,
   - locate `Parametric\bin\ptcdbatch.bat`.

3. **Task**  
   Select a discovered `.ttd` task.  
   The dropdown label uses the task description parsed from the `.ttd` file.

4. **Modelcheck Config Folder**  
   Required only when the selected task is `modelcheck.ttd`.  
   All files in this folder are added as `<ConfigFile>` entries.

5. **Creo Models Folder**  
   Source folder scanned for model files:
   - `*.prt` / `*.prt.<n>`
   - `*.asm` / `*.asm.<n>`
   - `*.drw` / `*.drw.<n>`

   For each base filename, only the latest version is included in the batch.

6. **Distributed Batch File**  
   Base output name. `.dxc` is automatically enforced.

7. **Buttons**
   - **GO**: creates the `.dxc` file.
   - **Open Batch**: opens a new PowerShell console and runs `ptcdbatch.bat <your-file>.dxc`.
   - **Kill**: executes `kill.bat` to force-close common batch processes.

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

## Settings persistence

On successful **GO**, app settings are saved to `app_settings.json` in the project directory, including the selected task filename.

## Process kill script

`kill.bat` attempts to stop these processes:

- `pro_comm_msg.exe`
- `nmsd.exe`
- `dbatchs.exe`
- `dsq.exe`
- `xtop.exe`

Use with care, since it force-terminates (`taskkill /F`) those processes.
