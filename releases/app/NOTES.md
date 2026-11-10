# ADCTOX 0.7.7 Release Notes

- **Collision-Free Design Chart & Dynamic Manual/Auto Coordinate Visualization (`Mode 1`)**:
  - Locked canvas plot-area padding (`padT = 42 * dpr`) and responsive single-row legend sizing so the coordinate plane never shifts vertically when switching between manual and automated design modes.
  - Merged callout pill (`추천 · 현재 선택: ...` / `Best · Selected: ...`) when the automated optimum and current selection coincide, with full bounding-box collision resolution when they differ.
  - Plotted continuous unrounded `(safetyRaw, efficacyRaw)` coordinates, target normal-tissue baseline risk (`tgt.tissues`), Pareto frontier trajectory in `Auto-design ADC`, and target-filtered sub-cloud + FDA reference ADC comparison vector + design trajectory in `Manual ADC Design`.
- **Malignancy Organ Vulnerability Mapping & Clean Priority Selection**:
  - Added pathophysiological organ vulnerability mapping and probabilistic multi-condition score compounding (`mergeOrganScore`) so hematologic and solid malignancies (`breast cancer`, `lung cancer`, `Lymphoid leukemia`, `Myeloid leukemia`, etc.) accurately populate active vulnerable organs even when entered without separate comorbidities.
  - Replaced decorative priority badges with clean structural border/background highlighting (`.organ-meter-btn.prio-active`).
- **Navigation, `How it works` Modal & Scoring Formula Box Polish**:
  - Removed duplicate step numbers (`1. 1.`) in both the top navigation bar and the `How it works` guide modal, and redesigned the modal steps and keyboard shortcuts into structured cards.
  - Styled the expandable **`점수 계산식` (`Scoring Formula`)** container with balanced vertical spacing and concise monospace equations.
