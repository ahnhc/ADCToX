# ADCTOX

[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04%2B-E95420?logo=ubuntu&logoColor=white)](docs/INSTALL.md)
[![Release](https://img.shields.io/github/v/release/ahnhc/ADCToX)](https://github.com/ahnhc/ADCToX/releases)
[![Checks](https://github.com/ahnhc/ADCToX/actions/workflows/terminal.yml/badge.svg)](https://github.com/ahnhc/ADCToX/actions/workflows/terminal.yml)

기저질환과 검사값을 입력하고, AI 장기 분석과 의약품 라벨 근거로 기존 ADC를 비교하는 터미널 애플리케이션입니다.

BioLORD와 SapBERT로 질환을 해석하고, FinnGen 자료로 학습한 MLP ensemble로 장기 취약성을 추정합니다. 결과에서는 환자의 장기 우선순위, 라벨 사용 제한, 관련 경고와 필요한 검사값을 확인할 수 있습니다.

연구용 프로토타입입니다. 장기 추정값은 독성 발생 확률이 아니며, 새로운 ADC 조합의 안전성은 검증되지 않았습니다.

<p align="center">
  <img src="artifacts/terminal-captures/ui-v0.0/04-results.png" alt="ADCTOX terminal results" width="850">
</p>

## Get started

Ubuntu 24.04 이상, Python 3.12 이상에서 설치합니다.

```bash
curl -fsSL https://raw.githubusercontent.com/ahnhc/ADCToX/main/install.sh | bash
```

설치가 끝나면 실행합니다.

```bash
adctox
```

처음에는 CPU 추론 환경과 약 972 MiB의 모델 파일을 받습니다. 설치 후 질환 분석은 로컬에서 실행됩니다. 모델 업데이트를 확인하거나 다운로드할 때만 인터넷이 필요합니다.

`adctox` 명령이 보이지 않으면 `~/.local/bin`을 PATH에 추가합니다. 설치 경로 변경, GPU 환경, 삭제 방법은 [설치 안내](docs/INSTALL.md)를 참고하세요.

Windows에서는 Ubuntu용 파일을 다운로드할 수 있습니다. 실행은 WSL의 Ubuntu에서 위 설치 명령을 사용합니다.

```powershell
curl.exe -fL https://github.com/ahnhc/ADCToX/releases/latest/download/adctox-ubuntu.tar.gz -o adctox-ubuntu.tar.gz
```

## Model updates

기저질환 선택 화면에서 **U**를 누르고 **업데이트**를 선택합니다. 터미널 명령으로도 가능합니다.

```bash
adctox --check-models
adctox --update-models
```

앱과 모델은 별도 버전으로 관리합니다. MLP 가중치만 바뀌면 그 파일만 받고, 변하지 않은 BioLORD, SapBERT, MONDO 파일은 재사용합니다. SHA256과 호환성을 확인한 뒤 전체 모델 묶음을 전환하며 이전 모델로 복원할 수 있습니다.

```bash
adctox --version
adctox --model-version
adctox --rollback-models
```

앱 자체를 업데이트할 때는 설치 명령을 다시 실행합니다. [변경 기록](CHANGELOG.md)과 [배포 구조](docs/DISTRIBUTION.md)에서 자세한 내용을 확인할 수 있습니다.

## Research

질환의 관련 장기를 찾는 일, 미래 장기 취약성을 추정하는 일, ADC 독성을 예측하는 일을 구분해 평가합니다. 기존 baseline 비교와 성공하지 못한 실험도 함께 공개합니다.

- [현재 구현과 연구 결과](ml/docs/research_status_2026-10-12.md)
- [모델 정확도 개선 및 fine-tuning 계획](ml/docs/model_accuracy_plan_2026-10-12.md)
- [Fable 검토 요청서](ml/docs/fable_review_2026-10-12.md)
- [실험 결과](ml/results/), [기존 구조 모델 카드](docs/MODEL_CARD.md)
- [초기 설계 연구 개요](docs/LEGACY_RESEARCH_OVERVIEW.md)

향후 기존 항체, 링커, payload의 새로운 조합을 탐색하는 단계를 연결할 계획입니다. 현재 배포의 중심은 기존 ADC의 라벨 근거 비교입니다.

## Development

```bash
git clone https://github.com/ahnhc/ADCToX.git
cd ADCToX
```

모델 업데이트와 터미널 테스트, 배포 준비 방법은 [개발 및 배포 안내](docs/DISTRIBUTION.md)에 있습니다. 원본 워크북, 학습 캐시, 모델 가중치는 Git 이력에 넣지 않습니다. 기본 encoder와 MONDO의 출처 및 조건은 [Third-party notices](THIRD_PARTY_NOTICES.md)에 정리했습니다.

문제는 [GitHub Issues](https://github.com/ahnhc/ADCToX/issues)에 남겨주세요.
