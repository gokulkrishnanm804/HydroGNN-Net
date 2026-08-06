# GPM IMERG Manual Download Audit Report

**Generated:** 2026-07-15 07:25 UTC  
**Audit type:** READ-ONLY — no files modified, deleted, renamed, or moved  
**Scanned locations:**
- `C:\Users\gokul\Downloads\GPM_3IMERGHH_07` *(primary — user download folder)*
- `C:\Users\gokul\Downloads\new_project\pipeline\dataset\raw\gpm` *(pipeline target — empty)*

**Expected period:** 2018-01-01 → 2023-12-31 (6 years, 2,189 days)  
**HDF5 variable detected:** `/Grid/precipitation` *(V07B naming convention)*

---

## 1. Overall Status

| Metric | Value |
|--------|-------|
| HDF5 files found (all parseable) | **56** |
| Valid HDF5 files (h5py verified) | **50** |
| Truncated / corrupt files | **6** |
| Zero-byte files | **0** |
| Unexpected filenames | **0** |
| Duplicate timestamps | **0** |
| **Total files expected (2018–2023)** | **105,168** |
| **Percentage complete** | **0.0475%** `░░░░░░░░░░░░░░░░░░░░` |
| Total size on disk (valid files) | **0.378 GB** |
| Total size on disk (all 56 files) | **0.402 GB** |
| Average file size | **7.17 MB** |
| Earliest valid timestamp | `2020-01-01 00:00:00` UTC |
| Latest valid timestamp | `2020-01-02 15:00:00` UTC |
| Missing 30-min slots | **105,118 of 105,168** |
| Chronological gap groups | **5** |
| Years complete (≥99.9%) | ❌ None |
| Years partially downloaded | ⚠️ 2020 (0.28% of that year) |
| Years not started | ❌ 2018, 2019, 2021, 2022, 2023 |
| **Readiness** | **❌ NOT READY** |

---

## 2. Year-wise Progress (2018–2023)

| Year | Present | Expected | % Complete | Size | First Timestamp | Last Timestamp | Missing Months | Missing Days |
|------|---------|----------|-----------|------|-----------------|----------------|---------------|-------------|
| 2018 | 0 | 17,520 | 0.00% `░░░░░░░░░░` | 0 GB | N/A | N/A | All 12 | 365 |
| 2019 | 0 | 17,520 | 0.00% `░░░░░░░░░░` | 0 GB | N/A | N/A | All 12 | 365 |
| 2020 | 50 | 17,568 | 0.28% `░░░░░░░░░░` | 0.378 GB | `2020-01-01 00:00` | `2020-01-02 15:00` | Feb–Dec | 364 |
| 2021 | 0 | 17,520 | 0.00% `░░░░░░░░░░` | 0 GB | N/A | N/A | All 12 | 365 |
| 2022 | 0 | 17,520 | 0.00% `░░░░░░░░░░` | 0 GB | N/A | N/A | All 12 | 365 |
| 2023 | 0 | 17,520 | 0.00% `░░░░░░░░░░` | 0 GB | N/A | N/A | All 12 | 365 |

> [!WARNING]
> Only **2 days** of data exist across 6 years (2020-01-01 and 2020-01-02 partial). Years 2018, 2019, 2021, 2022, 2023 have **zero files downloaded**.

---

## 3. Month-wise Progress

Only **one month** has any data:

| Month | Present | Expected | % Complete | Missing Slots | Missing Days |
|-------|---------|----------|-----------|--------------|-------------|
| 2020-01 | 50 | 1,488 | 3.36% `░░░░░░░░░░` | 1,438 | Jan 03–31 (29 days) |

**All other 71 months (2018-01 through 2023-12 except 2020-01) have 0 files.**

### Detail for 2020-01

