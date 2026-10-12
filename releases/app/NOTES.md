ADCTOX 0.2.1: fixes screen flicker on the model update and analysis screens (full clears on every redraw). Includes everything in 0.2:

- Typed text with several meanings (for example `asd`) is confirmed on one screen with each candidate and its organs.
- Symptoms such as `amnesia` link to the Human Phenotype Ontology; diseases outside the 13 organs show as `MONDO (no organ axis)`.
- Korean disease names are understood (당뇨, 치매, 자폐증, 중풍, 고지혈증 and formal KCD names).
- The analysis review shows the learned estimate of three models (Both, Den, Fin) with how many agree on each organ; automatic use keeps organs at least two agree on.
- Model updates download only changed files; `adctox --verify-models` re-hashes on request.

Install or update the app:

```bash
curl -fsSL https://raw.githubusercontent.com/ahnhc/ADCToX/main/install.sh | bash
adctox
```

Requires Ubuntu 24.04+ and Python 3.12+. Press U in the condition picker for model updates. App and model versions are independent; app 0.2 works with model 0.0 to 0.2, and app 0.1 can read model 0.2 without the new screens. Native Windows packaging is not included; use Ubuntu in WSL.
