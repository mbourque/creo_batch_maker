# Changelog

Short, user-facing notes for what changed in the PDSVISION Cad Assessment Tool. Newest entries at the top.

## 2026-07-22 — v1.12.4

- **Report**: sidebar auto-collapses on narrow windows to a thin hover strip; hover peeks it as an overlay (no toggle icon on wide screens).

## 2026-07-19 — v1.12.3

- **Report**: model thumbnail and name links show a “Drag this into Creo” hover tip again.

## 2026-07-19 — v1.12.2

- **Model Type Breakdown**: renamed row to Parts with freeform features.

## 2026-07-19 — v1.12.1

- **Model Type Breakdown**: added Parts with Freeform Features using positive FREEFORM information results.

## 2026-07-19 — v1.12.0

- New version

## 2026-07-19 — v1.11.185

- **Scan Information**: Multibody parts counts parts with more than one body (INFO included; single-body no longer counted).

## 2026-07-19 — v1.11.184

- **Scan Information**: Bulk parts counts INFO results (not only errors/warnings).

## 2026-07-19 — v1.11.183

- **Scan Information**: Number of flexible components counts INFO results (not only errors/warnings).

## 2026-07-19 — v1.11.182

- **Scan Information**: Number of mechanism components counts INFO results (not only errors/warnings).

## 2026-07-19 — v1.11.181

- **Filter view**: Sort by issue count is hidden when fewer than two warning/error checks remain.

## 2026-07-19 — v1.11.180

- **Remove this / Remove all like this**: opens the next check again instead of leaving a blank page.

## 2026-07-19 — v1.11.179

- **Sidebar navigation**: Score, Scan Information, Template Information, and checks all use the same scroll-to-top behavior.

## 2026-07-19 — v1.11.178

- **Sidebar checks**: clicking a check no longer bounces the page up and down.

## 2026-07-19 — v1.11.177

- **Filter view**: category and model filters drop from the list when only information checks remain for that group.

## 2026-07-19 — v1.11.176

- **Sidebar checks**: first click after open loads the check (no longer needs a second click while the report finishes starting).

## 2026-07-19 — v1.11.175

- **Remove this**: deleted checks are removed from the sidebar, and empty filter options are dropped from the Filter view list.

## 2026-07-19 — v1.11.174

- **Filter view**: when a filter has no checks left, it resets to Show all and drops the empty option again (no “No checks match” message).

## 2026-07-19 — v1.11.173

- **Remove this**: after removing an open check, the next check opens (same as filtered views); Score only if none remain.

## 2026-07-19 — v1.11.172

- **Remove this**: after removing an open check, the report returns to Score instead of an empty card.

## 2026-07-19 — v1.11.171

- **Show all**: Score, Scan Information, and Template Information respond on the first sidebar click after open.

## 2026-07-19 — v1.11.170

- **Show all**: Score, Scan Information, and Template Information each open alone from the sidebar (not all three at once).

## 2026-07-19 — v1.11.169

- **Show all**: Score, Scan Information, and Template Information stay in the sidebar while a check is open.

## 2026-07-19 — v1.11.168

- **Sidebar checks**: clicking a check loads only that check’s cards (including in Show all); Print This temporarily shows every warning and error.

## 2026-07-19 — v1.11.167

- **Filtered reports**: loads one selected check at a time and hides the summary cards; Show all still loads every warning and error for scrolling and printing.

## 2026-07-19 — v1.11.166

- **Show information**: hides Score, Scan Information, and Template Information so the selected check stays at the top; sidebar clicks scroll to it.

## 2026-07-19 — v1.11.165

- **Show information**: loads one information check at a time (faster on large reports); pick another from the sidebar to switch.

## 2026-07-18 — v1.11.164

- **Scan duration**: now adds ModelCHECK and thumbnail pass times (idle time between steps is not counted).

## 2026-07-18 — v1.11.163

- **File size information**: raw byte counts are now shown in MB or GB in report information rows.

## 2026-07-18 — v1.11.162

- **Report details**: item detail previews show five entries again; issue rows no longer show file size, feature count, overall size, or length units.

## 2026-07-18 — v1.11.161

- **Report layout**: reverted the metadata clear change that broke model row layout.

## 2026-07-18 — v1.11.160

- **Report layout**: Created by / size / features lines no longer wrap under the thumbnail when detail lists are present.

## 2026-07-18 — v1.11.159

- **Report details**: item detail previews now show three entries before the ellipsis to keep model rows compact.

## 2026-07-18 — v1.11.158

- **Report details**: item detail bullets now line up with the message text above them.

## 2026-07-18 — v1.11.157

- **Report details**: item detail lists are shown as bullets.

