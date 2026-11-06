# ml/

ADCTOX 앱과 모델 코드가 있는 폴더다. 앱은 환자의 기저질환과 검사값을 받아 승인된 ADC를 라벨 근거 순서로 보여준다.
앱(0.5.0 이상)이 쓰는 판정 모델은 처음부터 학습한 `ScratchJudge/`(모델 0.7과 0.8은 x2te, 모델 0.9는 rfb8)이고, 문서는 [docs/scratch_model.md](docs/scratch_model.md)다. 그 전의 Gemma 판정 모델(모델 0.5, 0.6)은 [docs/gemma_judge.md](docs/gemma_judge.md)에 있다.
- 처음부터 만든 모델: [docs/scratch_model.md](docs/scratch_model.md)
- 전체 흐름: [docs/overview.md](docs/overview.md)
- Gemma, encoder 탐색: [docs/sweep_1027.md](docs/sweep_1027.md)
- 장기 라벨 v5: [docs/relabel_v5_plan.md](docs/relabel_v5_plan.md)

## 주요 모듈

| 파일 | 역할 |
|---|---|
| `recommend.py` | 앱 진입점. 기저질환과 lab 값을 받아 ADC를 label restriction → boxed warning → W&P 순으로 정렬한다 |
| `form.py` | 한 화면 입력 UI. 질환 선택, lab 값, 질환 간 우선순위를 단계별로 받는다. ESC는 한 단계 뒤로 |
| `tui.py` | curses 메뉴(화살표 radio list, 검색 checklist) |
| `webapp.py` | `adctox --web`: 같은 다섯 단계를 브라우저에서. 127.0.0.1의 빈 포트(`ADCTOX_PORT`가 있으면 그 포트)에 stdlib HTTP 서버를 띄우고 `ml/web/`(index.html, app.css, app.js, 글꼴 AnthropicSansText-Light.otf와 PretendardVariable.woff2, mock.js는 개발용 fixture라 배포에서 빠진다)를 내보낸다. 서버에는 아무것도 남지 않는다 |
| `term.py` | curses가 없거나 한글 폭이 틀리는 환경(Windows)에서 쓰는 ANSI 대체 구현 |
| `suggest.py` | 입력 화면 검색. 철자 검색(한국어 초성 포함), 판정 모델의 가까운 개념 이름, 증상, 문장 → 질환 검색 |
| `mondo_index.py` | MONDO 이름 색인. 앱은 이름, 장기, 한국어 KCD 이름만 읽는다. 연구용 SapBERT linker(THETA 0.75)도 여기 있다 |
| `scratch_runtime.py` | 앱에서 처음부터 학습한 판정 모델(`ScratchJudge/`)을 실행한다(CPU 또는 GPU) |
| `scratch_export.py` | 처음부터 학습한 모델(`scratch_judge.py`의 모델과 기록 읽기 판정 표)을 앱용 `ScratchJudge/` 묶음으로 내보낸다 |
| `evidence_judge.py` | 처음 보는 질환을 이름 대신 MONDO 기록(정의, 상위 개념, 증상)으로 판정한다. 결과는 `concepts.json`에 미리 계산된다 |
| `gemma_runtime.py` | 양자화된 Gemma 판정 모델 실행(연구 비교 기준, `bench_judge.py`). 앱은 쓰지 않는다 |
| `gemma_judge2.py` | Gemma 4 E2B 판정 모델 학습. 출력 4종: organ, valid, align(MONDO 연결), sym(증상 → 질환) |
| `gemma_export.py` | 학습한 판정 모델을 LoRA 병합, 18층, int8로 내보낸다 |
| `eval_a4.py` | 배포 파이프라인(registry → MONDO → judge)을 영어, 한국어 gold query로 평가한다 |
| `eval_symptoms.py` | 증상, 문장 검색을 합성 평가 세트로 평가한다 |
| `build_portable.py` | 한 파일짜리 실행본(`dist/adc_recommender.py`, `--full`은 언어 모델 포함)을 만든다 |
| `build_cancer_mondo.py` | MONDO 암 용어 → 라벨 적응증 암종 표(`data/curated/competition/cancer_mondo.json`)를 만든다 |
| `build_trial_ae.py` | ADC 15종 주요 임상시험 32건의 ClinicalTrials.gov 결과를 장기별 이상반응 표(`data/curated/competition/trial_ae.json`)로 만든다. 임상시험과 arm은 `adc_trials.csv` |

