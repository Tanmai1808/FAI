# Baseline Audit

Recorded on 2026-11-21 before project edits. This is the preserved state from which the audit branch proceeds.

## Repository state

- Baseline commit: `03584f95df848f49f6d3c5cf17d9b8ce2cada929` (`Prepare ambulance dispatch project submission`).
- Baseline branch: `master`; working tree clean (`git status --porcelain` empty).
- No Git remote was configured. The commit is local and was not published.
- The audit work proceeds on the new local branch `academic-quality-audit`; the baseline commit was not rewritten.

## Baseline verification

| Check | Observed result |
|---|---|
| Tests | `python -m unittest discover -s tests -v`; Python 3.10.0; 27 tests passed, 0 failed. |
| Full-result validator | `python report/validate_results.py` run on a temporary copy of `results/full_20261121`; passed. It verified 1,760 policy episodes, 440 matched groups, 20 seeds, all seven experiment families, 1,232 summary rows, 100 deviation cases, 15 plots, 17 source hashes, and the proposal hash. The committed result directory was not modified by this check. |
| Report PDF | `pdfinfo report/main.pdf`: exactly 8 pages, A4, PDF 1.5. Baseline SHA-256: `2610667607A52E10769329F812CB38D2FC423A449D30F647D3576DFD359DDE4F`. |
| Original proposal | Six pages. Preserved file SHA-256: `8CECF4051109FE21F1E4EC3AE764C1AB86C27D84A4D26100061878EED3404EF2`. The proposal was not modified. |
| Existing result run | `manifest.json` reports 20 seeds (1000–1019), 1,760 episodes, and 584.463 seconds summed episode runtime. This is recorded runtime, not a wall-clock benchmark. |

The PDF contact sheet was visually inspected. The document is legible, but forced page breaks leave pages 4–6 unusually sparse and the four-panel figure and two full-sweep tables occupy separate pages. This is a layout defect to address while retaining exactly eight A4 pages.

## Baseline file hashes

Hashes below are SHA-256 and were captured before edits. The experiment manifest also records hashes for all 17 simulator source files; those values are listed separately in the source table.

### Model, configuration, report, and validation inputs

| Path | SHA-256 |
|---|---|
| `MODEL_DESIGN.md` | `D8987CDAFA7786DF7C5694DFF8E1D87A35E700E37A784D5FF734D4D9132DD72F` |
| `IMPLEMENTATION_PLAN.md` | `B56225C686EFEC9D70F0F39FEFE7AB703C8C3A1CD419B26FA030AA74210EB2EA` |
| `README.md` | `70FA117211ABC1DA250F3F82032732ABB504C2DFB546729C384026E66A3D5460` |
| `configs/default.json` | `7AF976E180EE1D49DFD813A83D72CBA781320DD13D9023F58AE800B7FE9DC1AC` |
| `configs/experiment_matrix.json` | `FBB4199870772056DF3EE78ED41F4BAA971E6F42BC9276B991B41C3940ED9A58` |
| `report/main.tex` | `40B7B93905E9973A17BC62AA2018CBF2D2326A0F7F47D7ECC48D26829DA12F64` |
| `report/references.bib` | `329FFD7A7A27C7C6865BC85A1ABC3B943FF83644FF1FCBC7497EA92CC3F79D07` |
| `report/build_report_assets.py` | `1002EF1541001FC63E5A7DF2DDADAF423F8854F202EE51EFCBE919134940E248` |
| `report/plot_results.py` | `66D2DF9120C8745D06D76AAA34490D160708BB6FDFF8D09F19180CF3E26C2394` |
| `report/validate_results.py` | `44E3BCA908FB68EFCC303E69A9B452BCBBB2BCF36AC16B921625176E29534944` |
| `tests/test_simulator.py` | `A09DEE9AA5D4065D80FE7B9AF75EC5AC806C42A1E98DF4EDC84AA1C348B4285A` |
| `tests/test_metrics.py` | `02FD03E57D1061540A6E3B9771C0E1D18D75B547781FB14BB6CA17A8BCADDFBC` |
| `tests/test_experiments.py` | `9E2DBAD83723BDCEA581F3FE1B208E7CE55CD4808C747FD0925F6D5392E51F99` |

### Original experimental CSVs and manifests

