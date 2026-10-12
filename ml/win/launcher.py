"""ADC Recommender.exe (built windowless): opens app\\ADC_Recommender.exe in Windows Terminal, or in a console window when
Windows Terminal is not installed. Being windowless, it leaves no extra cmd window behind."""
import os, shutil, subprocess, sys

here = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
app = os.path.join(here, "app", "ADC_Recommender.exe")
env = {k: v for k, v in os.environ.items() if not k.startswith(("_PYI", "_MEI"))}; env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
wt = shutil.which("wt")
try:
    if not wt: raise OSError
    subprocess.Popen([wt, "--size", "120,42", "new-tab", "--title", "ADC Recommender", "--", app, "--no-wt"], env=env, close_fds=True)
except OSError:
    subprocess.Popen([app, "--no-wt"], env=env, close_fds=True, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
