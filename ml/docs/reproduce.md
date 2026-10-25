# Gemma 판정 모델 재현: 튜닝 전후 비교

이 저장소의 파이프라인과 데이터로 Gemma 4 E2B를 튜닝하고, 튜닝하지 않은 Gemma와 같은 문제로 비교한다. 명령 하나로 끝난다.

## 필요한 것

- GPU 1장 이상(24 GB면 충분). 학습 1회 약 25분, seed 3개면 GPU 2장으로 약 1시간 반.
- Hugging Face에서 `google/gemma-4-E2B`를 받을 권한(Gemma 이용 약관 동의).
- 모델 캐시의 **복사본**: `adctox --update-models`가 받는 폴더를 복사해서 쓴다. MONDO 색인과 장기 라벨 표가 들어 있다.
  - 실제 앱이 쓰는 폴더는 건드리지 않는다. 스크립트도 그 폴더를 거부한다.
- 이 저장소의 `data/curated/`. 학습 데이터와 평가 문제가 모두 들어 있다.
  - 예외: `data/curated/external/`의 말뭉치 언급(라이선스 때문에 저장소에 없음).
  - 없으면 그 출처 없이 학습하고, 카드에 "external 빠짐"으로 남는다.

## 실행

```bash
cp -rL ~/.local/share/adctox/models/current /data/me/work_cache     # Windows: %LOCALAPPDATA%\adctox\models\current
ADC_RESEARCH_MODE=1 python ml/reproduce_judge.py --work /data/me/work_cache --tag r1 \
    --stage "S1 한국어 이름 추가" --note "mondo_ko + ko2" --seeds 7,8,9 --gpus 0,1
```

한 번 실행하면 아래가 차례로 돈다.

1. **튜닝 안 한 Gemma 채점** (`ml/bench_judge.py --system base`). 같은 revision, 같은 문제면 이전 결과를 다시 쓴다.
2. **seed마다:**
   - 학습 전 검사(데이터 언어, 평가 문제 유출, 판정 충돌). 실패하면 멈춘다.
   - 학습(`ml/gemma_judge2.py`), int8 내보내기(`ml/gemma_export.py`).
   - 단일 모델 채점(`--system single`). `--app`을 주면 앱 전체 파이프라인도 채점한다.
3. **보고서** `ml/results/reproduce/<tag>.md`:
   - base 대비 영어·한국어 장기 F1과 paired bootstrap 95% 구간.
   - 장기 13개 각각의 F1과 목표(0.95) 달성 여부.
   - 개념 정답률, 무효 입력 수락률.
4. **학습 기록** `ml/docs/tuning_log.md`를 다시 만든다. 실행마다 쓴 데이터 파일(행 수, sha256), 설정, 직전 실행 대비 바뀐 것, 점수가 남는다.

## 데이터 출처 빼 보기 (ablation)

`--drop`으로 출처를 뺀다. 출처 이름은 다음 중에서 고른다.

| 출처 | 내용 |
|---|---|
| `mondo_names` | MONDO 이름·동의어 |
| `train_queries` | 검토한 입력 예 |
| `external` | 말뭉치 언급 |
| `profiles` | 질환 프로필 |
| `kcd` | HIRA KCD 한국어 이름 |
| `gen_ko` | 한국어 표현 1차 |
| `gen_sym` | 증상 문장 |
| `mondo_ko` | 검토한 MONDO 한국어 이름 |
| `ko2` | 한국어 일상어·약어·오타 |
| `kotypo` | 규칙 기반 한국어 오타 (`ml/ko_typos.py`) |
| `ko3` | 한국어 짧은 말·약어·한영 혼합 (`ml/ko3_batches.py`) |
| `umls` | UMLS 이름·약어 (`ml/umls_build.py`, 라이선스 필요, 없으면 자동으로 빠짐) |

예: `--drop mondo_ko,ko2 --compare-to r1s7`이면 한국어 이름 데이터가 얼마나 기여했는지 나온다.

## 한영 일관성 학습

`--consist 1.0`을 주면 한국어 학습 텍스트마다 같은 개념의 영어 MONDO 이름을 짝지어, 한국어 출력이 영어 출력을 따르게 한다. 기본값은 0(끔)이다. 결과는 `ml/docs/data_inventory.md` 6절에 있다.

## 평가 문제

- **gold 600개(영어):** 두 명이 각각 라벨을 달고 합의했다. 장기별 두 사람의 일치도는 0.94~1.00, 평균 0.98이다.
- **같은 600개의 한국어판.**
- **분할:** dev와 test는 질의 묶음 단위로 반씩 나눈다. 튜닝 중에는 dev만 보고, test는 마지막에 한 번만 본다.
- **격리:** gold 개념과 그 상하위 개념은 학습 목표에서 빠진다. 평가 문제와 같은 텍스트가 정답 개념과 함께 학습에 들어가면 학습 전 검사가 멈춘다.
- **증상 설명 검색:** 점수는 남기지만 목표에서 뺐다. 프로필 문장 구조상 과적합되기 쉽다.

## 목표

- 장기 13개 각각 F1 0.95 이상, 영어와 한국어 모두.
- 무효 입력 수락 0.

장기별 dev 양성은 9~85개뿐이라 한두 개 차이로 0.05씩 움직인다. 그래서 seed 평균으로 보고, 최종은 test 한 번으로 판정한다.