| Path | SHA-256 |
|---|---|
| `results/full_20261121/raw_results.csv` | `8ABE1F28C744B491227FE5CE89552AEFB773232E32B816A3B9A8E264F1E2AE2E` |
| `results/full_20261121/b3_comparisons.csv` | `B8377ED4232568DC1ABCB5E50FB960BFDDFEAA5EAA1E7EEC609C91FC030E8EA1` |
| `results/full_20261121/summary_metrics.csv` | `FFF94314AAA04EA11B3B30393A12B1FAD4D4BC84151A26BC1E61B852DA9925B8` |
| `results/full_20261121/derived_rates_summary.csv` | `90E30E35B50BCB55F4C00351AFB16253BFDE5FDEFBA3E0869DF4B16D033B89BC` |
| `results/full_20261121/manifest.json` | `82F30CB208351AE9458E6C5DC22B4D5B621E8432021C6CC53338DC89219683B7` |
| `results/full_20261121/audit.json` | `94D64B5BA8053D4FE4AB82B2506ACE644ED91C770B187F4F5E5EA1C6FE54F446` |
| `results/full_20261121/run.log.jsonl` | `DA3FB4E4FC8D013E73AE2D4F78387D0EFF3CBE674256180024BEB190398C1BA8` |
| `results/full_20261121/deviations/deviation_cases.csv` | `77AD6E4B659FAFAF26A9788F68E851CA518E4DFF50FB0BD7D02BB977395E67F9` |
| `results/full_20261121/deviations/deviation_summary.csv` | `75D103EC5A27E8BB159FA597F8CFB4DE25EB1386F8F4DF3F4547818E5829EB0C` |
| `results/full_20261121/deviations/manifest.json` | `375651C1CF17B8A695A811C2B978B0BB6AD1AEBA03BAF0A331D192FEDB822ED4` |
| `docs/reference/original-proposal.pdf` | `8CECF4051109FE21F1E4EC3AE764C1AB86C27D84A4D26100061878EED3404EF2` |

### Simulator source hashes in the original run manifest

| Path | SHA-256 |
|---|---|
| `src/ambulance_dispatch/__init__.py` | `dc21b398b743962dcc001683ed51da6f07848b1e5ea5e91a0d83d1a324cf8fea` |
| `src/ambulance_dispatch/cli.py` | `dfe49cc9c989406f8086ec22caae45000d2161a322340f6258e70cc034ab8a35` |
| `src/ambulance_dispatch/communication.py` | `9309b1d234055250f4d36761bb0913dae984cbab553b98da7d658ea8d3f9b8e0` |
| `src/ambulance_dispatch/config.py` | `5e87a7f2c2030ed329701247ef5d67485e6c92aa21078b701f9f6a79c826e5eb` |
| `src/ambulance_dispatch/demand.py` | `ce0a019ac32e7c06193e0ce304ac728859baa3d6890d35a48f317f383fc39fcf` |
| `src/ambulance_dispatch/experiments.py` | `d908c74afd710e330540ac5c1b4d63ddb470a68f1f1e326820aed0b02322f5ae` |
| `src/ambulance_dispatch/graph.py` | `b6174a524c6498cbfda4e1816dcb3f506f4cb023230ca8f4487b17df1608e266` |
| `src/ambulance_dispatch/learning.py` | `c4f7d83a72c3c114d1f6c7239e403513509419be768b1adc91318f0d225fc1ca` |
| `src/ambulance_dispatch/metrics.py` | `3e3b0486999edf7aa01d92090053404cb5cf6cb74095008f06942d2eefa957f1` |
| `src/ambulance_dispatch/model.py` | `0c4b217003bcf053b198e258a91df5e165f2ad02d1efc84a09239092d584fa9d` |
| `src/ambulance_dispatch/plotting.py` | `fe57a966cde11bf6728050ba61bb4594f0b37d90edd39dd844eededbe114d406` |
| `src/ambulance_dispatch/policies/__init__.py` | `458260a1e1b1b6bee5174304d9a7b9f8e49538844ee57b4dbd5282c1392534c4` |
| `src/ambulance_dispatch/policies/baselines.py` | `55f1b21e07d8e67a45904e3a90e48e6ee5f7952cc9861b0f7b167931d00909e4` |
| `src/ambulance_dispatch/policies/bidding.py` | `7b88fc38548ccb66047a3f783d04c9d55ac9305662f23cc469408f04a5c9376d` |
| `src/ambulance_dispatch/policies/centralized.py` | `01786bad56613239d12bd5eba199ccfb9333fa8aa131e88e4995492b675b0421` |
| `src/ambulance_dispatch/policies/costs.py` | `839b9d5db4bc413546868e7d8206bdbeeb66cef6c418dc95b7ee81b5226954e9` |
| `src/ambulance_dispatch/simulator.py` | `07f258a5d7713f359f5e02ce792742d6b5b8777afdb1cd630b6c96b8ddef822b` |