## 2026-07-18 — v1.11.156

- **Report details**: item detail lists use the same text color as the message line above them.

## 2026-07-18 — v1.11.155

- **Report details**: item detail lists under each issue use a smaller compact font.

## 2026-07-18 — v1.11.154

- **Report details**: visible information rows also list up to five available ModelCHECK item details.

## 2026-07-18 — v1.11.153

- **Report details**: warning and error rows now list up to five available ModelCHECK item details, with an ellipsis when more exist.

## 2026-07-18 — v1.11.152

- **Report**: identical ModelCHECK results emitted twice for the same model (for example Missing Layers) are counted once.

## 2026-07-18 — v1.11.151

- **Template Information tags**: tags no longer select on a single click; double-click still selects one tag the normal browser way.

## 2026-07-18 — v1.11.150

- **Template Information tags**: double-clicking a parameter or similar tag now selects that tag only, not the whole row.

## 2026-07-18 — v1.11.149

- **Drawing template notes**: each note shows its location as a plain label with only the note value as a rounded tag.

## 2026-07-18 — v1.11.148

- **Drawing template notes**: the XML `<ans>` is used only as the note count; related `info#` values stay grouped by `<item>`.

## 2026-07-18 — v1.11.147

- **Drawing template notes**: Template Information now shows every `info#` value, including the note location/ID and note text.

## 2026-07-18 — v1.11.146

- **Template Information**: section headings now show only **Part template**, **Assembly template**, or **Drawing template**, without the fixed model filename.

## 2026-07-18 — v1.11.145

- **Drawing checks**: removed feature count, overall model size, and length units because those fields are not applicable to drawings.

## 2026-07-17 — v1.11.144

- **Scan Templates**: no longer writes `templates\creo-batch-template-scan.json` (unused after Template Information / summary cleanup).

## 2026-07-17 — v1.11.143

- **CAD Assessment Summary**: removed the **Templates scanned** line (Template Information already covers that).

## 2026-07-17 — v1.11.142

- **Template Information**: part and assembly templates now show **Mass units** (with **Length units**), from the same XML sources used for `start.mcs`.

## 2026-07-17 — v1.11.141

- **Scan Templates**: restored mass-units update — `UNITS_MASS` in `config\templates\checks.mch`, plus `PTC_UNITS_MASS` fallback (kg → KILOGRAM) when the check is missing from XML.

## 2026-07-17 — v1.11.140

- **Scan Templates**: removed the temporary `PTC_UNITS_MASS` fallback; mass units again come only from an `UNITS_MASS` check in the template XML.

## 2026-07-17 — v1.11.139

- **Scan Templates**: `PRT_UNITS_MASS` / `ASM_UNITS_MASS` now fill when the XML has no `UNITS_MASS` check, using `PTC_UNITS_MASS` from parameters (e.g. kg → KILOGRAM).

## 2026-07-17 — v1.11.138

- **Scan Templates**: writes `PRT_UNITS_MASS` / `ASM_UNITS_MASS` in `config\start.mcs` from template XML `UNITS_MASS` (e.g. KILOGRAM).

## 2026-07-17 — v1.11.137

- **Scan Templates**: writes `PRT_UNITS_LENGTH` / `ASM_UNITS_LENGTH` in `config\start.mcs` from the same template XML Length units check used in Template Information.

## 2026-07-17 — v1.11.136

- **Scan Templates**: updates `PRT_DATUM` / `PRT_VIEW` and `ASM_DATUM` / `ASM_VIEW` in `config\start.mcs` from the template XML (plus drawing lines under the correct anchors).

## 2026-07-17 — v1.11.135

- **Scan Templates**: `config\start.mcs` section markers and drawing anchors fixed so template scan can update part, assembly, and drawing blocks correctly.

## 2026-07-17 — v1.11.134

- **Scan Templates**: `PRT_TEMPLATE` / `ASM_TEMPLATE` / `DRW_TEMPLATE` in `config\start.mcs` are enabled only when that template file is set; otherwise commented.

## 2026-07-17 — v1.11.133

- **Scan Templates**: choosing a Drawing DTL enables `STD_DRW_DTL_FILE DEFAULT detail.dtl` in `config\start.mcs`; clearing it comments that line again.

## 2026-07-17 — v1.11.132

- **Scan Templates**: when a drawing template is shown, browse a **Drawing DTL** (`.dtl`) to save as `config\detail.dtl`.

## 2026-07-17 — v1.11.131

- **Template Information**: each value is shown as its own rounded tag (e.g. Plane: FRONT, RIGHT, TOP), not one background behind the whole line.

## 2026-07-17 — v1.11.130

