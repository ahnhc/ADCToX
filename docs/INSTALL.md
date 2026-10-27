# 설치 (Linux, macOS, Windows)

## 기본 설치

| 운영체제 | 명령 | 조건 |
|---|---|---|
| Linux (x86_64, arm64) | `curl -fsSL https://raw.githubusercontent.com/ahnhc/ADCToX/main/install.sh \| bash` | glibc 기반 배포판(Ubuntu 22.04 이상 확인), `curl` |
| macOS (Apple silicon) | 위와 같은 명령 | macOS 11 이상. Intel Mac은 PyTorch 2.11 빌드가 없어 지원하지 않는다 |
| Windows 10, 11 (64비트) | PowerShell에서 `irm https://raw.githubusercontent.com/ahnhc/ADCToX/main/install.ps1 \| iex` | 관리자 권한 불필요 |

- `Python 3.12` 이상(venv 포함)이 있으면 그것을 쓴다.
- 없으면 고정 버전 uv(0.12.17, SHA256 확인)를 임시로 받는다. 그 uv가 Python 3.12를 `~/.local/share/adctox/python`에 설치한다. 시스템 Python과 패키지는 건드리지 않는다.
- 특정 Python을 쓰려면 `ADCTOX_PYTHON=/path/to/python3.12`를 지정한다.
- Windows 설치기가 하는 일:
  - 공식 embeddable Python이 든 패키지를 받아 SHA256을 확인한다.
  - `%LOCALAPPDATA%\adctox\app`에 푼다.
  - 시작 메뉴와 바탕화면 바로가기, `adctox` 명령(사용자 PATH)을 만든다.
  - 모델을 받는다.
- 다시 실행하면 앱을 새 버전으로 바꾼다.

Linux에서 `venv`가 없다는 메시지가 나오면 다음 패키지를 설치하고 다시 실행한다.

```bash
sudo apt install python3-venv
```

설치기는 sudo를 사용하지 않는다. 기본 CPU PyTorch와 추론 의존성, 약 1.4 GiB의 모델 파일(모델 0.7: 처음부터 만든 판정 모델 302 MB 포함)을 설치한다. BioLORD와 SapBERT는 원본 Hugging Face 저장소의 고정 revision에서 받는다. upstream 이용 조건은 [THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES.md)를 참고한다.

설치 후 분석은 로컬에서 실행하며 입력한 질환이나 검사값을 업데이트 서버로 전송하지 않는다. 인터넷 연결은 설치 및 사용자가 요청한 업데이트에 사용한다. 입력 중 상태 파일은 기존 터미널 동작에 따라 `~/.config/adctox/last_input.json`에 저장될 수 있다.

## 설치 위치

```text
~/.local/bin/adctox
~/.local/share/adctox/
    current -> apps/<app-version>-<checksum>/
    apps/                         앱 코드
    venvs/runtime-1/              CPU 추론 환경
    models/
        current -> versions/<bundle>/
        versions/                 설치한 모델 묶음
        blobs/                    파일 해시별 저장소
        previous.json             이전 모델 정보
```

`XDG_DATA_HOME`을 설정했다면 해당 위치를 사용한다. 명령이 검색되지 않으면 아래 내용을 shell 설정에 추가한다.

```bash
export PATH="$HOME/.local/bin:$PATH"
```

경로를 바꾸려면 설치 스크립트를 먼저 받은 뒤 환경변수를 지정한다.

```bash
curl -fsSL https://raw.githubusercontent.com/ahnhc/ADCToX/main/install.sh -o /tmp/adctox-install.sh
ADCTOX_INSTALL_DIR="$HOME/apps/adctox" ADCTOX_BIN_DIR="$HOME/.local/bin" bash /tmp/adctox-install.sh
```

## 업데이트

모델 업데이트는 터미널 명령으로 한다. 다운로드가 끝나면 다음 실행부터 새 모델을 쓴다.

```bash
adctox --check-models
adctox --update-models
adctox --model-version
adctox --rollback-models
```

업데이트는 변경된 파일을 통째로 받는 방식이다. 동일한 encoder와 index는 재사용하지만 변경된 가중치 파일 내부의 byte patch를 받는 것은 아니다. 연결이 끊기거나 검증에 실패하면 현재 모델을 계속 선택한다. 받은 파일은 다음 시도에서 검증 후 재사용된다. 중단된 파일의 부분 다운로드 재개는 현재 지원하지 않는다.

앱 코드는 `adctox --update-app`으로 업데이트하거나 설치 명령을 다시 실행한다. 모델 업데이트만으로는 Python 의존성을 변경하지 않는다. 새로운 모델 구조가 runtime API를 바꾸면 먼저 앱 업데이트를 요구한다.

`ADC_MODEL_DIR`은 개발자가 특정 모델 디렉터리를 직접 고정하는 기존 옵션이다. 이 옵션을 설정한 상태에서는 기본 설치 경로의 새 모델보다 지정한 경로가 우선하므로 일반 사용에서는 설정하지 않는다.

## Windows

설치 위치는 `%LOCALAPPDATA%\adctox\app`(앱과 Python), `%LOCALAPPDATA%\adctox\models`(모델), `%LOCALAPPDATA%\adctox\bin\adctox.cmd`(명령)이다. 설치기 없이 쓰려면 Release의 `ADCTOX-windows.zip`을 아무 곳에 풀고 `ADCTOX.bat`을 실행해도 된다. PC에 Microsoft Visual C++ 재배포 패키지(x64)가 없으면 프로그램이 공식 설치 링크를 알려 준다.

삭제: `%LOCALAPPDATA%\adctox` 폴더와 바로가기를 지우고, 사용자 PATH에서 `%LOCALAPPDATA%\adctox\bin`을 뺀다.

## GPU 환경

기본 설치는 CPU 환경이다. 기존 GPU용 PyTorch 환경을 이용하려면 추론 의존성이 준비된 환경을 설치 위치의 `venvs/runtime-1`에 연결하고 개발자용 `ADCTOX_SKIP_DEPS=1` 옵션을 사용한다. 앱은 그 환경에서 CUDA가 보이면 GPU를 사용한다. 일반 설치 명령이 GPU용 PyTorch를 보존한다고 가정하지 않는다.

## 삭제

기본 경로로 설치했다면 다음 파일과 디렉터리를 삭제한다. 사용자 지정 경로를 썼으면 그 경로를 사용한다.

```bash
rm "$HOME/.local/bin/adctox"
rm -r "$HOME/.local/share/adctox"          # 앱, 모델, uv로 받은 Python 모두
```

남은 입력 상태도 지우려면 `~/.config/adctox/last_input.json`을 삭제한다.
