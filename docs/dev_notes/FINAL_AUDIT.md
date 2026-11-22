# Final end-to-end audit

Audit date: 2026-11-21. This is the current local completion record. `CHANGE_IMPACT.md` traces each approved audit change across model, algorithms, implementation, configuration, tests, experiments, metrics, outputs, analysis, discussion, limitations, README, implementation plan, and compiled PDF. `AUDIT/REPORT_CLAIMS.md` maps every report result object to its source and generation/validation path.

## Verified local deliverables

| Area | Observed verification |
|---|---|
| Automated tests | `python -m unittest discover -s tests -v` — 32 tests ran; all passed. This includes a regression test requiring the proposal-results table caption to match its actual columns. |
| Original seven-family results | `python report/validate_results.py results/full_20261121` — passed; 1,760 policy episodes, 440 matched scenario groups, 20 seeds, seven families, 1,232 summary rows, 100 deviation cases, 15 run-level plots, 17 source hashes. The report plot generator was also rerun to completion and wrote 70 report plots. |
| Independent weight sensitivity | `python tools/validate_weight_sensitivity.py results/improvements_20261121/weight_sensitivity` — passed; 720 raw cases, 180 matched level/seed groups, 720 paired policy cases, 9 intervals, 24 plots, 18 source hashes, and 719 original plus 1 separately marked recovered log entry. The report plot generator returned 24 plots. |
| Model and instructor corrections | Final equations and definitions are recorded in `MODEL_DESIGN.md`; B3 is labelled a heuristic, the B3-relative gap is signed and empirical, the bid/team-payoff coefficients agree, and home-demand and coverage-loss terms are disjoint. No theoretical nonnegative PoD claim remains in current source/report prose. See `AUDIT/MATHEMATICAL_REVIEW.md`. |
| Report claims | Generated tables/macros and plotted summaries are sourced from the submitted CSVs. Signed comparison arithmetic, paired seed counts, source hashes, and plot counts are checked by the validators. Detailed claim-to-artifact map: `AUDIT/REPORT_CLAIMS.md`. |
| Report PDF | Tectonic compiled `report/main.tex`; `pdfinfo report/main.pdf` reported **8 pages**, A4 (595.28 × 841.89 pt), PDF 1.5. Current PDF rendered to eight page images; the current contact sheet and pages were visually inspected. The references occupy page 8. |
| Contribution section | The report lists all three original names and proposal assignments. It says deliverables are present and personal completion/authorship is unverified; no unsupported personal completion claim is made. |
| Genuine screenshot | `results/full_20261121/screenshots/final_communication_plot_capture.jpg` is a desktop capture of the actual regenerated communication missed-dispatch plot opened in Photos. It was visually inspected and is readable. Provenance and the retained older mismatched screenshot are documented in `AUDIT/SCREENSHOT_REPLACEMENT.md`. |
| README paths and commands | README includes overview, model, policies, communication/learning, repository structure, setup, tests, experiment reproduction, result locations, report/plot links, screenshot, audit artifacts, and the no-remote status. Local paths are checked in the final verification command below. |
| Original proposal preservation | Current proposal SHA-256 is `8CECF4051109FE21F1E4EC3AE764C1AB86C27D84A4D26100061878EED3404EF2`, matching its captured baseline hash. It was not modified. |
| Primary raw data preservation | Current `results/full_20261121/raw_results.csv` SHA-256 is `8ABE1F28C744B491227FE5CE89552AEFB773232E32B816A3B9A8E264F1E2AE2E`, matching its captured baseline hash. |
| Security / file hygiene | Repository scan found no password/API-key/private-key pattern matches and no file larger than 20 MB. No ignored build/cache/pilot artifacts were deleted. The source feedback image includes the instructor's name, institutional email, and staff identifier; member names/IDs appear in the required contribution evidence. These are disclosed in `FINAL_ISSUES.md` for review before any later public release. |
| Git / publication | Branch is `academic-quality-audit`; no remote is configured and nothing was pushed. No audit commit was made before showing the proposed contents/status/exclusions, as requested. |

The report uses the included, MIT-licensed community `arxiv.sty` manuscript style. It is not described as an official arXiv house class; arXiv's official guidance concerns source processing and reviewing the resulting PDF. Details are disclosed in `FINAL_ISSUES.md` and the README.

## Repository-wide consistency search

The final search covered active Markdown, TeX, Python, configuration, generated table/macro, and result documentation for the old `beta'` notation, a nonnegative empirical PoD claim, an assertion that B3 is the centralized optimum, the stale response-time table caption, obsolete screenshot references, and unfinished final-audit markers. No active formulation/report/source contradiction remained after correcting the caption and adding its regression test. Historical material is clearly scoped: the original proposal is preserved unchanged; `AUDIT/BASELINE_AUDIT.md` is dated as a baseline and now has a resolution ledger; the initial unmatched sensitivity attempt is retained with an explicit “do not use for inference” note. The missing original sensitivity log event is separately marked as provenance repair and does not contribute to metrics.

## Reproduction and verification commands

From the repository root:

```powershell
python -m unittest discover -s tests -v
python report/validate_results.py results/full_20261121
python tools/validate_weight_sensitivity.py results/improvements_20261121/weight_sensitivity
python report/plot_results.py results/full_20261121
python report/plot_results.py results/improvements_20261121/weight_sensitivity
python report/build_report_assets.py results/full_20261121 --weight-sensitivity-dir results/improvements_20261121/weight_sensitivity
```

To rebuild the PDF from the report directory: `tectonic --keep-logs main.tex`. Full reruns use the exact commands in README; they write to fresh output directories and can take several minutes. Final report/README-only changes did not change simulation code, experiment configuration, or the frozen raw outcome CSVs; final checks validated those existing outcomes rather than rerunning the entire experiment suite.

## Repository contents proposed for review

The working tree is uncommitted. With untracked files expanded, Git reports 174 file paths: 83 modified, 90 untracked, and one deleted (the old screenshot, preserved byte-for-byte under `AUDIT/`). They cover root model/plan/README and ignore rules; `CHANGE_IMPACT.md`; `AUDIT/` baseline and final claim/provenance records; configs; report source, generated LaTeX, style/license, and compiled PDF; the original full results with regenerated plots and current screenshot; the corrected independent sensitivity run and preserved initial unmatched attempt; regression test files; and sensitivity/log-recovery/validation tools. Raw source-run episode CSVs are preserved; generated result files needed to verify/reproduce the report are included. The exact status is still visible via `git status --short --untracked-files=all`.

`git clean -ndX` (dry run only) listed these currently excluded temporary/cache artifacts: `report/__pycache__/`, `report/main.aux`, `report/main.bbl`, `report/main.blg`, `report/main.log`, `report/main.out`, `report/rendered_pages/`, `results/pilot_communication/`, package/test/tool `__pycache__/` directories, and `tmp/`. These are LaTeX intermediates, rendered audit pages, caches, or an exploratory pilot; submitted CSVs, plots, source, configs, screenshots, manifests, and the final PDF are not ignored. Nothing in this exclusion list was deleted.

## Remaining items

See `FINAL_ISSUES.md` for the mandatory public repository link pending user authorization, individual contribution confirmation, original-run metadata limits, sensitivity log recovery, clean-clone verification, statistical scope, and local commit pending review. These open items are not represented as completed.
