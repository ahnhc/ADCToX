# ADCTOX 0.7.8 Release Notes

- **Workflow-Ordered Navigation (`1. Patient Info` → `2. ADC Matrix` → `3. De Novo ADC Design`) & Default English UI**:
  - Reordered top workspace tabs so users start directly on **`1. Patient Info` (`환자 정보`)**, proceed to **`2. ADC Matrix` (`ADC 매트릭스`)**, and then open **`3. De Novo ADC Design` (`ADC 신규 설계`)**.
  - Set default launch language to English (`EN / KO` toggle in header) and renamed `Structure Studio` (`구조 스튜디오`) to **`De Novo ADC Design` (`ADC 신규 설계`)** across navigation, drawers, and the workspace guide.
- **Patient-Input Guard & Interactive Scoring Formula Tuner (`Mode 2: De Novo ADC Design`)**:
  - Added `hasPatientProfile()` validation so clicking `Manual ADC Design` or `Auto-design ADC` without entered conditions or lab values prompts the user to enter patient information first rather than simulating on fallback organs.
  - Upgraded **`Scoring Formula` (`점수 계산식`)** into an interactive live parameter tuning panel with synchronized sliders and numeric inputs for all 12 PK/PD model coefficients (`w_peak`, `k_risk`, normal expression weight, DAR load exponent, Fc-silenced factor, priority organ multiplier, and efficacy exponents) plus a 1-click **`Reset Defaults` (`기본값 복원`)** button.
- **Physiologically Scaled Lab Reference Bars & Guide Indicator Alignment**:
  - Aligned each biomarker's gray reference zone (`.bio-spectrum-normal`), boundary ticks (`refLow` / `refHigh`), and live value needle (`.bio-spectrum-needle`) onto a unified physiological scale with instant `oninput` feedback and distinct `Low` (`수치 저하`) vs. `Elevated` (`수치 상승`) badges.
  - Standardized visual indicator badges in the `?` Workspace Guide modal so `Treatment vs Control` (`치료군 vs 대조군`) matches the exact dimensions of the dosing status badges, and removed the redundant spotlight subtitle hint.