## Baseline gaps established for follow-up

1. `mean_response_minutes` and `critical_mean_response_minutes` are calculated only from calls with a scene-arrival event, but report prose and plot labels do not consistently say “among served incidents.”
2. `exp7_weight_tradeoff` scales `beta` and `gamma` together (4/4, 8/8, 16/16) while `alpha` remains 1. It does not independently identify the three weight effects.
3. The existing experiment manifest has `git_revision: null` and does not explicitly serialize the `RunSettings` default communication radius and packet-loss probability. The exact values are source defaults, but the manifest should state them as a verified addendum without rewriting run history.
4. The report uses generic `article` formatting with manual two-column layout rather than a distinct arXiv manuscript style. The official arXiv guidance describes source processing and PDF checking; no official arXiv house-paper class was identified. A compatible third-party style choice remains to be resolved transparently.
5. The report has only brief interpretation for the seven families, despite complete tables/plots. More outcome-specific, qualified discussion is needed.
6. The shared call signal is intentional per the proposal observation tuple `e_t`; no-communication means no peer packets, not loss of emergency notification.
7. Deliverable files exist for each contribution, but repository contents cannot verify which person completed or authored each task. Existing “fulfilled” statuses describe deliverable presence and need to remain qualified.

## Current resolution status

The list above records issues as they stood at the baseline commit; it is not a statement of current project state. Their audited disposition is:

| Baseline finding | Current disposition | Evidence |
|---|---|---|
| Served-call response and communication outcomes need clearer labels and joint interpretation. | Addressed in model definitions, generated communication table, report discussion, and README. | `MODEL_DESIGN.md`; `report/generated/communication_table.tex`; `AUDIT/METRIC_REVIEW.md`; `AUDIT/REPORT_CLAIMS.md`. |
| Proposal experiment 7 changes beta and gamma together. | Retained as proposed and described as a joint sweep; independent alpha/beta/gamma extension is reported separately. | `configs/weight_sensitivity.json`; corrected sensitivity batch; Table 3; `FINAL_AUDIT.md`. |
| Original run manifest omitted the Git revision and communication defaults. | Historical manifest is unchanged; source-derived defaults are recorded in its addendum and the provenance limitation is disclosed. | `results/full_20261121/run_metadata_addendum.json`; `README.md`; `FINAL_ISSUES.md`. |
| Generic article formatting did not satisfy the instructor's arXiv-template request. | Report now uses the included MIT-licensed community `arxiv.sty` style. It is not misrepresented as an official arXiv house class; no universal official paper class was identified. | `report/main.tex`; `report/arxiv.sty`; `report/ARXIV_STYLE_LICENSE.txt`; `README.md`; `FINAL_ISSUES.md`. |
| Earlier report interpretation was too brief. | Results now include actual CSV-generated tables, plots, joint communication outcomes, sensitivity discussion, limitations, and a claim-to-evidence map. | `report/main.tex`; `AUDIT/REPORT_CLAIMS.md`; final PDF. |
| No-communication semantics needed clarification. | Shared public call announcements are distinguished from disabled peer messages throughout the model and implementation documentation. | `MODEL_DESIGN.md`; `AUDIT/IMPLEMENTATION_REVIEW.md`; `report/main.tex`. |
| Personal contribution fulfillment cannot be inferred from repository files. | Original assignments are listed; every personal fulfillment status is explicitly unverified rather than asserted. | Report Contribution table; `FINAL_ISSUES.md`. |

For the current final state, use `FINAL_AUDIT.md` and `FINAL_ISSUES.md`, not this baseline snapshot, as the completion record.

