"""Application and model-runtime compatibility versions (Ubuntu and Windows share them)."""
APP_VERSION = "0.3.8"
RUNTIME_API = 1
REPOSITORY = "ahnhc/ADCToX"
# stable2.json: model bundles with the Gemma organ judge (model 0.5+); apps up to 0.3.7 read stable.json, which stays at 0.4,
# because their updater rejects the GemmaJudge/ folder
MODEL_MANIFEST_URL = f"https://raw.githubusercontent.com/{REPOSITORY}/main/releases/models/stable2.json"
APP_MANIFEST_URL = f"https://raw.githubusercontent.com/{REPOSITORY}/main/releases/app/stable.json"