보조 모듈:

- `restrictions.py`, `labs.py`, `drug_evidence.py`: label restriction 판정, lab 값 변환, 라벨의 장기별 근거.
- `adc_paths.py`, `adc_runtime.py`, `adc_updates.py`, `adc_version.py`: 경로, 모델 번들 찾기, 업데이트, 버전.
- `validate_*.py`: FAERS, JADER, subgroup 등 외부 검증. 계획은 [docs/validation_plan.md](docs/validation_plan.md).
- 나머지 `lab*.py`, `task_*.py`, `sapbert_ft_*.py`, `vulnerability_model.py` 등은 이전 연구 코드다.

## 연구 스크립트

전체 흐름은 [docs/overview.md](docs/overview.md)에 있다.

| 파일 | 역할 |
|---|---|
| `reproduce_judge.py` | Gemma 판정 모델 학습부터 튜닝 안 한 Gemma와의 비교 보고서까지 한 번에 실행 ([docs/reproduce.md](docs/reproduce.md)) |
| `bench_judge.py` | gold 벤치마크(처음 보는 질환) 채점 |
| `known_eval.py` | known 벤치마크(아는 질환, 새 표현) 만들기와 채점 |
| `gold_v1.py` | gold를 v5 기준으로 다시 라벨링한 gold_v1 만들기, 저장된 결과 재채점 |
| `tuning_ledger.py` | 실행마다 기록 카드(`results/tuning/`)와 [docs/tuning_log.md](docs/tuning_log.md) 작성 |
| `relabel_v5.py`, `relabel_v5_codex.py`, `relabel_v5_gpt.py` | 장기 라벨 v5: GPT 3회 라벨링, 투표, 판정, 감사, 합치기 |
| `relabel_v5_1.py` | v5.1: involved 장기 재검토 결과 반영 |
| `codex_batch.py` | JSON 배치 폴더를 Codex(`codex exec`)로 처리하는 범용 실행기 |
| `scratch_judge.py` | 처음부터 만든 판정 모델(X 계열) 학습. `--backbone`으로 encoder 튜닝에도 쓴다 |
| `scratch_pretrain.py` | 처음부터 만든 모델의 MLM 사전학습(BERT 구조, 무작위 가중치, 여러 GPU 가능) |
| `distill_teacher.py` | 튜닝한 Gemma의 장기 확률을 증류용 teacher 파일로 저장 (모델 0.8까지의 학습에 썼고, 모델 0.9는 쓰지 않는다) |
| `umls_build.py`, `fetch_umls.sh` | UMLS 2026AA에서 학습용 이름 만들기(UMLS 원본과 결과는 저장소에 넣지 않음) |
| `fetch_pubmed.py` | 사전학습용 PubMed baseline 내려받기(저장소에 넣지 않음) |
| `judge_data.py` | Gemma가 아닌 판정 모델(`scratch_judge.py`)의 학습 데이터. `gemma_judge2.py`와 같은 출처, 필터에 같은 질환의 이름 쌍을 더한다 |
| `linking_models.py` | MONDO 개념, 장기 라벨 로더(`ADCTOX_LABELS`), gold 격리(`gold_held`) |
| `gpu_queue.py` | 작업 목록 파일을 GPU 여러 장에 나눠 실행하는 큐 |

## 실행

```bash
.venv/bin/python -I ml/recommend.py                 # 터미널 화면
.venv/bin/python -I ml/recommend.py --web           # 브라우저 화면
```

연구 스크립트는 `ADCTOX_CACHE`(모델 cache 폴더)와 `ADCTOX_REPO`를 읽는다(`adc_paths.py`).

## 테스트

```bash
.venv/bin/python -m pytest -q
```

## 결과와 기록

- 평가 결과 JSON: `results/`, 벤치마크는 `results/benchmarks/`.
- 이전 연구 기록(FinnGen 취약성 모델, BioLORD, 초기 추천기 설계): [docs/archive/ml_research_log.md](docs/archive/ml_research_log.md).
- 그 밖의 이전 문서 목록: [저장소의 docs/archive/README.md](../docs/archive/README.md).
