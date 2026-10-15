# GitHub 버전 관리와 배포 (Linux, macOS, Windows)

## 구분

| 대상 | 버전과 위치 | 배포 방식 |
|---|---|---|
| 앱 | `ml/adc_version.py`, 현재 0.3.1 | Git tag `v0.3.1`, GitHub Release의 `adctox-ubuntu.tar.gz`(Linux, macOS 공용), `ADCTOX-windows.zip` |
| 모델 묶음 | `releases/models/stable.json`, 현재 0.2 | 별도 tag `models-0.2`, MLP 및 MONDO index assets |
| 기본 encoder | manifest에 고정한 HF revision | 원본 Hugging Face에서 파일별 다운로드 |
| 연구 자료 | `ml/docs`, `ml/results`, `report`, `docs` | Git 이력 및 README 링크 |
| 학습 원본 | 원본 워크북과 로컬 cache | Git 및 앱 archive에 포함하지 않음 |

GitHub 저장소는 [ahnhc/ADCToX](https://github.com/ahnhc/ADCToX)다. 앱과 모델의 stable manifest는 서로 독립적으로 변경할 수 있다. GitHub Releases는 파일별 2 GiB 미만의 asset을 배포할 수 있어 현재 파일 크기에 별도 Oracle 서버가 필요하지 않다. [GitHub 공식 안내](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).

## 앱 빌드

`ml/build_portable.py --full`을 재사용한다. 추론 함수와 터미널 모듈을 하나의 Python 파일에 넣고, 원본 워크북 대신 factual label evidence를 포함한다. 기본 encoder와 학습 가중치는 넣지 않는다.

```bash
python -I scripts/build_ubuntu_release.py
```

`ml/data/label_evidence.json`이 있으면 raw cache 없이 빌드할 수 있다. 이 파일은 `ml/drug_evidence.py`로 얻은 라벨 경고와 수치 근거이며 원본 워크북이 아니다. 라벨 snapshot을 갱신할 때 이 파일도 명시적으로 재생성해야 한다. 규칙, registry 및 checks는 현재 `conf/`에서 읽는다.

산출물은 `dist/releases/app/`에 생기며 `releases/app/stable.json`에 URL, 크기, SHA256을 기록한다. archive에는 다음 세 파일만 있다.

```text
adc_recommender_full.py
requirements-cpu.txt
bundle-info.json
```

`bundle-info.json`은 포함한 핵심 소스의 해시를 기록한다. 앱을 바꾸면 `APP_VERSION`과 CHANGELOG를 함께 갱신하고 새로운 tag로 배포한다. 이미 배포한 tag의 파일을 다른 내용으로 덮어쓰는 방식은 사용하지 않는다.

## 모델 빌드

현재 학습 환경에서 실행한다.

```bash
/data/hyeongchanahn/envs/adctox/bin/python -I scripts/build_ubuntu_release.py --models --model-version 0.0
```

로컬 cache의 학습 head와 MONDO index를 export한다. 학습을 다시 수행하는 명령은 아니다. 배포 checkpoint는 tensor와 기본형 metadata만 포함해 `torch.load(weights_only=True)`로 읽으며, 배포 MONDO index는 object array 대신 문자열 array를 사용해 `allow_pickle=False`로 읽는다. 수치 및 모델 구조는 기존 구현과 동일하다.

파일별 URL, 크기, SHA256, 모델 버전, 장기 축 순서, architecture 및 runtime API를 manifest에 기록한다. 학습 head만 바뀌면 다른 파일의 SHA256은 그대로 유지한다. 업데이트 시 그 파일만 새로 다운로드한다.

기본 encoder revision은 `scripts/build_ubuntu_release.py`의 `ENCODERS`에 있다. 향후 fine-tuned encoder를 배포할 때는 원본 encoder 대신 새 encoder의 모든 파일을 manifest에 등록하고, 같은 encoder로 만든 MLP 입력 및 MONDO index의 호환성을 함께 검증해야 한다. manifest의 파일 URL은 HTTPS GitHub Release 또는 Oracle mirror도 지원한다. 기존 encoder와 새로운 index를 검증 없이 혼합하면 안 된다.

호환되지 않는 architecture, 축 순서, runtime API는 모델 업데이트에서 거절한다. 단순히 metadata 버전을 올리는 것만으로 새 구조가 지원되지는 않는다. 새 구조에는 앱 runtime과 검증도 필요하다.

## 공개 순서

로컬에서 확인한 뒤 Git 이력을 push하고, 모델 Release를 먼저 준비한다. 두 tag 모두 main의 정확한 commit을 가리키게 한다.

```bash
git push -u origin main
gh release create models-0.0 --target main --latest=false --title 'Models 0.0' --notes-file releases/models/NOTES.md dist/releases/models/vuln_biolord.pt dist/releases/models/mondo_index.npz dist/releases/models/models.json
gh release create v0.1.0 --target main --latest --title 'ADCTOX 0.1' --notes-file releases/app/NOTES.md dist/releases/app/adctox-ubuntu.tar.gz dist/releases/app/app.json
```

최초 공개 준비 중에는 채널과 asset 게시 사이에 짧은 불일치가 생길 수 있으므로 설치 명령을 공유하기 전에 실제 URL에서 새 설치를 확인한다. 이후 업데이트는 새 asset을 먼저 올리고 검증한 다음 stable manifest를 가리키게 한다. 위 예시는 첫 공개 버전용이며 다음 배포에는 새로운 버전과 tag를 사용한다.

GitHub Actions는 새 push/PR에서 updater, 터미널 및 추천기 테스트와 raw 데이터 없는 앱 빌드를 확인한다. 전체 임상 연구 suite나 모델 정확도를 검증했다는 의미는 아니다. 원본 cache가 필요한 일부 테스트는 CI에서 skip된다.

## 모델 전환 및 복원

다운로드 중에는 기존 current bundle을 변경하지 않는다. 파일을 해시별 `blobs`에 검증한 뒤 version 디렉터리를 완성하고 `current` symlink를 atomic rename으로 전환한다. 새 version은 기존 directory를 수정하지 않는다. 동시에 두 업데이트가 실행되지 않도록 파일 lock을 사용한다.

이전 모델의 파일이 온전하면 `--rollback-models`로 복원할 수 있다. 오래된 version 및 blob은 자동 삭제하지 않아 업데이트 횟수에 따라 저장 공간이 늘 수 있다. 모델 파일이 로컬에서 손상되면 재검증 후 다시 다운로드한다.

개발 서버의 기존 NumPy pickle checkpoint는 연구 재현을 위해 남아 있다. manifest가 있는 배포 bundle에서는 제한된 loader를 사용한다. 학습 스크립트를 직접 실행할 때는 `ADC_RESEARCH_MODE=1`로 설치 모델과 분리한다. `vulnerability_model.py`의 직접 학습/export 경로는 이를 자동 설정한다.

## Windows 패키지 (0.3부터)

```bash
/data/hyeongchanahn/envs/adctox/bin/python -I scripts/build_ubuntu_release.py           # 앱 archive 먼저
/data/hyeongchanahn/envs/adctox/bin/python -I scripts/build_windows_release.py          # dist/releases/windows/ADCTOX-windows.zip
```

- Linux에서 만든다. 공식 embeddable CPython 3.12.10(SHA256 고정)에 win_amd64 wheel을 풀어 넣는다. 의존성은 uv가 Windows 기준으로 풀고(`pip download --platform`은 빌드 머신의 marker를 적용해 Linux 전용 CUDA 패키지를 끌어온다), pip가 고정된 wheel을 받는다. 잠금 목록은 cache의 `windows-lock.txt`.
- 앱 파일은 Ubuntu와 같은 archive를 `apps/<release>/`에 풀고 `app.txt`로 선택한다. 그래서 `--update-app`이 두 OS에서 같게 동작한다.
- 모델은 첫 실행 때 `%LOCALAPPDATA%\adctox\models`로 받는다. Windows에서는 디렉터리 symlink 대신 `current.txt`로 현재 bundle을 가리키고, lock은 `msvcrt`를 쓴다.
- Microsoft Visual C++ 런타임은 기본으로 넣지 않는다. 없는 PC에서는 launcher가 공식 설치 링크를 안내한다. Visual Studio 라이선스(Community 포함)가 있으면 `--bundle-vc-runtime`으로 넣을 수 있다.
- 실제 Windows 검증은 GitHub Actions의 `windows-smoke` job이 한다: updater 테스트, 압축 해제, 모델 다운로드, 질환 분석 실행.

Release에는 `ADCTOX-windows.zip`을 앱 Release의 asset으로 함께 올린다. 빌드는 `releases/app/windows.json`(크기, SHA256, URL)도 갱신하는데, Windows 한 줄 설치기 `install.ps1`이 이 파일을 읽는다.

## 한 줄 설치기 (0.3.1부터)

| 파일 | 대상 | 읽는 manifest |
|---|---|---|
| `install.sh` | Linux x86_64/arm64, macOS Apple silicon | `releases/app/stable.json` |
| `install.ps1` | Windows 10/11 64비트 | `releases/app/windows.json` |

`install.sh`는 Python 3.12+가 없으면 고정 버전 uv(0.12.17, 플랫폼별 SHA256을 스크립트에 고정)로 Python 3.12를 설치 폴더 안에 받는다. uv 버전을 바꿀 때는 세 플랫폼의 `.sha256`을 함께 갱신한다. 배포 후 `.github/workflows/install.yml`이 Release 게시 시점에 Ubuntu 22.04/24.04, macOS 14/15, Windows에서 공개 설치 명령을 그대로 실행하고 앱을 돌려 본다.

## Oracle mirror가 필요한 경우

현재는 사용하지 않는다. 나중에 GitHub 다운로드 정책이나 배포 환경 때문에 mirror가 필요하면 같은 파일을 HTTPS로 제공하고 manifest의 URL을 바꾸면 된다. 앱 업데이트 코드를 새로 만들 필요는 없다.

테스트 또는 별도 mirror를 사용하는 개발자 환경에는 다음 설정을 사용할 수 있다.

```text
ADCTOX_APP_MANIFEST     설치기의 앱 manifest URL
ADCTOX_MODEL_MANIFEST   모델 업데이트 manifest URL
ADC_MODEL_HOME         모델 version/blob 저장 경로
ADC_MODEL_DIR          특정 모델 디렉터리 강제 지정
ADC_RESEARCH_MODE=1    설치 모델 대신 연구 cache 사용
```

일반 배포 URL은 HTTPS만 허용한다. updater 테스트는 명시적인 `allow_local=True`에서만 loopback HTTP 서버를 사용한다.

## 검증 명령

```bash
.venv/bin/python -m pytest tests/test_model_updates.py tests/test_terminal_layout.py tests/test_ml_recommender.py -k 'not full_build' -q
bash -n install.sh
```

모델 export는 별도로 legacy checkpoint와 동일 입력의 예측을 비교한다. 실제 공개 후에는 임시 설치 경로에서 설치, 캐시 재사용, 모델 업데이트 및 실행을 확인한다. Windows native 패키징은 이번 범위에 포함하지 않는다.

### 0.1 공개 검증

[검증 기록](../artifacts/distribution/verification-2026-10-12.json)에 실제 Release와 설치 결과를 기록했다. GitHub Actions에서 96개가 통과했고, 비공개 원본 및 모델 환경이 필요한 30개는 skip됐다. 로컬 회귀 검사는 125개와 별도 full portable parity 검사 1개가 통과했다.

공개 `curl` 설치는 모델 17개를 받았고, 반복 업데이트는 다운로드 0개와 재사용 17개였다. 설치된 CPU 앱의 실제 질환 분석 출력이 배포 전 CPU 출력과 같았으며, 실제 터미널에서 `U` 진입, 업데이트 완료, 질환 선택 화면 복귀를 확인했다. 변환 전후 세 질환의 모델 예측 최대 절대 오차는 0이고 MONDO 연결도 같았다. 이는 배포 동작과 수치 보존 검증이며 새 모델의 정확도 개선 결과는 아니다.