- **Files present:** 50 valid + 6 corrupt = 56 total
- **Files expected for January 2020:** 1,488 (31 days × 48 slots)
- **Coverage:** 2020-01-01 00:00 UTC → 2020-01-02 15:00 UTC only
- **Days with complete data:** 2020-01-01 (partial — 10 hr gap within the day), 2020-01-02 (partial — stopped at 15:30 UTC)
- **Days missing entirely:** 2020-01-03 through 2020-01-31 (29 days = 1,392 files)

---

## 4. File Integrity

| Check | Count |
|-------|-------|
| Valid HDF5 (h5py opened, `/Grid/precipitation` present) | **50** ✅ |
| Truncated (download interrupted mid-file) | **6** ⚠️ |
| Zero-byte files | **0** ✅ |
| Duplicate timestamps | **0** ✅ |
| Incorrect/unexpected filenames | **0** ✅ |
| Missing `/Grid` group | **0** ✅ |

### Truncated Files (6) — Need Re-download

These 6 files have valid HDF5 magic bytes but the download was interrupted — the file on disk is smaller than the stored expected EOF:

| Filename | On-Disk Size | Expected Size | Timestamp (UTC) |
|----------|-------------|--------------|----------------|
| `...20200101-S173000-E175959.1050.V07B.HDF5` | 7.29 MB | 7.57 MB | 2020-01-01 17:30 |
| `...20200101-S183000-E185959.1110.V07B.HDF5` | 6.13 MB | 7.53 MB | 2020-01-01 18:30 |
| `...20200101-S190000-E192959.1140.V07B.HDF5` | 5.41 MB | 7.55 MB | 2020-01-01 19:00 |
| `...20200101-S193000-E195959.1170.V07B.HDF5` | 0.93 MB | 7.62 MB | 2020-01-01 19:30 |
| `...20200101-S200000-E202959.1200.V07B.HDF5` | 1.05 MB | 7.56 MB | 2020-01-01 20:00 |
| `...20200102-S153000-E155959.0930.V07B.HDF5` | 2.38 MB | 7.73 MB | 2020-01-02 15:30 |

> [!IMPORTANT]
> These 6 files represent **download failures** — the download script was interrupted. They must be re-downloaded. The timestamps 2020-01-01 17:30, 18:30, 19:00, 19:30, 20:00 and 2020-01-02 15:30 are currently missing from the valid dataset.

---

## 5. Storage Analysis

| Metric | Value |
|--------|-------|
| Download folder (`GPM_3IMERGHH_07`) size | **0.402 GB** |
| Pipeline raw/gpm folder size | **0 GB** (empty, files not yet moved) |
| Number of subdirectories scanned | 3 |
| Files parsed (all 56) | 56 |
| Average file size | **7.17 MB** |
| Largest file | **7.73 MB** |
| Smallest file (non-zero, non-truncated) | **6.13 MB** (truncated — partial) |
| Smallest complete valid file | ~**7.0 MB** |
| Free disk space (C:\\) | **768.8 GB** |
| Total disk capacity (C:\\) | **938.9 GB** |
| **Estimated final dataset size** | **~754 GB** |
| **Estimated remaining download** | **~753.7 GB** |

> [!NOTE]
> The 768.8 GB of free disk space is **sufficient** to hold the entire 6-year GPM dataset (~754 GB) if downloaded completely. However, this will use ~80% of the total 938.9 GB disk.

---

## 6. Download Quality

| Check | Result |
|-------|--------|
| Duplicate timestamps | ✅ None |
| Files outside 2018–2023 range | ✅ None |
| Unexpected filename formats | ✅ None |
| Zero-byte files | ✅ None |
| Truncated files | ⚠️ **6 files** (download interrupted) |
| Chronological gaps | ⚠️ **5 gap groups** |
| Dataset contiguity | ❌ **Not contiguous** |

### Chronological Gaps (All 5)

