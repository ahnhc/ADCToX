#!/usr/bin/env bash
set -euo pipefail

# Ubuntu installer; no sudo, native Windows packaging, or patient-input handling.
if [[ "$(uname -s)" != Linux ]]; then
  echo 'This installer targets Ubuntu/Linux. On Windows, run it inside Ubuntu on WSL.' >&2
  exit 1
fi
command -v curl >/dev/null || { echo 'curl is required.' >&2; exit 1; }
task_python="${ADCTOX_PYTHON:-python3}"
"$task_python" -c 'import sys; assert sys.version_info >= (3, 12), "Python 3.12+ is required (Ubuntu 24.04 or newer)"'
task_prefix="${ADCTOX_INSTALL_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/adctox}"
task_bin="${ADCTOX_BIN_DIR:-$HOME/.local/bin}"
task_manifest="${ADCTOX_APP_MANIFEST:-https://raw.githubusercontent.com/ahnhc/ADCToX/main/releases/app/stable.json}"
task_tmp="$(mktemp -d -t adctox-install.XXXXXXXX)"
trap 'rm -rf "$task_tmp"' EXIT

curl --proto '=https' --tlsv1.2 -fsSL --retry 2 "$task_manifest" -o "$task_tmp/app.json"
mapfile -t task_fields < <("$task_python" - "$task_tmp/app.json" <<'PY'
import json,re,sys,urllib.parse
d=json.load(open(sys.argv[1])); assert d['schema_version']==1 and d['runtime_api']==1
assert re.fullmatch(r'\d+\.\d+(?:\.\d+)?',d['app_version'])
assert re.fullmatch(r'[0-9a-f]{64}',d['sha256'])
assert urllib.parse.urlsplit(d['url']).scheme=='https'
assert type(d['size']) is int and 0<d['size']<50*1024**2
assert re.fullmatch(r'\d+\.\d+\.\d+',d['torch_version'])
print(d['app_version']);print(d['url']);print(d['sha256']);print(d['size']);print(d['torch_version'])
PY
)
[[ ${#task_fields[@]} == 5 ]] || { echo 'Invalid app release manifest.' >&2; exit 1; }
task_version="${task_fields[0]}"
echo "Installing ADCTOX $task_version"
curl --proto '=https' --tlsv1.2 -fsSL --retry 2 --max-filesize "${task_fields[3]}" "${task_fields[1]}" -o "$task_tmp/app.tar.gz"
"$task_python" - "$task_tmp" "${task_fields[2]}" "${task_fields[3]}" <<'PY'
import hashlib,pathlib,sys,tarfile
p=pathlib.Path(sys.argv[1]);a=p/'app.tar.gz'
assert a.stat().st_size==int(sys.argv[3]),'App download size mismatch'
assert hashlib.sha256(a.read_bytes()).hexdigest()==sys.argv[2],'App checksum mismatch'
with tarfile.open(a) as t:
 names={'adc_recommender_full.py','requirements-cpu.txt','bundle-info.json'}
 assert len(t.getmembers())==3 and {m.name for m in t.getmembers()}==names
 assert all(m.isfile() for m in t.getmembers())
 t.extractall(p/'app',filter='data') if sys.version_info>=(3,12) else t.extractall(p/'app')
PY
mkdir -p "$task_prefix/apps" "$task_prefix/venvs" "$task_bin"
task_env="$task_prefix/venvs/runtime-1"
if [[ ! -x "$task_env/bin/python" ]]; then
  "$task_python" -m venv "$task_env" || { echo 'Install python3-venv, then rerun the installer.' >&2; exit 1; }
fi
if [[ "${ADCTOX_SKIP_DEPS:-0}" != 1 ]]; then
  "$task_env/bin/python" -m pip install --disable-pip-version-check "torch==${task_fields[4]}" --index-url https://download.pytorch.org/whl/cpu
  "$task_env/bin/python" -m pip install --disable-pip-version-check -r "$task_tmp/app/requirements-cpu.txt"
fi
if [[ "${ADCTOX_SKIP_MODELS:-0}" != 1 ]]; then
  ADC_MODEL_HOME="$task_prefix/models" "$task_env/bin/python" -I "$task_tmp/app/adc_recommender_full.py" --update-models
fi
task_release="$task_prefix/apps/$task_version-${task_fields[2]:0:12}"
if [[ ! -d "$task_release" ]]; then mv "$task_tmp/app" "$task_release"; fi
"$task_python" - "$task_prefix" "$task_release" "$task_bin" <<'PY'
import os,pathlib,shlex,sys
prefix,release,bindir=map(pathlib.Path,sys.argv[1:]);link=prefix/'.app-next'
link.unlink(missing_ok=True);link.symlink_to(release);os.replace(link,prefix/'current')
launcher=bindir/'adctox';temporary=bindir/'.adctox-next'
q=shlex.quote
temporary.write_text('#!/usr/bin/env bash\nset -e\nexport ADC_MODEL_HOME='+q(str(prefix/'models'))+'\nexec '+q(str(prefix/'venvs/runtime-1/bin/python'))+' -I '+q(str(prefix/'current/adc_recommender_full.py'))+' "$@"\n')
temporary.chmod(0o755);os.replace(temporary,launcher)
print('Installed: '+str(launcher))
PY
echo 'Run: adctox'
if [[ ":$PATH:" != *":$task_bin:"* ]]; then
  printf 'Add to PATH: export PATH=%q:"$PATH"\n' "$task_bin"
fi
