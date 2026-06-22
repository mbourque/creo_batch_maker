# Changelog

Short, user-facing notes for what changed in the PDSVISION Cad Assessment Tool. Newest entries at the top.

## 2026-06-17 — v1.10.1
- **ModelCHECK**: fixed UI freeze after **Skip** on Scan Templates (or when refreshing the ModelCHECK step) on folders with many files.

## 2026-06-17 — v1.10

- **ModelCHECK** batch runner waits for both ModelCHECK XML and HTML (`*.p.html`, `*.a.html`, `*.d.html`) before settling and running `**kill.bat`** (fixes missing **More details…** links when HTML was still being written). 

## 2026-06-17 — v1.9

- **Scan Templates**: `templates\` and `creo-batch-template-scan.json` are created only when you run **Scan Templates >** and finish the step — not on **Skip** or **Browse…** alone.

## 2026-06-17 — v1.8

- **ModelCHECK** batch jobs no longer embed `configs\templates\` config files (those are for **Scan Templates** only).

## 2026-06-17 — v1.7

- **Thumbnails**: part and assembly progress now say “Part thumbnails running…” / “Assembly thumbnails running…” (with chunk count when batching), same style as drawing thumbnails.

## 2026-06-17 — v1.6

- **Thumbnails** / **Create Report**: failed count now includes part, assembly, and drawing failures together (no longer drops earlier phases when the next pass starts).

## 2026-06-17 — v1.5

- Added **CHANGELOG.md** in the app folder — a short list of user-facing changes, newest first, with date and version.

