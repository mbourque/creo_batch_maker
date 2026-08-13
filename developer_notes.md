# To compile into an exe:

`pyinstaller --clean main.spec` (or run `package_cad_assessment_tool.bat`, which rebuilds the exe first). `main.spec` bundles all app Python modules via `main.py` imports plus an explicit module list; sidecar files (`model_checks.xml`, `report_template.html.j2`, `kill.bat`, `configs\`) stay beside the exe, not inside it.

# To package for distribution (exe, sidecars, configs, sample models):

run `package_cad_assessment_tool.bat` in the project folder. It runs PyInstaller with `main.spec` (outputs `main.exe` in the project root), then creates `cad_assessment_tool.zip` (replaces any existing zip).

# To push bundled `configs\` into Creo ModelCHECK:

run `push_settings_to_creo.bat` (backs up the target config folder first).

# To delete old dbatch files from C:\ProgramData:

`cd C:\ProgramData`
`Get-ChildItem -Directory -Filter "dbatch*" | Remove-Item -Recurse -Force`

# To allow configs/start.mcs to check in

`git update-index --no-skip-worktree config/start.mcs`

`git add configs/start.mcs`

`git commit -m "Update start.mcs"`

then redo  

`git update-index --skip-worktree config/start.mcs`

# To allow configs/conditions.mcc to check in

`git update-index --no-skip-worktree config/condition.mcc`

`git add configs/condition.mcc`

`git commit -m "Update condition.mcc"`

then redo  

`git update-index --skip-worktree config/condition.mcc`

# To remove cached on roaming directory

Delete all files in  

`C:\Users\micha\AppData\Roaming\PTC\ProENGINEER\mdlchk`

# Add this to both TDD's on Creo install so they open master rep by default.

```
<SERVICE name="dbatchs">
	<SIMPREP enum="PRO_SIMPREP_MASTER_REP"/>
</SERVICE>
```