- **Template Information**: value lines use a light rounded background (same tone as table row hover) so they are easier to scan.

## 2026-07-17 — v1.11.129

- **Configuration**: removed **Designers…** from the menu.

## 2026-07-17 — v1.11.128

- **Configuration → Model Checks…**: opens the active `.mch` from **Settings → Checks…** / `config\condition.mcc` (not `config\templates\`).

## 2026-07-17 — v1.11.127

- **CAD Assessment Summary**: **Models scanned** is in Scan Summary (above total size); **Duplicate models** is last under Dataset Overview.

## 2026-07-17 — v1.11.126

- **CAD Assessment Summary**: Scan Summary order is **Working directory**, **Total size of scanned models**, **Model checks**, then **Scan duration** last.

## 2026-07-17 — v1.11.125

- **CAD Assessment Summary**: **Model checks** now appears under **Working directory** in the Scan Summary group.

## 2026-07-17 — v1.11.124

- **Models failed**: no longer lists Scan Templates models from `templates\\` (only the working-folder top level is checked).

## 2026-07-17 — v1.11.123

- **CAD Assessment Summary**: **Number of unique models** is now **Number of unique components** under **Assembly Structure**.

## 2026-07-17 — v1.11.122

- **CAD Assessment Summary**: **Model checks** reads `config\condition.mcc` beside `main.exe` in the packaged app (was missing in the EXE build).

## 2026-07-17 — v1.11.121

- **Scan Information**: **Statistics** is now **CAD Assessment Summary**, with grouped rows for scan summary, dataset overview, model types, assembly health, metadata, and notable findings.

## 2026-07-17 — v1.11.120

- **Create Report**: **Processing, please wait…** appears immediately; building `master.xml` runs in the background (no long freeze before the overlay).

## 2026-07-17 — v1.11.119

- **Statistics → Scan duration**: finds earliest/latest ModelCHECK XML times in one folder pass (skips non-XML names without stating them).

## 2026-07-17 — v1.11.118

- **Create Report**: shows a **Processing, please wait…** dialog with an animated bar while the report builds, then closes when finished.

## 2026-07-17 — v1.11.117

- **Statistics**: row order is **Working directory**, **Models scanned**, **Scan duration**, **Total size of scanned models**, then **Last saved by**.

## 2026-07-17 — v1.11.116

- **Statistics**: **Working directory** and **Scan duration** rows after **Model checks** (duration from first to last ModelCHECK XML in that folder).

## 2026-07-16 — v1.11.115

- **Large working folders**: status/pending scans now look up only relevant types (`.prt`/`.asm`/`.drw` and expected XML/HTML/JPG outputs) instead of listing every file when the folder also has prior-scan clutter.

## 2026-07-16 — v1.11.114

- **Skip / step change**: ModelCHECK and Thumbnails status (“N of M models…”) scans in the background so Skip no longer freezes the UI on large working folders.

## 2026-07-16 — v1.11.113

- **ModelCHECK / Thumbnails**: while a batch is Waiting…, the UI no longer rescans the whole working folder every progress tick (Stop/Pause and Skip stay responsive on large jobs).

## 2026-07-15 — v1.11.112

- **Statistics**: **Model checks** row after **Scan date** shows the `.mch` file from `config\condition.mcc`.

## 2026-07-15 — v1.11.111

- **Settings → Checks…**: choose a `.mch` from `config\` and update every checks-file name in `config\condition.mcc`.

## 2026-07-13 — v1.11.110

- **README**: how to point interactive Creo at this app’s ModelCHECK config (`modelcheck_dir` / `modelcheck_enabled`).

## 2026-07-13 — v1.11.109

- **Config folder**: app paths and menus now use `config\` (was `configs\`). Rename the folder on disk to match (e.g. `git mv configs config`).

## 2026-07-12 — v1.11.108

- **Statistics**: total features for the top-level assembly is now that assembly’s component count (`NUM_COMPONENTS`, e.g. 9480), not a sum of every part’s internal features.

## 2026-07-12 — v1.11.107

- **Statistics**: total features for the top-level assembly now counts each BOM occurrence (repeated parts/assemblies add their features every time), using `ASM_BOM`.

## 2026-07-12 — v1.11.106

- **Statistics**: total features for a single top-level product now sums resumed features from every part and assembly in the scan (not only models listed under `UNQ_COMPONENTS`).

## 2026-07-12 — v1.11.105

- **Statistics**: total features for the top-level assembly now sums resumed features across every unique part and sub-assembly in that product (not only the assembly file itself).

## 2026-07-12 — v1.11.104

- **Statistics**: last row shows total features in the top-level assembly (label includes the assembly name).

## 2026-07-08 — v1.11.103

- **Scan Templates + Debug mode**: **Next >** appears when the template scan finishes (XML present / run-complete flag), without closing the PowerShell runner window left open by **-NoExit**.

## 2026-07-08 — v1.11.102

- **Create Report**: `master.xml` is built only from ModelCHECK XML in the working folder itself (not subfolders such as `templates\\`).

## 2026-07-08 — v1.11.101

- **Create Report**: `master.xml` no longer includes ModelCHECK XML from `templates\\`, so Scan Templates models (e.g. drawing template) do not inflate Statistics or the model list.

## 2026-07-08 — v1.11.100

- **Thumbnails**: after a restart, each progress bar shows **100% finished** when that pass already ran and only known failures remain (including drawings that never produced a thumbnail). **Thumbnails >** then shows the failed-models dialog and retries those.

## 2026-07-08 — v1.11.99

- **Thumbnails → Failed (N)**: counts every model still missing a thumbnail across part, assembly, and drawing (not only the latest timeout log). Click **here** opens a combined review list. Models that finish a pass without output are added to that pass’s failure log so part failures stay visible after drawings run.

## 2026-07-08 — v1.11.98

- **Thumbnails**: when a pass finishes (chunks at 100%), the next pass is assembly or drawing — leftover part failures no longer restart the part pass or show the failed-models retry dialog before drawings run.

## 2026-07-08 — v1.11.97

- **Thumbnails**: each progress bar (part / assembly / drawing) is driven only by that pass’s files on disk — assembly and drawing show **100%** when their models are done, independent of part failures; a part re-run no longer clears later passes.

## 2026-07-08 — v1.11.96

- **Thumbnails**: assembly and drawing progress bars show **100%** when that pass is already complete on disk, even if the part pass still has failures; starting a part re-run no longer resets later passes that are already done.

## 2026-07-08 — v1.11.95

- **Thumbnails / Create Report**: **Thumbnail files found** when any in-scope model already has a thumbnail (same idea as ModelCHECK XML), not only when every model is done; progress bars show per-pass completion (e.g. 717 of 720) instead of 0% when outputs exist on disk.

## 2026-07-08 — v1.11.94

- **Thumbnails**: progress bars show 100% when thumbnail outputs already exist on disk (same as ModelCHECK after a prior run); **Create Report** thumbnail status uses the same per-model check.

## 2026-07-08 — v1.11.93

- **Create Report**: thumbnail status again checks only renamed `*.part.jpg` / `*.assembly.jpg` / `*.drawing.jpg` files; drawing thumbnails are required only when the JPEG 2D plot task is available from your Creo loadpoint.

## 2026-07-08 — v1.11.92

- **Create Report**: thumbnail status now detects plain `.jpg` and legacy `.model.jpg` outputs (same rules as the Thumbnails batch step), not only renamed `*.part.jpg` / `*.assembly.jpg` / `*.drawing.jpg` files.

## 2026-07-08 — v1.11.91

- **Report → Statistics**: table rows highlight on hover (same style as **Biggest problems**).

## 2026-07-08 — v1.11.90

- **Batch settings**: OK/Cancel buttons now use the same dialog styling as other modals (white text instead of gray).

## 2026-07-08 — v1.11.89

- **Scan settings**: OK/Cancel buttons now use consistent dialog styling (white text instead of gray).

## 2026-07-07 — v1.11.88

- **Scan Templates**: template rows for model types turned off in **Scan settings** are hidden; existing templates for those types are cleared when settings change.

## 2026-07-07 — v1.11.87

- **Report → Models failed**: renamed from **Models skipped** (same list of models that did not complete scanning).

## 2026-07-07 — v1.11.86

- **Report → Models skipped**: model types turned off in **Scan settings** are no longer listed as skipped.

## 2026-07-07 — v1.11.85

- **Thumbnails** (drawing-only scan settings): the wizard step now finds `.drw` files and enables **Thumbnails >** instead of reporting no models.

## 2026-07-07 — v1.11.84

- **Settings → Scan settings…**: choose which model types to include when scanning the working folder (parts, assemblies, and/or drawings). Unchecked types are skipped in batch runs.

## 2026-07-07 — v1.11.83

- **Start over…**: batch status cleanup removes `.pvz` files (not `.pvx`).

## 2026-07-07 — v1.11.82

- **Start over…**: also removes batch status files (`*-run.complete`, pause/stop flags, and `.pvz`).

## 2026-07-07 — v1.11.81

- **Configuration → View scales…**: opens `configs\view_scale.txt` in Notepad.

## 2026-07-07 — v1.11.80

- **Report → Statistics**: **Total size of scanned models** is listed directly under **Models scanned**.

## 2026-07-07 — v1.11.79

- **Report → Statistics**: **Non solid parts** row (under **Bulk parts**) counts parts whose `BODY_INFO` bodies all have **No Geometry**.

## 2026-07-07 — v1.11.78

- **Report**: information sections have no **Flag** or **Remove** buttons (they do not work with the issue filters).

## 2026-07-06 — v1.11.77

- **Report → Statistics**: label **Sheet metal parts** (was **Sheetmetal parts**).

## 2026-07-06 — v1.11.75

- **File → Purge cache…**: opens a visible PowerShell window (stays open) so you can see what was removed or skipped.

## 2026-07-06 — v1.11.72

- **Report**: checks marked `<info_check>Y</info_check>` in `model_checks.xml` with `INFO` results appear as **Information** sections; **Filter view > Show information** (excluded from score and issue counts).

## 2026-07-06 — v1.11.59

- **Report**: **Filter view** is hidden when there are no warnings or errors left.

## 2026-07-06 — v1.11.58

- **Report**: **Filter view** hides **Show warnings** or **Show errors** when that severity has no issues.

## 2026-07-05 — v1.11.57

- **Packaging**: PyInstaller spec updated for `update_start_from_xml` (Scan Templates → `start.mcs` in the built exe).

## 2026-07-05 — v1.11.56

- **Configuration → Start…** opens `configs\start.mcs` in Notepad (replaces **Defaults…**).

## 2026-07-05 — v1.11.55

- **Maintenance**: renamed `update_sample_start_from_xml.py` to `update_start_from_xml.py` (same behavior; updates `start.mcs`).

## 2026-07-05 — v1.11.54

- **Settings → Model Checks…** opens `configs\templates\checks.mch` (was `default_checks.mch`).

## 2026-07-05 — v1.11.53

- **Scan Templates**: template XML is merged into `configs\start.mcs` (renamed from `sample_start.mcs`).

## 2026-07-05 — v1.11.52

- Dialogs (warnings, pause, settings, About, and similar) open centered on the main window instead of the screen corner.

## 2026-07-05 — v1.11.51

- **File → Pause**: **Resume** warns if Creo (**xtop**) is still running and keeps the pause dialog open until you quit Creo.

## 2026-07-04 — v1.11.50

- **File → Pause**: first dialog asks you to wait for the current chunk; a second dialog appears when it is safe to use interactive Creo (**Resume** / **Stop**).

## 2026-07-04 — v1.11.49

- **File → Pause**: dialog updates when the batch is actually held (green **safe to use interactive Creo**), not only when Pause is clicked.

## 2026-07-04 — v1.11.48

- **File → Pause**: pause Scan Templates, ModelCHECK, or Thumbnails after the current chunk (writes `creo-batch-pause.requested`); dialog offers **Resume** or **Stop**. Blocks automatic mode until you resume or stop.

## 2026-07-04 — v1.11.47

- **Report → Statistics**: **Files scanned** renamed to **Models scanned**.

## 2026-07-04 — v1.11.46

- **Report**: **Files scanned** moved from **Score** to **Statistics**, under **Last saved by**.

## 2026-07-04 — v1.11.45

- **Report → Statistics**: **Total size of scanned models** sums each model’s `FILE_SIZE` (bytes) and shows MB or GB.

## 2026-07-04 — v1.11.44

- **GO**: if Creo (**xtop**) is already running, a warning asks you to quit Creo and the batch does not start.

## 2026-07-03 — v1.11.43

- **Report → Statistics**: **Users** renamed to **Last saved by**.

## 2026-07-03 — v1.11.41

- **Report → Statistics**: **Users** list is right-aligned like the other statistic values.

## 2026-07-03 — v1.11.40

- **Report → Statistics**: **Users** list is plain text (normal weight, wraps at spaces).

## 2026-07-03 — v1.11.39

- **Report → Statistics**: **Users** list wraps across lines and uses normal (not bold) weight.

## 2026-07-03 — v1.11.38

- **Report → Statistics**: **Users** also parses truncated `LastSaved` values such as `JERRY.L.TAYLOR -` (no text after the dash).

## 2026-07-03 — v1.11.37

- **Report → Statistics**: **Users** lists unique usernames from each model’s `LastSaved` field (text before `-`, e.g. `MBOURQUE`).

## 2026-07-03 — v1.11.36

- **Report → Statistics**: first row is **Scan date** (e.g. Thursday July 3, 2026 8:15am), from when `master.xml` was written.

## 2026-07-03 — v1.11.35

- **Report → Statistics**: **Sheetmetal parts**, **Multibody parts**, **Skeleton parts**, and **Bulk parts** moved directly under **Drawings**.

## 2026-07-03 — v1.11.34

- **Report → Score**: **Visible issues** label renamed to **Total issues**.

## 2026-07-03 — v1.11.33

- **Report**: **Parts**, **Assemblies**, and **Drawings** counts moved from **Score** to the top of the **Scan Information → Statistics** list.

## 2026-07-03 — v1.11.32

- **Report**: **Parts**, **Assemblies**, and **Drawings** counts moved from **Score** to the top of **Scan Information**.

## 2026-07-03 — v1.11.31

- **File → Recent scans**: shown on the **Setup** wizard step only (hidden on Templates, ModelCHECK, Thumbnails, and Report).

## 2026-07-03 — v1.11.30

- **Report > Template Information**: part and assembly **Start relations** heading drops the count; relations render in one block with line breaks (no extra gap between lines).

## 2026-07-03 — v1.11.28

- **Report > Template Information**: drawing adds sheet sizes, symbols, sheet count, and notes; part adds length units, designated attributes, and accuracy; assembly adds designated attributes (from template scan XML).

## 2026-07-03 — v1.11.19

- **Scan Templates**: each template (part, assembly, drawing) runs in its own batch chunk — one model at a time — instead of all templates in a single run.

## 2026-07-03 — v1.11.18

- **Scan Templates**: after a failed template scan, **Back** and **Scan Templates >** work again so you can change templates or retry (manual and automatic mode).

## 2026-07-03 — v1.11.17

- **Report**: **Template Information** (sidebar, under Scan Information) lists part, assembly, and drawing template scan details from `templates\*.xml` when a template scan was run; omitted when no template XML exists.

## 2026-07-02 — v1.11.16

- **File → Recent scans**: numbered entries (`1.`, `2.`, …) with a shortened path (`C:/PTC/XMA3/.../folder`) so similar folders are easier to tell apart.
- **File → Recent scans**: browsing to a working directory on Setup adds that folder to the list (same as starting a batch).

## 2026-07-02 — v1.11.14

- **Settings** (`app_settings.json`): `recent_scans` is always written (below `working_directory`) so you can add test paths manually; older settings files are upgraded on startup.

## 2026-07-02 — v1.11.13

- **File → Recent scans**: lists up to 10 recently batched working folders (folder name in the menu, full path in `app_settings.json`). Pick one to restore that working directory. Hidden when the list is empty.

## 2026-07-02 — v1.11.12

- **Report** (Scan Information → **Models skipped**): **More…** expands the full list; **Collapse** returns to the short preview (same as Family table detail).

## 2026-07-02 — v1.11.11

- **Report** (Scan Information → **Models skipped**): drag a model name into Creo to open it (click does nothing).

## 2026-07-02 — v1.11.10

- **Report** (Scan Information → Statistics): added a **Bulk parts** row that totals `BULK_ITEMS` values found in report-visible checks.
- **Report** (Scan Information → Statistics): renamed **Number of skeleton models** to **Skeleton models**.

## 2026-06-30 — v1.11.9

- **Thumbnails** / **ModelCHECK**: batch progress bars update smoothly while the runner is active (one chunk-file check per tick instead of rescanning the whole folder); the UI stays responsive on large folders. **Failed (N)** may lag during an active batch and refreshes when the pass finishes.
- **Report** (Statistics): family generic/instance counts in the progress table match the Family table detail (same scanned-file filter). Performance table row labels use sentence case. **Models skipped** uses the same subsection heading size as other Scan Information blocks.
- **Report** (**Duplicate Models**): lists each duplicate found under the count (`Preview the model : MODEL.PRT`); model names link to that model elsewhere in the report when it appears as an issue row.

## 2026-06-28 — v1.11.8

- **ModelCHECK** / **Thumbnails**: when a failure log still applies, **Automatic mode** reuses your last retry choice from this session (e.g. **one model per batch** picked on ModelCHECK also applies when thumbnails auto-start with failures). Manual **GO** still shows the retry dialog each time. The batch runner log records chunk size at start (fixed bad quoting in generated `.ps1` that could print a harmless PowerShell error on runner start).

## 2026-06-27 — v1.11.7

- **ModelCHECK** / **Thumbnails** / **Automatic mode**: wizard progress bars track each batch pass correctly (separate chunk `.dxc` names per pass), refresh while the runner is active, reach **100%** when the runner finishes and all chunk files are gone (`*-run.complete` supports **Debug mode**), hold briefly before auto-advance, and no longer skip ahead of the bar.
- **Thumbnails**: three progress rows (part → assembly → drawing) reflect the active pass — no **waiting to start** while that pass is running, including fast single-chunk runs and automatic chaining.
- **Batch runner**: better handling when **xtop** restarts quickly between chunks (avoids false **XTOP GONE** / timer issues).
- **Report**: **Model Complexity** rows are clickable like **Biggest problems** (plain text, row hover, jump to model); **Open in browser?** after **Create Report** stays modal on top (no flash behind the main window).

## 2026-06-26 — v1.11.6

- **Stop**: cooperative stop, `kill.bat`, and cleanup; confirmation stays on top (**Proceed** default); auto-advance pauses until you continue.
- **Automatic mode** / **ModelCHECK** / **Thumbnails**: advance after a batch finishes (even with failures) without re-running the same step; thumbnails chain part → assembly → drawing before **Create Report**; fixed auto loops, per-pass progress bars, and batch-runner **xtop** / **kill.bat** timing between chunks.
- **ModelCHECK** / **Thumbnails**: retry dialog when a failure log exists (batch all still missing, retry failed at normal chunk size, or one model per batch); **Stop** clears failure logs.

## 2026-06-24 — v1.11.0

- **Automatic mode**: replaced the multi-step internal chain with a simple timer that calls the same **Next >** / **GO** handler as manual mode when each batch step is ready, so Scan Templates advances to ModelCHECK reliably after the scan completes.
- **Create Report**: fixed **Open in browser?** appearing repeatedly in Automatic mode after a successful build (the auto timer no longer re-triggers **Create Report**; use **Create Report** manually anytime to rebuild, even when `index.html` already exists).
- **Automatic mode**: **< Back** pauses auto-advance until you click **Next >**, **Skip**, or a step action (**Scan Templates >**, **Run ModelCHECK >**, etc.) yourself.
- **Thumbnails** / **Automatic mode**: fixed advancing to **Create Report** before all thumbnail passes finished (part → assembly → drawing) and before `*.part.jpg` / `*.assembly.jpg` / `*.drawing.jpg` rename — drawing thumbnails were often skipped and JPEGs stayed as plain `*.jpg`. Automatic mode now uses the same **Waiting…** / **Next >** rules as the footer and does not advance until each step is fully finished.

## 2026-06-23 — v1.10.3

- **Scan Templates**: `**configs\sample_start.mcs`** is updated as soon as the scan batch finishes (not only when you run ModelCHECK **GO**).
- **Scan Templates**: fixed **Browse...** buttons being clipped when multiple template rows are visible.

## 2026-06-23 — v1.10.2

- **Settings → Batch settings…**: dialog stays open (modal, no instant OK from a stray Enter when opened from the menu).

## 2026-06-22 — v1.10.1

- **ModelCHECK**: fixed UI freeze after **Skip** on Scan Templates (or when refreshing the ModelCHECK step) on folders with many files.

## 2026-06-22 — v1.10

- **ModelCHECK** batch runner waits for both ModelCHECK XML and HTML (`*.p.html`, `*.a.html`, `*.d.html`) before settling and running `**kill.bat`** (fixes missing **More details…** links when HTML was still being written).

## 2026-06-22 — v1.9

- **Scan Templates**: `templates\` and `creo-batch-template-scan.json` are created only when you run **Scan Templates >** and finish the step — not on **Skip** or **Browse…** alone.

## 2026-06-22 — v1.8

- **ModelCHECK** batch jobs no longer embed `configs\templates\` config files (those are for **Scan Templates** only).

## 2026-06-22 — v1.7

- **Thumbnails**: part and assembly progress now say “Part thumbnails running…” / “Assembly thumbnails running…” (with chunk count when batching), same style as drawing thumbnails.

## 2026-06-22 — v1.6

- **Thumbnails** / **Create Report**: failed count now includes part, assembly, and drawing failures together (no longer drops earlier phases when the next pass starts).

## 2026-06-22 — v1.5

- Added **CHANGELOG.md** in the app folder — a short list of user-facing changes, newest first, with date and version.

## 2026-06-21 — v1.4.15

- **Scan Templates / Thumbnails**: improved scan logic and image thumbnail creation reliability.

## 2026-06-18 — v1.4.14

- **Scan Templates**: added separate inch and millimeter template configuration files.
- **Scanning**: improved failed-model detection, added rescan options for all/not-failed/failed items, and improved Creo kill handling.

## 2026-06-16 — v1.4.13

- **Thumbnails**: 2D JPEG runs now create thumbnails too.
- **Reports**: added report/statistics tweaks and updated relation handling.
- **Configurations**: cleaned up unused configs, added `rel_update.txt`, and adjusted `xtop` kill timing.

## 2026-06-15 — v1.4.12

- **Thumbnails**: renamed the old 3D JPEG step to **Thumbnail**.
- **Run cleanup**: fixed skip cleanup behavior and corrected ModelCHECK `.mch` / `sample_start.mcs` files.
- **Reports**: added **Zip Report**, debug mode, and fixes for automatic mode.

## 2026-06-14 — v1.4.11

- **Reports**: added warning/error icons and a top-level assembly statistics section.
- **Scanning**: fixed scan timing bugs, added a stop action, and hid menus while a scan is running.

## 2026-06-13 — v1.4.10

- **UX**: replaced the earlier flow with a wizard-style UI, progress indicator, and hidden batch runner window.
- **Automation**: added automatic processing mode.
- **Scanning**: added elapsed-time progress, failed-model reporting, and cleanup of old `.txt` logs on start over.
- **Reports**: updated the template so images can be dragged.

## 2026-06-12 — v1.4.9

- **Workflow**: simplified the app around a single main action, improved run logic, and added a **Create Report** task.

## 2026-06-11 — v1.4.8

- **Templates**: added support for reading values from template configs.
- **UI / Configs**: fixed task dropdown font display and updated default/sample config files.

## 2026-06-10 — v1.4.7

- **Checks**: refined check categories and MBD readiness checks.
- **Reports**: added at-a-glance statistic links and updated ModelCHECK configuration files.
- **Maintenance**: added `update_sample_start_from_xml.py` and cleaned up `.gitignore`.

## 2026-06-09 — v1.4.6

- **Scoring**: fixed the scoring mechanism and changed MBD checks to errors.
- **Reports**: added an MBD readiness card/category and help links explaining checks.
- **Save flow**: added a browser refresh warning when unsaved changes are present.

## 2026-06-08 — v1.4.5

- **Reports**: added model-type and category filters.
- **Statistics**: added a statistics page and optimized heavy report page loads.
- **Templates**: added template upload and template config files.

## 2026-06-05 — v1.4.4

- **Reports**: added save support, sorting, score adjustment by removing checks, and general stability improvements.

## 2026-06-03 — v1.4.3

- **Family tables**: fixed generic model names/images for family table instances.
- **UI**: fixed an app hang that could happen when using menus.

## 2026-06-02 — v1.4.2

- **Family tables**: improved handling so family table instances show the proper generic model name and image.

## 2026-06-01 — v1.4.1

- **Batch tasks**: preserved JPEG tasks on loadpoint refresh, added a 2D JPEG plot task, tightened per-task model scans, and improved dialogs/logging.
- **Local reports**: added patching so **More info** HTML pages load locally.
- **Configs**: updated `config.pro` and JPEG task configuration.

## 2026-05-31 — v1.4

- **JPEG export**: added 2D JPEG export TDD and removed drawings from the 3D JPEG TDD.
- **Settings / UI**: added About menu, centered dialogs, changed button order, and set the minimum timeout to 60 seconds.
- **Batch runner**: improved batch handling messages.

## 2026-05-30 — v1.3.3

- **Settings**: added Timeout UI.
- **Batch runner**: added an end-of-run summary and killed an extra Creo-related process.
- **Reports**: sorted report output alphabetically and adjusted timestamps.
- **Packaging**: fixed the executable so it loads template and XML files correctly.

## 2026-05-29 — v1.3.2

- **ModelCHECK**: updated model checks and configs with clearer descriptions.

## 2026-05-26 — v1.3.1

- **Batch runner**: made batch-run creation more fault tolerant and hid `kill.bat` output.

## 2026-05-17 — v1.3

- **Settings**: added `config_init.mc`.

## 2026-05-14 — v1.2.2

- **Reports**: fixed missing-image placeholders and improved summary report output.
- **Save flow**: improved persistence and renamed generated report output to `index.html` with a button to open it.

## 2026-05-13 — v1.2.1

- **Reports / Settings**: fixed report generation and added extra settings/config files.

## 2026-05-12 — v1.2

- **Reports**: added report creation, XML merge support, and report template updates.
- **Validation**: added field validation in the UI.
- **Docs**: merged and cleaned up README updates.

## 2026-05-11 — v1.1

- **Core runner**: rewrote parser logic, changed the app to spawn batch runs, and added settings.
- **Repository cleanup**: stopped tracking generated build output and per-user settings.

## 2026-05-09 — v1.0.3

- **Docs**: updated README documentation.

## 2026-05-05 — v1.0.2

- **ModelCHECK configs**: added a `configs` folder containing batch-mode ModelCHECK settings and reference files.
- **Docs**: updated README documentation.

## 2026-04-26 — v1.0.1

- **Packaging / Docs**: added the executable and initial README.

## 2026-04-09 — v1.0

- **Initial release**: added the first version of the main application script.

