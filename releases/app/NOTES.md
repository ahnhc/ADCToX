# ADCTOX 0.7.6 Release Notes

- **Pictorial Brand Logo (`ADC` + `ToX`)**: Replaced the generic 3-bar header icon with an inline SVG vector rendition of the original ADCToX pictorial emblem (Erlenmeyer flask `A` with golden conjugate & bubbles + `D` + `C` in cyan, paired with syringe `T` + toxic droplet `o` + crossed bones `X` in crimson).
- **Patient-Tailored ADC Design (`Mode 1`) Upgrade**:
  - Added **`ADC 수동 설계` (`Manual ADC Design`)** alongside **`ADC 자동 설계` (`Auto-design ADC`)** and initialized the coordinate plane in an explicit ready state so candidate dots are plotted only after manual or automated design execution.
  - Upgraded the in-silico pharmacological scoring model with linker–payload chemical pairing affinity, payload-specific DAR hydrophobic aggregation ceilings (`optDar`, `maxSafeDar`, `hydro`), and tumor-indication target matching.
  - Fixed `.micro-popover` clipping by mounting tooltips to `document.body` with viewport-clamped fixed coordinates and full Korean/English descriptions across all 5 design groups (`Target`, `Linker`, `Payload`, `DAR`, `Fc`).
- **Workspace & Clinical UX Refinements**:
  - Active vulnerable organs now sort by severity (`%` descending) and visually highlight (`★ 우선 1위` / `★ Priority #1`) when clicked to prioritize protection of that organ across drug ranking and construct simulation.
  - Added interactive hover/selection animations on condition autocomplete options and continuous top progress bar feedback during semantic mapping and background model inference.
  - Simplified the Mode 2 header to **`검진 정보` (`Lab Values`)** and streamlined the Mode 0 `#1` spotlight badge.
