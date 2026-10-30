#!/usr/bin/env bash
set -euo pipefail

# Linux and macOS (Apple silicon) installer; no sudo, no patient-input handling. Windows: install.ps1.
# Uses Python 3.12+ when one is installed; otherwise downloads a pinned uv (checksum verified) and lets it fetch Python 3.12
# into the install folder. Written for bash 3.2 (the macOS default): no mapfile, no associative arrays.
task_os="$(uname -s)"; task_arch="$(uname -m)"
case "$task_os/$task_arch" in
  Linux/x86_64) task_uv_target=x86_64-unknown-linux-gnu; task_uv_sha=fa82fd8dde8e8eefdecada6aa0889666556cfceb690d06e0c3bca49eb3070a63 ;;
  Linux/aarch64|Linux/arm64) task_uv_target=aarch64-unknown-linux-gnu; task_uv_sha=d636d1b678e9e7f367ecb22b46bd1cabbed234d6bc3b4d96365d2b507f72f86c ;;
  Darwin/arm64) task_uv_target=aarch64-apple-darwin; task_uv_sha=85f00cbdc6dd3e97eba4c31b4d014375a9fdfe8f570023b84e5102fc3456896b ;;
  Darwin/x86_64) echo 'Intel Macs are not supported: PyTorch publishes no macOS Intel builds for this version. Use an Apple silicon Mac.' >&2; exit 1 ;;
  *) echo "Unsupported system: $task_os $task_arch. On Windows, run in PowerShell: irm https://raw.githubusercontent.com/ahnhc/ADCToX/main/install.ps1 | iex" >&2; exit 1 ;;
esac
command -v curl >/dev/null || { echo 'curl is required.' >&2; exit 1; }
task_prefix="${ADCTOX_INSTALL_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/adctox}"
task_bin="${ADCTOX_BIN_DIR:-$HOME/.local/bin}"
task_manifest="${ADCTOX_APP_MANIFEST:-https://raw.githubusercontent.com/ahnhc/ADCToX/main/releases/app/stable.json}"
task_uv_version=0.12.17
task_tmp="$(mktemp -d "${TMPDIR:-/tmp}/adctox-install.XXXXXXXX")"
trap 'rm -rf "$task_tmp"' EXIT
task_env="$task_prefix/venvs/runtime-1"
mkdir -p "$task_prefix/apps" "$task_prefix/venvs" "$task_bin"

python_ok() {   # a Python 3.12+ that can make a virtual environment with pip
  "$1" -c 'import sys, venv, ensurepip; assert sys.version_info >= (3, 12)' >/dev/null 2>&1
}
task_python=""
if [[ -x "$task_env/bin/python" ]] && "$task_env/bin/python" -c 'import sys; assert sys.version_info >= (3, 12)' >/dev/null 2>&1; then
  task_python="$task_env/bin/python"                       # reinstall or update: keep the existing runtime
else
  for c in ${ADCTOX_PYTHON:-} python3.14 python3.13 python3.12 python3; do
    p="$(command -v "$c" 2>/dev/null || true)"
    [[ -n "$p" ]] || continue
    if [[ "$task_os" == Darwin && "$p" == /usr/bin/python3 ]]; then continue; fi   # the Xcode stub (3.9) may open an install dialog
    if python_ok "$p"; then task_python="$p"; break; fi
  done
  if [[ "${ADCTOX_FORCE_UV:-0}" == 1 ]]; then task_python=""; fi       # tests: take the uv path even when a Python is installed
  if [[ -z "$task_python" ]]; then
    echo "No Python 3.12+ with venv found; downloading uv $task_uv_version to install Python 3.12 into $task_prefix/python"
    curl --proto '=https' --tlsv1.2 -fsSL --retry 2 "https://github.com/astral-sh/uv/releases/download/$task_uv_version/uv-$task_uv_target.tar.gz" -o "$task_tmp/uv.tar.gz"
    task_sum="$( (sha256sum "$task_tmp/uv.tar.gz" 2>/dev/null || shasum -a 256 "$task_tmp/uv.tar.gz") | cut -d' ' -f1)"
    [[ "$task_sum" == "$task_uv_sha" ]] || { echo 'uv download failed verification.' >&2; exit 1; }
    tar -xzf "$task_tmp/uv.tar.gz" -C "$task_tmp"
    task_uv="$task_tmp/uv-$task_uv_target/uv"
    UV_PYTHON_INSTALL_DIR="$task_prefix/python" "$task_uv" venv --quiet --seed --python 3.12 --managed-python "$task_env"
    task_python="$task_env/bin/python"
  fi
