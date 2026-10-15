ADCTOX 0.3.3: belantamab mafodotin (BLENREP) added as the 15th ADC.

- **Label:** the current US label (version 2, 2026-10-06), read the same way as the other 14.
- **Evidence:** boxed ocular toxicity, thrombocytopenia.
- **Rules:**
  - Hepatic: mild impairment no adjustment; moderate or severe not established.
  - Renal: no adjustment outside dialysis.
  - Eye exam before every dose.
  - Withhold below 25,000/mcL platelets.

Update: `adctox --update-app`. New install:

```bash
curl -fsSL https://raw.githubusercontent.com/ahnhc/ADCToX/main/install.sh | bash      # Linux, macOS
```

```powershell
irm https://raw.githubusercontent.com/ahnhc/ADCToX/main/install.ps1 | iex             # Windows (PowerShell)
```

Models stay at 0.3.
