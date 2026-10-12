Ubuntu terminal release with independent model updates.

Install:

```bash
curl -fsSL https://raw.githubusercontent.com/ahnhc/ADCToX/main/install.sh | bash
adctox
```

Requires Ubuntu 24.04+ and Python 3.12+. Press U in the condition picker for model updates, or run `adctox --update-models`. App and model versions are independent. Native Windows packaging is not included; use Ubuntu in WSL.

The archive contains the app, CPU dependency list, and source hashes. Model weights are downloaded separately. See the repository's research documentation and third-party notices.