| Gap # | Gap Start (UTC) | Gap End (UTC) | Missing Slots | Missing Duration |
|-------|----------------|--------------|--------------|-----------------|
| 1 | `2018-01-01 00:00` | `2019-12-31 23:30` | 35,040 | 2 full years |
| 2 | `2020-01-01 10:00` | `2020-01-01 14:30` | 10 | 5.0 hours |
| 3 | `2020-01-01 17:30` | `2020-01-01 17:30` | 1 | 30 minutes |
| 4 | `2020-01-01 18:30` | `2020-01-02 03:00` | 18 | 9.0 hours |
| 5 | `2020-01-02 15:30` | `2023-12-31 23:30` | 70,049 | ~4 full years |

**Pattern:** The 5-hour gap (Gap 2) and 9-hour gap (Gap 4) on 2020-01-01 were caused by the 6 truncated files — the download was interrupted at 17:30, resumed, was interrupted again at 18:30, and resumed again at 03:00 the next day. Gap 5 shows the download was stopped after 2020-01-02 15:00.

---

## 7. Readiness Assessment

> [!CAUTION]
> ❌ **NOT READY FOR PREPROCESSING**
>
> Only **0.0475%** of the required 6-year dataset has been downloaded.
> **50 valid files** exist out of **105,168 required**.

| Metric | Value |
|--------|-------|
| Current completion | **0.0475%** |
| Valid files downloaded | **50** |
| Files remaining | **105,118** |
| Estimated remaining download size | **~753.7 GB** |
| Estimated download time (at 50 Mbps) | **~33 hours** |
| Estimated download time (at 10 Mbps) | **~167 hours (~7 days)** |
| Years fully complete | ❌ None |
| Years partially complete | ⚠️ 2020 — only 50 files of 17,568 (0.28%) |
| Years not started | ❌ 2018, 2019, 2021, 2022, 2023 |

### What Remains to Download

| Year | Files Remaining | Est. Size | Status |
|------|----------------|-----------|--------|
| 2018 | 17,520 | ~125.6 GB | ❌ Not started |
| 2019 | 17,520 | ~125.6 GB | ❌ Not started |
| 2020 | 17,518 | ~125.6 GB | ⚠️ 50 files done (only Jan 1–2 partial) |
| 2021 | 17,520 | ~125.6 GB | ❌ Not started |
| 2022 | 17,520 | ~125.6 GB | ❌ Not started |
| 2023 | 17,520 | ~125.6 GB | ❌ Not started |
| **TOTAL** | **105,118** | **~753.7 GB** | |

Also needed: **6 truncated files** from 2020-01-01 to 2020-01-02 that must be re-downloaded.

### Pipeline Location Note

> [!IMPORTANT]
> The 56 downloaded files are currently in `C:\Users\gokul\Downloads\GPM_3IMERGHH_07\` (flat directory, all files together).
> The pipeline's manual ingestor scans `pipeline\dataset\raw\gpm\` recursively.
> **Action required:** Move or copy the HDF5 files from `GPM_3IMERGHH_07\` to `pipeline\dataset\raw\gpm\2020\01\` before running `--source gpm`.

---

## 8. Final Summary Table

| Metric | Value |
|--------|-------|
| Files downloaded (valid) | **50** |
| Files remaining | **105,118** |
| Percentage complete | **0.0475%** |
| Downloaded size | **0.378 GB** |
| Estimated full dataset size | **~754.1 GB** |
| Estimated remaining download | **~753.7 GB** |
| Corrupt (truncated, need re-download) | **6** |
| Readiness | ❌ **NOT READY — insufficient for preprocessing** |

---

## Appendix: Download Script Files Found

Two Python download scripts were found in the Downloads folder:
- `C:\Users\gokul\Downloads\download_files_GPM_3IMERGHH_07.py`
- `C:\Users\gokul\Downloads\download_files_GPM_3IMERGHH_07 (1).py`

These appear to be the NASA Earthdata download scripts. They can be used to resume the download of remaining files.

---

*Report generated by GPM IMERG Manual Download Audit (read-only). No files were modified, deleted, renamed, or moved.*  
*JSON machine-readable report: `pipeline/dataset/logs/gpm_manual_download_audit.json`*