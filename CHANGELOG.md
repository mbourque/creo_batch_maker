# Changelog

Short, user-facing notes for what changed in the PDSVISION Cad Assessment Tool. Newest entries at the top.

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