fi

curl --proto '=https' --tlsv1.2 -fsSL --retry 2 "$task_manifest" -o "$task_tmp/app.json"
task_fields=()
while IFS= read -r line; do task_fields+=("$line"); done < <("$task_python" - "$task_tmp/app.json" <<'PY'
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
echo "Installing ADCTOX $task_version ($task_os $task_arch)"
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
if [[ ! -x "$task_env/bin/python" ]]; then
  "$task_python" -m venv "$task_env" || { echo 'Could not create a virtual environment (on Ubuntu: install python3-venv), then rerun.' >&2; exit 1; }
fi
if [[ "${ADCTOX_SKIP_DEPS:-0}" != 1 ]]; then
  if [[ "$task_os" == Linux ]]; then
    "$task_env/bin/python" -m pip install --disable-pip-version-check "torch==${task_fields[4]}" --index-url https://download.pytorch.org/whl/cpu
  else
    "$task_env/bin/python" -m pip install --disable-pip-version-check "torch==${task_fields[4]}"      # macOS: the PyPI build (CPU and Apple GPU)
  fi
  "$task_env/bin/python" -m pip install --disable-pip-version-check -r "$task_tmp/app/requirements-cpu.txt"
fi
if [[ "${ADCTOX_SKIP_MODELS:-0}" != 1 ]]; then
  ADC_MODEL_HOME="$task_prefix/models" "$task_env/bin/python" -I "$task_tmp/app/adc_recommender_full.py" --update-models
fi
task_release="$task_prefix/apps/$task_version-${task_fields[2]:0:12}"
if [[ ! -d "$task_release" ]]; then mv "$task_tmp/app" "$task_release"; fi
"$task_env/bin/python" - "$task_prefix" "$task_release" "$task_bin" <<'PY'
import os,pathlib,shlex,sys
prefix,release,bindir=map(pathlib.Path,sys.argv[1:]);link=prefix/'.app-next'
link.unlink(missing_ok=True);link.symlink_to(release);os.replace(link,prefix/'current')
launcher=bindir/'adctox';temporary=bindir/'.adctox-next'
q=shlex.quote
temporary.write_text('#!/usr/bin/env bash\nset -e\nexport ADC_MODEL_HOME='+q(str(prefix/'models'))+'\nexec '+q(str(prefix/'venvs/runtime-1/bin/python'))+' -I '+q(str(prefix/'current/adc_recommender_full.py'))+' "$@"\n')
temporary.chmod(0o755);os.replace(temporary,launcher)
web=bindir/'adctox-web';temporary=bindir/'.adctox-web-next'
temporary.write_text(launcher.read_text().replace(' "$@"',' --web "$@"',1));temporary.chmod(0o755);os.replace(temporary,web)
print('Installed: '+str(launcher)+', '+str(web))
PY
echo 'Run: adctox   (in the browser: adctox-web)'
if [[ ":$PATH:" != *":$task_bin:"* ]]; then
  task_rc="$HOME/.bashrc"; [[ "$task_os" == Darwin || "${SHELL:-}" == */zsh ]] && task_rc="$HOME/.zprofile"
  echo 'Add to PATH (then open a new terminal):'
  echo "  echo 'export PATH=\"$task_bin:\$PATH\"' >> $task_rc"
fi
