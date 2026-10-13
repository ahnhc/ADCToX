ADCTOX 0.3: app updates and a Windows package.

- The app checks for a newer app once a day and shows it in the condition picker. `adctox --update-app` installs it (from this version on).
- Windows: download `ADCTOX-windows.zip`, unzip anywhere, double-click `ADCTOX.bat`. No installer and no admin rights; the first start downloads the models (about 1 GB). If the PC lacks the Microsoft Visual C++ Redistributable (x64), the program says so and links the official installer.
- Includes 0.2 and 0.2.1: one-screen confirmation for inputs with several meanings, symptoms and Korean disease names, three-model organ estimate (Both, Den, Fin), delta model updates, no screen flicker.

Ubuntu install or update:

```bash
curl -fsSL https://raw.githubusercontent.com/ahnhc/ADCToX/main/install.sh | bash
adctox
```

Ubuntu needs 24.04+ and Python 3.12+. Windows needs 64-bit Windows 10 or 11. Press U in the condition picker for model updates. App 0.2.1 and older have no `--update-app`; run the installer (or unzip the Windows package) once to reach 0.3.
