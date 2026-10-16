# ADCTOX 모델 검토, 구현 최적화, 파인튜닝 여지 조사

작성: 2026-10-12. 대상: [연구 현황](research_status_2026-10-12.md), [모델 개선 계획](model_accuracy_plan_2026-10-12.md), 현재 working tree 코드.

이 문서는 세 가지 작업의 결과다.

1. 세션 정리 문서를 코드와 데이터에 대조한 검토.
2. 추론 경로 최적화와 그 전후 측정.
3. Sonnet 서브에이전트로 라벨링한 질환 연결 pilot gold를 만들고, 그것과 FinnGen 재평가로 파인튜닝 여지를 찾은 실험.

모든 수치는 아래 결과 파일에서 왔다. 새 모델은 제품에 배포하지 않았다.

| 결과 | 파일 |
|---|---|
| 속도 전후 | `ml/results/benchmarks/runtime_{before,after}_{cuda,cpu}.json` |
| 질환 연결(Task A) | `ml/results/benchmarks/linking_v0.json`, `linking_headroom_v0.json`, `sapbert_ft_pilot_v0.json` |
| FinnGen 취약성(Task B) | `ml/results/benchmarks/vuln_sel_v1.json` (fold seed 0,1,2), `vuln_sel_v0.json` (seed 0, spread 보정 전) |
| Pilot gold | `data/curated/disease_linking/` (`gold_v0.jsonl`, `ANNOTATION_GUIDE.md`, `annot/`, `raw/`) |

## 1. 요약

- **구현 최적화:** 질의 처리 시간(모델이 이미 로드된 새 질의 기준)이 GPU에서 1.99 s → 0.036 s, CPU에서 1.62 s → 0.12 s로 줄었다. Peak RSS는 GPU 실행에서 3.9 GB → 2.3 GB, CPU 실행에서 5.1 GB → 2.1 GB로 줄었다. 40개 질의의 장기, 추정값, ADC 순서는 변경 전과 **완전히 동일**하다. Cold start는 개선되지 않았다.
- **Auto 0.25와 반영 0.5는 ADC 순서가 같다.** 무의미한 문자열도 장기 추정을 받아 순서를 바꾼다. Pilot gold에서 auto fallback은 무효 입력의 100%, 모호 입력의 100%를 받아들이고 장기 macro-F1을 0.050 낮췄다 [−0.116, −0.009].
- **질환 연결 오류의 최대 원인은 encoder가 아니라 MONDO → 장기 crosswalk다.** SapBERT가 개념을 맞힌 경우의 37%에서 장기가 틀렸다. 완벽한 crosswalk를 가정한 상한은 macro-F1 +0.17이고, 완벽한 rerank와 threshold 보정의 상한은 +0.09다.
- **SapBERT 파인튜닝 pilot**은 recall@1 0.708 → 0.733, macro-F1 +0.019 [−0.011, +0.046]이었다. 방향은 양수지만 CI가 0을 포함한다.
- **FinnGen 모델은 연구 지표와 제품 출력이 다른 것을 측정하고 있었다.** 기존 지표(관측 칸 organ ρ)로 MLP는 0.738이지만, 터미널이 실제로 보여주는 severity로 같은 정답을 비교하면 0.251이다. 제품의 목표값(축별 excess)을 직접 학습하는 head는 이를 **0.358로 올렸다 [+0.067, +0.129]**. 이번 조사에서 가장 분명한 학습 개선 여지다.

## 2. 코드 대조에서 확인한 문제

### P0-1. 미매핑 입력 반영 계수는 순서에 영향이 없고, 무의미한 입력도 통과한다

`recommend()`의 정렬 키(`ml/recommend.py`의 `rows.sort`)는 장기 값이 0보다 큰지만 쓰고 크기는 쓰지 않는다. 계수가 실제로 바꾸는 것은 `f*lv >= 0.01` 컷과 표시 값뿐이다. 실제 모델로 `lung hole`, `lung hole + cirrhosis`, `xqzv blorp`를 0.25와 0.5로 실행하면 ADC 순서가 모두 같았다. `xqzv blorp`는 ocular/dermatologic/otologic 추정을 받아 순서를 바꿨다.

Pilot gold 평가(§5)에서 A4f(현재 기본 동작인 auto fallback)는 다음과 같았다.

- 무효 입력 30개, 모호 입력 51개를 모두 받아들였다.
- 유효 입력의 coverage는 100%가 되었지만, 장기 macro-F1은 fallback이 없는 A4보다 0.050 낮았다.

→ 권고: 미매핑 입력의 기본값을 `반영 안함`으로 둔다. 선택지는 `포함 / 미포함`으로 정리하고, 학습 prior와의 유사도 같은 validity gate를 통과한 경우에만 포함을 제안한다. 계수 비교 실험(계획 §3C)은 삭제한다.

### P0-2. FinnGen 학습 자료는 선택된 일부 쌍이고, 제품은 나머지로 외삽한다

- 자료에는 가능한 prior–outcome 쌍 중 일부만 있고, 대부분 유의한 쌍이다. 구체적인 수는 FinnGen 이용 조건 때문에 적지 않는다.
- `vulnerability_model.predict()`는 outcome **전체** 평균으로 장기 값을 만든다.
- §6의 재평가로 이 차이가 실제 성능 차이임을 확인했다.

### P0-3. "미관측 ICD family"는 FinnGen endpoint 접두어다

- `lab.load_rows()`의 정규식 `^([A-Za-z]+\d*)`가 endpoint 접두어로 그룹을 만든다. 장 단위 그룹도 있고, 접두어가 없는 endpoint는 단독 그룹이 된다.
- 발표에서는 "FinnGen 범주 접두어 holdout"이라고 써야 한다.
- 개념 기준 split(ICD-10/MONDO 매핑 또는 임베딩 클러스터)을 추가해야 한다.

### P1

- **MONDO 인덱스에 비인간 동물 질환이 들어 있다.** 예: `iron deficiency anemia, non-human animal`. Pilot 유효 질의의 3.7%에서 SapBERT top-1이 비인간 개념이었고, 시스템 top-10 후보에는 서로 다른 비인간 개념 599개가 나타났다. 인덱스 빌드에서 제외해야 한다(데이터 수정, 학습 불필요).
- **domain one-hot 누락**은 문서대로 확인했다(`[:, :nl+nd]`가 lag 블록만 남김). outcome 텍스트 임베딩이 domain 정보를 이미 담고 있어 재학습의 기대 효과는 낮다. 우선순위를 낮춘다.
- `predict()`가 lag 자리에 outcome index를 넘기지만, `TwoTower.forward`가 그 인수를 쓰지 않아 영향은 없다.
- 문서의 `resolve` 임계값(0.80/0.75/0.60), MONDO severity 0.80, 상위 3개 장기, TIER 순서, 정렬 키는 코드와 일치한다.

## 3. 구현 최적화

### 변경 내용

| 위치 | 이전 | 이후 |
|---|---|---|
| `mondo_index._embed` | 호출마다 SapBERT tokenizer와 모델을 새로 로드 | `(경로, 장치)`별로 한 번 로드(`_ENC`) |
| `mondo_index.link` | 호출마다 npz에서 101k×768 행렬을 다시 읽고 float32로 변환한 뒤 numpy matmul | 한 번 읽어 장치에 float32 tensor로 유지(`_IDX_E`), torch matmul |
| `vulnerability_model._st` | 호출마다 SentenceTransformer 생성 | 한 번 생성(`_ST`). 텍스트별 임베딩 캐시(`_EMB`, 최대 4096) |
| `vulnerability_model.predict` | 호출마다 checkpoint 로드. 텍스트 × lag × head마다 개별 forward | ensemble을 한 번 로드(`_CK`). head마다 한 번의 batch forward |
| `recommend._free_info` | 질의마다 registry 41개 이름을 다시 임베딩. registry 검색과 MLP가 같은 텍스트를 따로 임베딩 | registry는 프로세스당 한 번. 자유 입력 임베딩은 두 단계가 공유 |
| `recommend.recommend` | 호출마다 라벨 HTML 14개 파싱과 rule YAML 로드 | 프로세스당 한 번(`_evidence()`, 반환은 deepcopy) |
| `recommend.clear_model_cache` | MONDO 인덱스만 초기화 | 모델 업데이트 시 encoder, 인덱스 행렬, ensemble, 임베딩 캐시까지 초기화 |
| `build_portable.runtime_modules` | `_st`, `predict`, `_embed`, `link`만 추출 | 새 helper와 캐시 전역도 추출 |

자유 입력은 registry 이름과 **다른 batch**에서 임베딩한다. 같은 batch에 넣으면 fp16 padding 때문에 첫 질의의 추정값이 약 0.0015 달라졌다. 분리한 뒤에는 변경 전과 비트 단위로 같다.

### 측정

`ml/benchmark_runtime.py`가 마법사가 질의 하나에 하는 일(`analyze_conditions` + auto fallback `recommend`)을 측정한다. 질의는 40개, cold start는 3회다. GPU는 RTX 4090 1장, CPU는 24 thread다.

| 조건 | GPU 이전 | GPU 이후 | CPU 이전 | CPU 이후 |
|---|---:|---:|---:|---:|
| Cold start 첫 질의 p50 | 7.72 s | 7.66 s | 6.47 s | 7.17 s |
| 새 질의(모델 로드 후) p50 | 1.987 s | **0.036 s** | 1.624 s | **0.118 s** |
| 새 질의 p95 | 2.504 s | 0.042 s | 2.069 s | 0.184 s |
| 캐시 재조회 p50 | 0.270 s | 0.010 s | 0.278 s | 0.007 s |
| Peak RSS | 3,875 MB | 2,314 MB | 5,129 MB | 2,071 MB |
| Peak VRAM(PyTorch 할당) | 2,853 MB | 984 MB | - | - |
| 출력 불일치(40개 질의) | | 0 | | 0 |

- Cold start는 개선하지 못했다. CPU는 0.7 s 느려졌는데, 3회 측정의 변동인지 인덱스를 장치 tensor로 올리는 비용인지는 구분하지 못했다.
- 공유 서버라 다른 사용자의 부하가 섞였을 수 있다. 각 조건은 한 번씩만 실행했다.
- 테스트: `tests/test_terminal_layout.py`, `tests/test_ml_recommender.py`, `tests/test_model_updates.py`가 125 passed, 1 skipped. full build의 서버 출력 일치 테스트도 1 passed.

## 4. 질환 연결 pilot gold

### 만든 과정

1. **질의 작성(Sonnet 1개):** 종양 환자에게 흔한 동반질환 100개 개념을 13축에 분산하고, 개념마다 canonical/synonym/abbrev/typo/lay 표현 5개를 썼다. 여기에 모호 입력 40개, 비질환 30개, 무효 입력 30개를 더해 총 600개다. 작성자는 장기나 ID를 붙이지 않았다.
2. **후보 pool(`ml/build_linking_pools.py`):** SapBERT top-8, BioLORD top-5, 문자 TF-IDF top-8, 작성자 의도 개념의 합집합(평균 15.8개)을 섞어 보여주었다. 의도 개념은 600개 모두 MONDO에서 찾았다.
3. **독립 판독(Sonnet 8개 = 4 shard × 2명):** 판독자는 질의와 섞인 후보만 보고 validity, 허용 개념, 장기를 붙였다. 의도 개념, 시스템 출력, crosswalk, 다른 판독자의 결과는 보지 못하게 했다. 장기는 임상 지식으로 판단하게 해서 crosswalk와의 순환을 피했다.
4. **조정(Sonnet 1개):** 불일치 45건을 지침에 따라 결정했다(`annot/adjudicated.jsonl`).

### 일치도와 최종 구성

| 항목 | 값 |
|---|---:|
| validity Cohen κ | 0.917 |
| 둘 다 valid일 때 개념 호환 | 98.9% |
| 둘 다 valid일 때 장기 집합 완전 일치 | 95.6% (Jaccard 0.978) |
| 불일치 → 조정 | 45 / 600 |
| 최종 validity | valid 482, ambiguous 51, non_disease 37, invalid 30 |

**해석 한계:** 두 판독자가 같은 모델이므로 오류가 상관되어 있고, 이 일치도는 사람 판독 간 신뢰도를 과대평가한다. 질의도 LLM이 썼으므로 실제 사용자 입력 분포와 다르다. 이 자료는 **LLM silver set**이며 expert gold가 아니다. 아래 수치는 방법 간 상대 비교와 오류 유형 파악용으로 쓰고, 임상 정확도로 인용하지 않는다. 임상의 판독은 최소한 test split 296개에 먼저 받는 것이 좋다.

## 5. Task A 결과: 질환 → 장기

개념 그룹을 해시로 dev 304 / test 296으로 나눴다. threshold는 dev에서 정하고 test로 보고한다. CI는 개념 그룹 bootstrap이다. 장기 macro-F1은 유효 질의 기준이며, 거절된 유효 질의는 빈 예측으로 센다.

| 시스템 | macro-F1 | 개념 정확도 | coverage | 무효 수용 | 모호 수용 |
|---|---:|---:|---:|---:|---:|
| A0 exact alias | 0.424 | 0.364 | 0.343 | 0.000 | 0.118 |
| A1 TF-IDF | 0.596 | 0.589 | 0.665 | 0.267 | 0.176 |
| A2 SapBERT θ=0.75 | 0.619 | 0.619 | 0.682 | 0.200 | 0.529 |
| A3 BioLORD (dev θ=0.825) | 0.601 | 0.597 | 0.628 | 0.000 | 0.529 |
| **A4 현행 `resolve()`** | **0.637** | - | 0.707 | 0.200 | 0.588 |
| A4f 현행 + auto fallback | 0.587 | - | 1.000 | 1.000 | 1.000 |
| A5 비인간 제외 + gate | 0.584 | 0.581 | 0.611 | 0.133 | 0.471 |

A4 대비 차이(test, macro-F1): A2 −0.018 [−0.034, −0.005], A5 −0.053 [−0.077, −0.029], A4f −0.050 [−0.116, −0.009].

**현행 `resolve()`가 가장 좋다.** 질의 유형별 test macro-F1(A4)은 canonical 0.776, synonym 0.711, abbrev 0.514, typo 0.538, lay 0.402다. canonical 이름도 0.78에 그치는 이유는 아래의 crosswalk 오류다.

### 오류 분해(SapBERT top-1, 유효 질의 466개 중 gold 개념이 있는 것)

| 유형 | 개수 | 해결 수단 |
|---|---:|---|
| top-1 정답 | 318 | |
| 그 중 장기 오류(crosswalk) | 117 | crosswalk 수정. 학습 불필요 |
| 그 중 0.75 미만이라 버려짐 | 26 | threshold 보정 또는 파인튜닝 |
| 정답이 top 2–10 안 | 78 | reranker 또는 파인튜닝 |
| 정답이 top-10 밖 | 70 | alias 및 약어 사전 확장 (lay 30, abbrev 21, typo 14) |

Crosswalk가 맞는 개념에 **추가로 붙이는** 장기는 GI 22, metabolic 22, musculoskeletal 21, neurologic 17 순이다. **빠뜨리는** 장기는 pulmonary 20, infectious_immune 18 순이고, crosswalk가 비어 있는 개념은 9건이다.

### Oracle 상한(test, A2 기준 0.619)

| 수정 | macro-F1 | 개념 정확도 |
|---|---:|---:|
| 완벽한 crosswalk | 0.785 | 0.619 |
| 완벽한 rerank top-10 | 0.621 | 0.661 |
| threshold 보정만 | 0.649 | 0.686 |
| rerank + threshold | 0.705 | 0.852 |
| 모두 | 0.908 | 0.852 |

### SapBERT 파인튜닝 pilot(`ml/sapbert_ft_pilot.py`)

- **학습 자료:** gold에 등장한 모든 개념과 그 직계 부모/자식 1,822개를 학습에서 제외했다. 나머지 24,216개 개념의 synonym 쌍과 합성 오타 쌍 88,761개를 썼다.
- **설정:** InfoNCE(batch 256, τ 0.05, lr 2e-5, 1 epoch, 346 step, 약 40 s) 한 가지만 실행했다. 인덱스는 파인튜닝한 모델로 다시 임베딩했다.

| test | recall@1 | recall@5 | recall@10 | macro-F1 | 개념 정확도 |
|---|---:|---:|---:|---:|---:|
| frozen (비인간 제외, dev θ 0.57) | 0.708 | 0.818 | 0.864 | 0.680 | 0.703 |
| fine-tuned (dev θ 0.53) | 0.733 | 0.831 | 0.886 | 0.699 | 0.733 |
| 차이 [95% CI] | | | | +0.019 [−0.011, +0.046] | +0.030 [−0.010, +0.071] |

- 방향은 양수지만 검정력이 부족하다. 사전학습 SapBERT가 이미 UMLS 동의어로 학습되었으므로 이득은 오타, 약어, 일상 표현 쪽에서 나올 가능성이 크다. 다음 시도에는 이런 표현의 학습 쌍(사람 검토 포함)이 필요하다.
- dev에서 F1만 최대화하면 θ가 0.53–0.57까지 내려가고, 무효 입력 60%와 모호 입력 100%를 받아들인다. **similarity threshold 하나로는 거절을 해결할 수 없다.** SapBERT θ별로 보면 0.75에서 개념 정밀도 0.833, coverage 0.758이지만 무효, 모호 입력의 44%를 받아들이고, 0.85에서도 22%를 받아들인다. 별도의 validity 분류기가 필요하다.

## 6. Task B 결과: FinnGen 장기 취약성

`ml/eval_vulnerability.py`는 각 방법이 test prior의 **전체 grid**(prior × outcome × lag)를 out-of-fold로 예측하게 한다. 접두어 family 5-fold, fold seed 0/1/2이며, baseline과 spread는 fold의 training 자료로만 계산한다. CI는 family bootstrap이다.

| 방법 | 관측 칸 organ ρ (lab.py 지표) | **제품 severity ρ** | 제품 top-3 일치 | null-fill ρ | presence AUROC |
|---|---:|---:|---:|---:|---:|
| lookup | 0.683 | −0.023 | 0.140 | 0.487 | 0.632 |
| BioLORD kNN | **0.749** | 0.150 | 0.271 | 0.514 | 0.630 |
| BioLORD MLP (배포 구조) | 0.738 | 0.251 | 0.244 | 0.448 | 0.571 |
| hurdle (MLP × P(관측)) | 0.562 | 0.087 | 0.134 | **0.665** | **0.900** |
| 축 kNN (제품 목표 직접) | - | 0.323 | 0.203 | - | - |
| **축 MLP (제품 목표 직접)** | - | **0.358** | **0.269** | - | - |

측정 잡음 상한(각 행의 CI로 정답을 다시 뽑았을 때의 관측 칸 ρ)은 0.915다.

### 지표 정의

- **관측 칸 ρ:** `lab.organ()`과 같다. 저장된 lab 결과(MLP 0.740, kNN 0.749)를 재현한다. MLP − kNN은 −0.011 [−0.027, +0.003]이다.
- **제품 severity ρ:** 터미널 계산을 그대로 따른다. 전체 outcome의 excess 평균을 spread로 나누고, 중앙값을 빼고, clip한다. 이를 같은 prior의 관측된 축별 excess(같은 spread로 나눔)와 Spearman으로 비교한다. 4개 이상 축이 관측된 prior만 포함한다.
- **null-fill ρ:** 관측되지 않은 쌍을 HR=1로 둔 민감도 분석이다.

### 해석

1. **연구 지표와 제품 출력의 괴리가 핵심 병목이다.** "organ ρ 0.74"는 관측된 8개 안팎의 outcome 안에서의 순위다. 제품처럼 outcome 전체로 집계하면 같은 정답과의 일치가 0.25로 떨어진다. 문서와 발표의 0.74를 제품 정확도로 쓰면 안 된다.
2. **제품 지표에서는 MLP가 kNN보다 낫다**(+0.100 [+0.054, +0.139]). 관측 칸 지표에서는 반대였다. 어느 방법을 쓸지는 어떤 지표를 일차로 쓰느냐에 달려 있다.
3. **제품의 축별 목표를 직접 학습하면 +0.099 [+0.067, +0.129]**다(축 MLP − 배포 MLP). 축 MLP는 축 kNN보다도 +0.035 [+0.015, +0.060] 높다. top-3 일치는 +0.026 [−0.007, +0.054]로 불확실하다.
4. **hurdle**은 어떤 outcome에 연관이 있는지는 잘 맞히지만(AUROC 0.90), 제품의 현재 정답 정의(관측 칸의 excess)에서는 나빠진다. "연관 여부까지 포함한 위험"을 제품 목표로 삼을지는 연구 질문의 선택이다. 목표를 바꾸면 hurdle 계열이 유리하다.
5. **상한까지 여유가 크다.** 관측 칸 ρ 0.75 대 잡음 상한 0.915. 다만 13축 중 관측되는 축이 적어 축별 정답 자체가 잡음이 크다.

## 7. 파인튜닝 여지: 결론과 우선순위

| 순위 | 대상 | 근거 | 예상 효과 | 학습 여부 |
|---|---|---|---|---|
| 1 | **FinnGen head를 제품 목표로 재학습**(축별 excess, 질환 내 순위). 다음 단계로 LoRA와 ranking loss | 축 MLP +0.099 [+0.067, +0.129] | 제품 severity ρ 0.25 → 0.36 이상 | 예. 공모전의 "직접 학습한 모델"에 직접 해당 |
| 2 | **MONDO → 장기 crosswalk 수정**과 비인간 개념 제거 | 맞힌 개념의 37%에서 장기 오류. oracle +0.17 | Task A의 가장 큰 단일 개선 | 아니오(데이터) |
| 3 | **validity gate**(무효, 모호 입력 분류기, 작은 head) | threshold로는 무효 수용 20–60%. auto fallback은 100% 수용 | 무효 입력이 순서를 바꾸는 문제 제거 | 예(작은 분류기) |
| 4 | **SapBERT 파인튜닝 + reranker** | pilot +0.019 [−0.011, +0.046]. oracle rerank+θ 상한 +0.09 | 오타, 약어, 일상 표현 개선 | 예. 사람이 검토한 쌍이 더 필요 |
| 5 | 약어와 일상 표현 alias 확장 | 정답이 top-10 밖인 70건(lay 30, abbrev 21) | 검색 coverage | 아니오(사전) |
| 뒤로 | domain one-hot 재학습, encoder bake-off 추가, MONDO feature 재시도 | 기존 null 결과. 정보 중복 | 낮음 | |

공모전에서 쓸 학습 모델은 1번(제품 목표 head)과 3번(validity gate)이 가설과 측정이 가장 분명하다. 4번은 사람 검토 자료가 늘어난 뒤 다시 시험한다.

## 8. 계획 문서에 반영할 수정

1. **Task B 일차 지표를 "제품 severity ρ"로 바꾼다.** 관측 칸 ρ는 보조 지표로 둔다. 문서에 0.74를 제품 정확도로 쓰지 않는다.
2. **§3C의 0/0.25/0.5 계수 비교를 삭제한다.** "포함 여부 + gate" 평가로 대체한다.
3. **A 과제 gold는 현재 LLM silver다.** 임상의 2인 판독은 test split부터 받는다. 실제 사용자 입력(로그 수집 동의 하에)으로 신규 test를 만든다.
4. **접두어 family split 명칭을 정정한다.** 개념 기준 split을 추가한다.
5. 선택 실험이 여러 번 쌓였다(이번에도 axis head, hurdle, FT pilot 3개). **다음 확인 실험은 후보 하나만 사전 등록**하고, 새 split seed와 새 gold에서 확인한다.

## 9. 재현 명령

```bash
cd <repo>; PY=<python env>/bin/python
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
# 속도: 변경 전 수치는 이 문서와 함께 저장된 runtime_before_*.json
CUDA_VISIBLE_DEVICES=1 $PY -I ml/benchmark_runtime.py --device cuda --out ml/results/benchmarks/runtime_after_cuda.json
$PY -I ml/benchmark_runtime.py --device cpu --out ml/results/benchmarks/runtime_after_cpu.json
# Task A
CUDA_VISIBLE_DEVICES=3 $PY -I ml/build_linking_pools.py          # 후보 pool과 판독 shard (판독 후 다시 실행하면 shard가 바뀜)
$PY -I ml/merge_linking_gold.py prepare && $PY -I ml/merge_linking_gold.py finalize
CUDA_VISIBLE_DEVICES=1 $PY -I ml/eval_linking.py [--refresh]
$PY -I ml/linking_headroom.py
CUDA_VISIBLE_DEVICES=3 $PY -I ml/sapbert_ft_pilot.py
# Task B
CUDA_VISIBLE_DEVICES=2 $PY -I ml/eval_vulnerability.py --name sel_v1 --seeds 0,1,2
```

SapBERT 파인튜닝 체크포인트는 `$ADCTOX_CACHE/sapbert_ft_pilot/`에 있으며 배포 경로와 연결하지 않았다.

## 10. 확인하지 못한 것

- Gold는 같은 모델의 두 인스턴스가 판독한 silver set이다. 사람 판독과의 일치도는 측정하지 않았다.
- FinnGen 원 추출 기준(top-N인지 유의성 필터인지)은 데이터 분포에서 추정한 것이다. 워크북 제공자에게 확인이 필요하다.
- 축 MLP, hurdle, SapBERT FT는 모두 선택 단계의 결과다. 확인용 split에서 재현하지 않았다.
- 속도는 공유 GPU 서버에서 각 조건을 한 번씩 측정한 값이다. 반복 측정 CI는 없다.

---

# 2차: 권장 우선순위 자동 반영 (2026-10-12 오후)

§7의 우선순위 1–4를 코드와 모델에 반영했다. 사람 검토 대신 **Claude Haiku 에이전트 30개**를 정해진 틀로 라벨링에 썼다. 모든 학습에서 pilot gold의 개념과 그 부모, 자식 개념(1,822개)은 제외했다. Gold는 평가에만 썼다.

## 결과 요약

| 우선순위 | 반영 내용 | 판정 기준과 결과 | 제품 적용 |
|---|---|---|---|
| 1. FinnGen head를 제품 목표로 재학습 | 축별 excess를 직접 예측하는 axis MLP 5개를 `vuln_biolord.pt`에 추가(`axis`) | 사전 등록 기준: 새 fold seed 100/101/102에서 배포 MLP 대비 제품 severity ρ의 CI 하한 > 0. 결과 **+0.107 [+0.073, +0.139]**, top-3 일치 +0.048 [+0.020, +0.073] → **통과** | 적용 |
| 2. MONDO → 장기 crosswalk 수정 | Haiku 라벨로 학습한 개념 → 장기 모델(SapBERT 임베딩 + 기존 crosswalk + ancestor multi-hot, 축별 logistic). 비인간 개념 5,575행 제거 | gold test 개념 수준 장기 완전 일치: crosswalk 0.578 → 학습 모델 0.651, **+0.072 [−0.023, +0.176]**. 파이프라인 macro-F1 +0.009 [−0.039, +0.055] → **미확정** | 적용(방향 일치, 악화 근거 없음). 이전 인덱스는 `mondo_index.pre_v1.npz`로 보존 |
| 3. Validity gate | SapBERT 질의 임베딩 + top-1/margin + 문자 통계의 logistic 분류기를 `mondo_index.npz`에 탑재. `자동` fallback과 MONDO 연결에 적용 | gold test에서 유효 질환 통과 92.9%, **무효 입력 통과 0%**(threshold만 쓰면 60%), 모호, 비질환 통과 47.6%. AUROC 0.878 | 적용 |
| 4. SapBERT 파인튜닝 2차 | MONDO 쌍 + 검토 통과 질의 1,783개 + NCBI Disease 학습 mention 3,376개 | 사전 등록 기준: gold test macro-F1 CI 하한 > 0. 결과 +0.020 [−0.008, +0.050], 개념 정확도 +0.034 [−0.005, +0.074], **NCBI test recall@1 +0.013 [0.000, +0.028]** → **기준 미달** | 미적용. 체크포인트는 `ml_cache/sapbert_ft_v2/` |

### 전체 파이프라인 변화 (gold test, 개념 그룹 bootstrap)

| | macro-F1 | coverage | 무효 입력 수용 | 모호 입력 수용 |
|---|---:|---:|---:|---:|
| 이전 `resolve()` | 0.637 | 0.707 | 0.200 | 0.588 |
| **현재 `resolve()`** | **0.651** | 0.703 | **0.000** | 0.529 |
| 이전 + `자동` fallback | 0.587 | 1.000 | 1.000 | 1.000 |
| **현재 + `자동` fallback** | 0.599 | 0.937 | **0.000** | 0.765 |

- macro-F1 차이는 +0.013 [−0.038, +0.062]로 확정되지 않았다.
- **확정된 개선은 무효 입력 차단이다.** `xqzv blorp`, `banana`가 더 이상 장기 추정을 받지 않는다.
- 모호 입력(`ms`, `pe` 등)의 수용률은 여전히 높다. 남은 과제다.

### 속도 (v1 모델, 같은 40개 질의)

| | GPU 이전 → v1 | CPU 이전 → v1 |
|---|---|---|
| 새 질의 p50 | 0.036 → 0.020 s | 0.118 → 0.105 s |
| Cold start 첫 질의 | 7.66 → 6.88 s | 7.17 → 6.31 s |
| Peak RSS | 2,314 → 2,350 MB | 2,071 → 2,117 MB |

axis head는 질의당 forward 1회로 끝나므로, 기존 TwoTower(질의당 772행)보다 가볍다.

## Haiku 라벨링 과정과 품질 관리

| 단계 | 에이전트 | 결과 |
|---|---:|---|
| 1차 개념 장기 라벨(4,000개, 16 batch, 20% 중복, batch당 calibration 10개) | 16 | **여러 에이전트가 지시와 달리 키워드 스크립트로 라벨을 만들었다**(`/tmp/label_*.py`). 중복 일치 51%, calibration 완전 일치 0.20–1.00 |
| 학습 질의 생성(개념 500개 × 4 + 비질환/무효 200개) | 5 | 2,200개, 중복 제거 후 2,051개. 일부 "lay"가 정식 명칭이고, 유효 약어가 모호로 표시되는 등 품질이 섞여 있음 |
| 엄격 재라벨(registry에 실제로 등장하는 개념 602개, 스크립트 금지, 이유 기재 필수, calibration + 중복) | 5 | calibration 0.80–1.00, **중복 일치 0.87** |
| 질의 검토(batch당 오답 함정 30개 삽입) | 4 | 함정 거부율 0.93–1.00. 네 batch 모두 사용 |

1차 batch는 미리 정한 규칙(calibration ≥ 0.9, 또는 독립 라벨 2개가 일치)을 통과한 것만 학습에 썼다. 최종 학습 라벨은 2,298개이고, 그중 엄격 라벨이 600개다. **이 라벨들은 기계 라벨이다.** 위 개선 수치는 같은 계열(Sonnet) gold에서의 비교이므로 임상 정확도로 인용하지 않는다.

## 코드 변경

- `ml/vulnerability_model.py`: `axis_net`, `axis_targets`, `train_axis()`, `--axis-only`. checkpoint에 `axis`가 있으면 `predict()`가 이를 쓴다. 이전 앱은 이 key를 무시한다.
- `ml/mondo_index.py`: `link()`가 `valid`(질환일 확률)와 `gate`를 반환한다. gate 가중치는 인덱스 파일에 들어 있고, 이전 인덱스에서는 `None`이 되어 이전처럼 동작한다.
- `ml/recommend.py`:
  - `AUTO_FALLBACK = 0.25`: `자동`은 gate를 통과한 입력에만 적용되고, `반영`은 사용자 강제로 항상 적용된다.
  - `GATE_MONDO = True`, `GATE_BORROW = False`: gold dev 기준으로 선택했다.
  - 안내 문구를 "자동은 질환으로 인식된 입력에만 반영합니다"로 바꿨다.
- `ml/build_portable.py`, `scripts/build_ubuntu_release.py`: full build가 새 함수를 추출하고, 릴리스가 axis head와 gate 배열을 포함하도록 했다. 업데이트 manifest의 `architecture`는 updater 호환을 위해 `biolord-twotower-v1`을 유지한다.
- 새 스크립트:
  - `ml/linking_models.py` (`organs` / `gate` / `index`)
  - `ml/sample_label_concepts.py`
  - `ml/build_external_linking.py`
  - `ml/sapbert_ft_v2.py`
- 테스트: `tests/test_terminal_layout.py`, `test_ml_recommender.py`(full build 포함), `test_model_updates.py` → 126 passed, 1 skipped.

**배포 상태:** 연구 캐시(`$ADCTOX_CACHE/`)와 이 저장소의 터미널에는 반영되었다. GitHub Release(모델 0.1)는 **공개 배포라서 실행하지 않았다.** `scripts/build_ubuntu_release.py --models --model-version 0.1`로 만들 수 있다. 되돌리려면 `vuln_biolord.pre_axis_2026-10-12.pt`, `mondo_index.pre_v1.npz`를 원래 이름으로 복사한다.

## 추가 데이터로 더 학습할 수 있는 것

| 데이터 | 해결하는 문제 | 접근 | 승인 필요 |
|---|---|---|---|
| **FinnGen/Risteys 전체 endpoint 쌍(선택 전) 결과** | Task B 최대 병목(학습 자료가 선택된 일부 쌍). 유의하지 않은 쌍까지 있으면 hurdle 없이 제품 목표를 직접 학습 가능 | 협업자 워크북의 원 추출 또는 Risteys R12 다운로드 | 협업자 확인, FinnGen 이용 조건 |
| **덴마크 disease trajectory(Jensen et al. 2014, 620만 명, ICD-10 쌍 RR)** | Task B의 **독립 코호트 외부 검증**. 현재는 같은 자료의 재분할뿐 | 논문 보충자료(공개) | 다운로드 승인 |
| HuDiNe(Hidalgo et al. 2009, Medicare ICD-9 쌍 RR/φ) | 전체 쌍이 있는 comorbidity network. selection 없는 사전학습 또는 검증 | 공개 | 다운로드 승인 |
| UK Biobank | 개인 단위 생존분석으로 목표값 자체를 새로 정의 | 기관 신청과 비용 | 신청 필요 |
| **COMETA(Reddit 일상 표현 2만 개 → SNOMED)** | Task A의 가장 약한 lay 표현(test F1 0.40) | 저자에게 데이터 이용 동의서 | 동의서 서명 |
| MedMentions, BC5CDR | 실제 텍스트 mention → 개념. NCBI처럼 MONDO xref로 매핑 | 공개 | 다운로드 승인 |
| **UMLS Metathesaurus와 SPECIALIST Lexicon 약어 목록(LRABR)** | 약어, 동의어 사전 확장(정답이 top-10 밖인 오류의 주원인). LRABR은 공개, UMLS는 NLM UTS 계정 필요 | NLM | UMLS: 본인 계정 승인 |
| KCD(한국표준질병사인분류) 한글 명칭 | 한국어 입력 지원(현재 영어만) | 통계청 공개 | 다운로드 승인 |
| 실제 사용자 입력 로그(동의 하) | 실제 입력 분포의 test set. 지금 gold는 LLM이 작성 | 앱 내 수집 | 사용자 동의 절차 |

**우선 권장 순서:** ① FinnGen 전체 쌍(협업자 문의) ② 덴마크 trajectory로 외부 검증 ③ UMLS/LRABR 약어 사전 ④ COMETA. ①–②는 Task B의 신뢰도, ③–④는 Task A의 약어, 일상 표현을 직접 겨냥한다.

---

# 3차: 사용자 테스트 피드백 반영 (2026-10-12 저녁)

## 1. 약어처럼 여러 질환으로 읽히는 입력 (`asd`)

**문제:** `asd`가 MONDO에서 atrial septal defect로 확정되었다. 사용자는 autism spectrum disorder를 의도했다.

**변경:**
- 인덱스 v2에 **NLM SPECIALIST Lexicon 약어표(LRABR, 2026)**를 넣었다.
  - LRABR 약어 23,132개의 확장어 100,826개를 SapBERT로 MONDO에 미리 연결했다(유사도 ≥ 0.92인 경우만 인정).
  - 그 결과 2,920개 약어가 질환 후보 목록을 갖는다. 후보는 PubMed 코퍼스(MedMentions + NCBI)에 많이 등장한 순으로 정렬한다.
- `mondo_index.link()`가 `readings`(가능한 해석)와 `ambiguous`를 함께 돌려준다. 해석이 생기는 경우는 두 가지다.
  - 약어 확장 후보
  - 1등과 유사도 차이가 0.02 이내인 근접 후보
- 해석들이 **서로 다른 장기**를 가리키면 분석 결과 화면에 `Other readings`가 표시된다. 다음 단계에서 다음 선택지를 묻는다.
  - **"'asd'은(는) 어떤 질환인가요?"**
  - 후보 질환들 / `다시 입력하기` / `모름 / 장기 미확인`
- 선택은 `recommend.CHOICE`에 저장된다. 이후 판정은 선택한 개념의 장기로 한다. 일반 텍스트 출력(`--plain`)에는 `other readings:`가 기록된다.
- `asd`의 후보: atrial septal defect, Alzheimer disease, autism spectrum disorder, anterior segment dysgenesis, adult-onset Still disease, acute stress disorder.
- 같은 방식으로 `ra`는 rheumatoid arthritis, `amnesia`는 dissociative amnesia(장기 축 없음)와 Memory impairment(신경)로 갈린다.

## 2. MONDO에 없는 증상, 소견 (`amnesia`, `sleep`)

**변경:** 인덱스 v2에 **HPO(Human Phenotype Ontology 2026-09-01)** 표현형 19,178개(42,417 문자열)를 추가했다. 장기는 HPO 최상위 가지에서 결정적으로 정한다(신경계 이상 → neurologic 등).

| 상황 | 동작 |
|---|---|
| 질환이 연결되지 않음 | 유사도 0.85 이상인 HPO 용어가 장기를 가지면 `Phenotype (HPO)`로 반영 |
| 장기 가지 밖의 용어(예: Fatigue)가 가장 가까움 | 반영하지 않음. 엉뚱한 이웃 용어로 넘어가지 않게 하기 위함 |
| MONDO 질환은 찾았지만 13축에 장기가 없음(PTSD, 우울증) | `Unmapped` 대신 `MONDO (no organ axis)`로 표시 |
| 장기 없는 질환과 장기 있는 증상이 함께 맞음(amnesia, depression) | 두 해석을 선택지로 제시 |

**사용자 관찰 "학습 모델이 neuro 0.5를 맞혔다"의 해석:** FinnGen 모델은 *그 질환이 있는 사람에게 이후 어떤 장기 질환이 많은가*를 추정한다. amnesia 같은 신경 증상에서 신경이 높게 나오는 것은 자연스럽다. 그러나 이것은 질환의 **소속 장기**와 다른 질문이다. 화면에서 `Mapped organs`(연결된 장기)와 `Model signal / Estimated organs`(학습 추정)를 계속 구분해 둔 이유다. 연결이 실패했을 때만 gate를 통과한 입력에 한해 추정을 쓴다.

## 3. 회귀 점검 (gold, 사용자 선택 없이 1등 해석 기준)

| | dev F1 | test F1 | test coverage | 무효 수용 | 모호 수용 |
|---|---:|---:|---:|---:|---:|
| v1 인덱스 | 0.715 | 0.651 | 0.703 | 0.000 | 0.529 |
| v2 인덱스 | 0.726 | 0.660 | 0.728 | 0.000 | 0.588 |

- v2 − v1 test F1은 +0.010 [−0.030, +0.028]로, 악화는 없다.
- 비질환(증상, 소견) 입력 28개의 장기 적중은 0.25 → 0.36이다.
- 선택 질문이 뜨는 입력은 68개다. 그중 gold가 모호로 본 것이 23개(모호 51개 중 45%)다. 유효 질환 482개 중 44개(9%)는 확인 질문을 한 번 더 받는다.

## 4. 모델 업데이트: 해시 비교로 변경 파일만

**이전 문제:** blob을 재사용할 때도 매번 전체 SHA256을 다시 계산했다(1 GB 가까이). 변경이 없어도 새 버전 디렉터리를 만들었다.

**변경 (`ml/adc_updates.py`):**
- 다운로드 시 해시로 검증한 blob은 `blobs/verified.json`에 (크기, mtime)으로 기록한다. 이후에는 둘이 같으면 재해시하지 않는다.
- 이 기록 이전에 설치된 blob은 크기가 맞으면 한 번만 편입한다. 이미 기록되었다가 크기나 mtime이 바뀐 blob은 손상으로 보고 다시 받는다.
- `plan()`이 받아야 할 파일과 용량을 해시 계산 없이 계산한다. 업데이트 화면에는 "변경 파일 N개 (X MiB)만 다운로드합니다", 또는 "최신 상태입니다. 다운로드할 파일이 없습니다"가 표시된다.
- 변경이 없으면 `install()`은 아무것도 받지 않고 새 디렉터리도 만들지 않는다.
- 전체 재검증은 `adctox --verify-models`로 따로 실행한다. 손상 파일은 기록에서 지워 다음 업데이트 때 다시 받는다.
- 테스트 2개를 추가해 `tests/test_model_updates.py`가 26 passed다.

## 5. 수집한 데이터 (`data/raw/DATASETS_2026-10-12.md`)

| 데이터 | 상태 | 쓰임 |
|---|---|---|
| SPECIALIST LRABR 2026 | 받음 | 약어 후보(이미 적용) |
| HPO 2026-09-01 | 받음 | 증상 → 장기(이미 적용) |
| MedMentions st21pv, BC5CDR, NCBI Disease, **COMETA**(Reddit 일상 표현) | 받음. MONDO로 매핑된 mention 32,421개(`data/curated/external/mentions_mondo.jsonl`). COMETA 2,951개 | 0.2 재학습 때 SapBERT 학습 쌍, 외부 test |
| 덴마크 DTB(Siggaard et al. 2020, ICD-10 쌍 77,294개), Jensen et al. 2014(유의한 쌍 4,014개) | 받음 | FinnGen 취약성 모델의 **독립 코호트 외부 검증** |
| HuDiNe(Medicare ICD-9, 전체 쌍 RR/φ) | 받음(Wayback 복구, 학술 목적만 허용) | 선택 편향 없는 comorbidity 사전학습, 검증 후보 |
| HIRA 상병마스터(KCD-8 기반 한, 영 명칭 47,798개) | 받음 | 한국어 입력 지원 |
| FinnGen/Risteys 전체 endpoint 쌍 | **공개 일괄 파일 없음** | endpoint별 CSV 버튼만 있음(약 2.7천 페이지). 전체 자료는 FinnGen sandbox 또는 신청 필요 |

라이선스 주의: HuDiNe는 학술 목적만 허용된다. COMETA의 SNOMED 라벨은 재배포 시 SNOMED 조건을 확인해야 한다. 둘 다 앱 번들에는 넣지 않고 학습과 평가에만 쓴다.

## 6. 0.2 재학습 계획 (사용자 확인 후 진행)

1. SapBERT 3차 학습. 학습 자료는 MONDO 쌍 + 검토된 질의 + 외부 4개 코퍼스의 train split(COMETA 포함)이다. 평가는 gold test와 각 코퍼스 test에서 한다. 배포 기준은 사전 등록한다: gold test F1의 CI 하한 > 0, 그리고 외부 test 2개 이상에서 악화 없음.
2. 덴마크 DTB로 FinnGen axis 모델을 외부 검증한다. ICD-10 쌍 → 질환 이름 → 축 excess로 바꿔 장기 순위 ρ를 계산한다. 결과에 따라 DTB를 추가 학습 자료로 쓸지 정한다.
3. 한국어 입력: HIRA 한, 영 명칭을 alias로 추가한다(한국어 gold는 별도).
4. 앱 버전 0.2, 모델 0.2 릴리스(공개 배포는 사용자 승인 후).

## 7. 주의: 자료가 적은 장기 축에서는 학습 추정을 믿기 어렵다

사용자 테스트에서 `amnesia`의 학습 추정이 이전 모델(Neuro 0.50)과 axis head(Ear 0.26, MSK 0.23)에서 크게 달랐다. FinnGen 학습 자료에서 neurologic, infectious_immune, otologic, musculoskeletal 축은 관측된 prior 질환이 다른 축보다 훨씬 적다. 구체적인 수는 원자료 이용 조건 때문에 적지 않는다.

해석:
- axis head의 개선(+0.107)은 주로 자료가 많은 축에서 나왔다. 신경, 면역, 귀, 근골격 축의 값은 사실상 학습 근거가 거의 없다.
- 이전 모델이 신경 질환에 Neuro를 높게 준 것도, 이 축의 자료에서 배운 것이라기보다 질환 이름과 outcome 이름의 텍스트 유사성에서 왔을 가능성이 크다.
- 두 모델 모두 이 축들에서는 검증되지 않았다.

비교용 설정: `ADC_VULN_HEAD=twotower`로 실행하면 이전 TwoTower ensemble 추정을 볼 수 있다(기본은 axis head).

0.2 재학습 제안:
- (a) 덴마크 DTB와 HuDiNe의 전체 쌍으로 희소 축(신경, 면역, 귀, 근골격)을 보강한다.
- (b) 축별 표본 수가 기준 미만이면 그 축의 추정은 화면에 "자료 부족"으로 표시하고, 자동 반영에서 제외한다.
- (c) 축별 성능을 따로 보고한다.

> 4차 반영(아래): (b)는 "자료 부족" 표시 대신 **빈칸 + 자동 반영 제외**로 바꾸었고, 기준은 표본 수가 아니라 축별 검증 결과다.

---

# 4차: 0.2 진행 (2026-10-12 밤)

## 1. 질환 확인 화면 정리

- 결과 화면의 긴 `Other readings` 줄을 한 줄로 줄였다: `다른 의미 N개, 다음 화면에서 선택`(이미 고른 경우 `직접 고른 의미, 다음 화면에서 바꿀 수 있음`).
- 질환마다 따로 뜨던 선택 화면을 **한 화면(`입력하신 질환 확인`)**으로 합쳤다. 입력별 제목 아래 후보가 radio로 정렬되고, 오른쪽 열에 장기, 증상(HPO)이면 `증상` 표시, 마지막에 `모름`. `다시 입력하기` 항목은 PgUp으로 대신한다.
- 기본 선택은 실제로 적용된 해석이다(예: `amnesia`는 Memory impairment). ENTER는 다음 입력의 현재 선택으로 이동하고 마지막에서 완료한다.
- 테스트: `tests/test_terminal_layout.py::test_meaning_choice_is_one_screen_...`

## 2. SapBERT 3차: 배포하지 않음

| | 내용 |
|---|---|
| 처음부터 vs 이어서 | 처음부터 학습은 SapBERT가 쓴 UMLS 동의어 약 400만 쌍이 필요해 불가능. 체크포인트에서 이어서 학습하고, **전체 층 vs 상위 4층만**을 1, 2 epoch씩 비교(4개) |
| 학습 쌍 | MONDO 쌍 + 검토 질의 1,783 + 외부 4개 코퍼스 train. 중복 제거 후 외부 코퍼스의 **고유 (개념, 표현) 쌍은 3,020개뿐**(NCBI 912, BC5CDR 421, MedMentions 1,394, COMETA 293). 3.2만 mention 대부분은 같은 흔한 표현의 반복이고, 흔한 질환은 gold 개념이라 학습에서 빠진다 |
| 선택(dev만) | frozen 0.684, full 1ep 0.681, full 2ep 0.682, top4 1ep 0.680, top4 2ep 0.682. **어느 변형도 frozen보다 낫지 않았고 전체 층과 일부 층의 차이도 없었다** |
| test(선택된 full 2ep, 1회) | gold macro-F1 +0.017 [−0.012, +0.044], 외부 recall@1 NCBI +0.007, BC5CDR +0.006, MedMentions +0.000, COMETA +0.013(모두 CI가 0 포함) |
| 판정 | 사전 기준(gold CI 하한 > 0) 미달. 3회 연속 같은 결론이므로 연결 오류의 원인은 encoder가 아니다. 체크포인트는 `ml_cache/sapbert_ft_v3/`(미배포) |

## 3. 학습 추정의 축별 검증과 빈칸 처리 (`ml/axis_reliability.py`)

규칙(실행 전 고정): 축은 (내부) FinnGen 코드 계열 보류 5-fold CV, 새 seed 200–202에서 축별 Spearman의 CI 하한 > 0이고, (외부) 덴마크 DTB(노출 818개, KCD 영문명으로 예측)에서 30개 이상일 때 ρ < 0이 아니면 표시한다. 아니면 **빈칸, 자동 반영 제외**.

| 축 | 내부 ρ [95% CI] (n) | DTB ρ [95% CI] (n) | 결과 |
|---|---|---|---|
| haematologic | +0.32 [+0.19, +0.43] (4074) | +0.44 [+0.36, +0.51] (409) | 표시 |
| **hepatic** | +0.69 [+0.51, +0.75] (1593) | **−0.07 [−0.20, +0.07]** (252) | **빈칸** |
| cardiovascular | +0.32 [+0.19, +0.46] | +0.13 [+0.06, +0.21] | 표시 |
| pulmonary | +0.35 [+0.24, +0.48] | +0.22 [+0.14, +0.29] | 표시 |
| renal | +0.39 [+0.29, +0.49] | +0.41 [+0.33, +0.49] | 표시 |
| gastrointestinal | +0.39 [+0.19, +0.55] (336) | +0.29 [+0.21, +0.36] | 표시 |
| neurologic | +0.32 [+0.15, +0.46] (276) | +0.15 [+0.06, +0.22] | 표시 |
| ocular | +0.59 [+0.42, +0.69] (318) | +0.38 [+0.30, +0.45] | 표시 |
| dermatologic | +0.43 [+0.28, +0.59] | +0.13 [+0.04, +0.21] | 표시 |
| metabolic_endocrine | +0.36 [+0.29, +0.43] | +0.10 [+0.03, +0.18] | 표시 |
| **musculoskeletal** | +0.47 **[−0.08, +0.76]** (57) | +0.35 [+0.29, +0.41] | **빈칸** |
| **infectious_immune** | +0.01 **[−0.18, +0.25]** (267) | +0.07 [−0.01, +0.15] | **빈칸** |
| otologic | +0.33 [+0.10, +0.52] (138) | +0.32 [+0.24, +0.41] | 표시 |

- 구현: 체크포인트의 `axis_hidden`. `vulnerability_model.predict()`가 해당 축의 severity를 0으로 두므로 화면 추정과 자동, 수동 반영 모두에서 빠진다. 릴리스 빌드(`build_ubuntu_release.py`)와 portable 빌드에 함께 실린다. 이전 체크포인트는 `vuln_biolord.pre_hidden_2026-10-12.pt`.
- 신경 축은 두 검증을 모두 통과했다. 3차 §7의 우려(신경 자료 92개)와 달리 순위 정보는 있다.

### 축 offset 문제 (보정은 기준 미달로 미적용)

축별 순위 검정은 축 안의 순서만 보므로, 축마다 다른 offset을 놓친다. ICD-10 질환명 2,000개에 대해 axis head의 1위 축은 **Ear 25%, hepatic 27%, Neuro 0.5%**였다. `amnesia`가 Neuro 대신 Ear로 나온 직접 원인이다.
축별 평균, 표준편차 보정(`ml/axis_calibration.py`, 규칙 사전 고정: 어느 쪽이든 질환 내 순위가 유의하게 나빠지면 미적용)의 결과는 다음과 같다.
- 1위 축 분포는 고르게 바뀐다(Ear 2%, Neuro 9.5%).
- 내부 −0.035 [−0.056, −0.010], DTB +0.038 [+0.017, +0.057] → **미적용**. offset의 일부는 FinnGen 자료 안에서는 실제 구조지만 덴마크로는 옮겨지지 않는다.

## 4. DTB를 학습 자료로 추가할지 (`ml/axis_dtb_augment.py`): 기준 미달

| 단계 | FinnGen 보류(질환 내 ρ 차이) | DTB 보류(블록 단위) | 판정 |
|---|---|---|---|
| v1 가중치 1, seed 300–302 | −0.032 [−0.055, −0.010] | **+0.199 [+0.165, +0.234]** (0.19 → 0.39) | 미달 |
| 가중치 선택(seed 300–302) | w 0.1: −0.002 / w 0.25: −0.013 / **w 0.5: −0.016 [−0.034, +0.002]** | +0.055 / +0.134 / **+0.180** | w 0.5 선택 |
| **확인(seed 400–402, w 0.5)** | −0.018 [−0.042, **−0.0005**] | +0.177 [+0.145, +0.209] | **미달**(상한이 0을 0.0005 밑돎) |

- DTB를 더하면 덴마크 보류 자료에서 질환 내 순위가 크게 좋아지고, 축별로는 13개 중 12개 축이 통과한다(면역만 빈칸). 대신 FinnGen 보류에서 약 0.02 나빠진다.
- 사전 기준에 따라 배포하지 않았다. 기준을 바꿀지는 사용자 판단으로 남긴다.

## 5. 한국어 입력 (index v3)

- 건강보험심사평가원 상병마스터(한방 전용, U코드 제외)로 한글명 → 영문명 표 52,626개를 `mondo_index.npz`에 넣었다(`linking_models.py index3`, 이전은 `.pre_v3`).
- 찾는 순서: 일상어 목록(`data/curated/korean/lay_aliases.tsv`, 예: 당뇨 → diabetes; KCD의 '당뇨'는 R81 Glycosuria) → 정확한 KCD 이름(`상세불명의 X`, `기타 X`, `X(진성)`은 X로도 찾음) → 입력으로 **끝나는** 이름 중 가장 일반적인 코드. 입력을 포함하기만 하는 이름은 쓰지 않는다(`갑상선기능저하증` → Hypoparathyroidism, `간질` → hernia 같은 오류 때문).
- 예: 당뇨, 당뇨병 → Type 2 diabetes(registry), 치매 → Dementia, 자폐증 → autism, 뇌졸중, 중풍 → stroke, 고지혈증 → hyperlipidemia, 건망증 → Memory impairment, 류마티스 관절염 → rheumatoid arthritis.
- 한국어 gold는 없다. 영어 입력은 바뀌지 않는다(gold A4 macro-F1 0.660, v2와 동일).
- portable 빌드와 서버 결과 일치 테스트에 `자폐증`을 추가했다.

## 6. 버전

- 앱 0.2(`ml/adc_version.py`, `pyproject.toml`, API). RUNTIME_API는 1 유지: 새 키(`axis_hidden`, `ko_*`, `hp_*`, `abbr_*`)는 모두 선택 사항이라 0.1 앱 + 0.2 모델, 0.2 앱 + 0.1 모델 모두 동작한다.
- 모델 0.2 = 0.1의 FinnGen axis head + `axis_hidden` + index v3. SapBERT, BioLORD는 바뀌지 않으므로 업데이트 때 head와 index만 받는다.
- `THIRD_PARTY_NOTICES.md`에 HPO, SPECIALIST Lexicon, HIRA 상병마스터(공공누리 1유형 출처표시)를 추가했다.
- GitHub 릴리스와 push는 하지 않았다.

---

# 5차: 학습 자료를 FinnGen에서 덴마크 DTB로 교체 (2026-10-12 밤)

## 1. 왜 처음에 FinnGen을 썼나

- 팀원이 2026-10-09에 준 `finngen_outcome_mapping.xlsx`(`data/raw/atlas/2026-10-10/`)가 출발점이다. 내용은 FinnGen R10의 질환 → 질환 hazard ratio 요약(lag별)이고, 팀원은 각 결과 질환을 CTCAE SOC에 맞춘 독성 도메인으로 매핑했다(`mapped_toxicity_domain`).
- 원래 계획(`docs/archive/team/TEAMMATE_DATA_USE.md`)은 점수식의 `Coupling` 항(FAERS 적응증 동시발생 자리)을 이 자료로 채우는 것이었다. 분모, 시간 방향, 불확실성(CI, p, N)이 있어서 FAERS보다 낫다고 판단했다. 이 계획은 `src/`에 구현되지 않았다.
- 대신 ML 쪽에서 "기저질환 X가 있으면 어느 장기가 이미 취약한가"를 학습하는 모델(`ml/task_a_comorbidity_risk.py`, `vulnerability_model.py`)로 쓰였다. 앱에서는 기본 꺼짐이고, 장기를 못 찾은 입력의 보조 추정으로만 쓴다.
- 한계: 일부 쌍만 들어 있고 대부분 유의한 쌍이다(선택 기준은 제공자 확인 필요). 결과 질환 종류도 한정된다.

## 2. 비교 (`ml/axis_source_compare.py`, 규칙 사전 고정)

심판은 학습에 쓰지 않는 제3 코호트인 **HuDiNe**(미국 Medicare, ICD-9 3자리, 환자 10명 이상인 모든 동시발생 쌍, 849개 질환, 이름은 CMS ICD-9-CM v32)다. 규칙: 심판 점수가 가장 높은 모델을 쓰되, FinnGen 대비 차이의 CI 하한이 0보다 커야 한다. 축은 심판에서 축별 CI 하한 > 0이면 표시한다.

| 모델 | 미국 심판(HuDiNe) | FinnGen 보류 | 덴마크 보류 |
|---|---|---|---|
| Fin만(기존) | 0.212 | **0.360** | 0.182 |
| **덴마크만** | **0.404** | 0.224 | **0.418** |
| 둘 다(가중치 1) | 0.360 | 0.334 | 0.394 |
| 둘 다(덴마크 0.5) | 0.344 | 0.351 | 0.369 |

- 덴마크만 vs FinnGen: 심판 **+0.192 [+0.149, +0.236]**, FinnGen 보류 −0.136, 덴마크 보류 +0.236.
- 13개 축 모두 심판에서 통과(ρ +0.32 ~ +0.58)했으므로 빈칸 축은 없다.
- 결과: **덴마크만 학습한 axis head를 배포**(`axis_training = DTB exposures only`, head 3개). FinnGen axis head는 `vuln_biolord.finngen_axis_2026-10-12.pt`에 보존. FinnGen TwoTower ensemble은 비교용(`ADC_VULN_HEAD=twotower`)으로 남는다.
- 변화 예: amnesia Ear 0.26 → **Neuro 0.40**, hepatitis → Liver 0.94, rheumatoid arthritis → MSK. ICD 질환명 2,000개의 1위 축에서 Ear 25% → 9.7%.

## 3. 해석과 주의

- FinnGen 보류 점수에서는 FinnGen 모델이 가장 높다. 같은 자료 안에서 맞히는 문제라 자연스럽다. 두 독립 코호트(덴마크, 미국)에서는 덴마크 모델이 일관되게 낫다.
- 덴마크와 미국 자료는 둘 다 ICD 장(chapter)으로 결과를 장기에 매핑했다. FinnGen은 팀원의 CTCAE 독성 도메인 매핑이다. 심판이 덴마크와 같은 방식의 목표를 쓰므로 덴마크에 일부 유리할 수 있다. 다만 미국 자료는 선택 없는 전체 쌍이고 코호트도 다르다.
- 덴마크 자료의 결과에는 같은 장기의 다른 질환이 포함되므로(예: RA → 근골격), 자기 장기 신호가 강하다. 앱에서 이 추정은 장기를 못 찾은 입력에만 쓰이므로 이 성질은 오히려 맞다.
- FinnGen의 HR 값과 행은 앱과 번들에 나가지 않는다(이전과 같음).

---

# 6차: 모델 3개를 함께 보여주고 동의한 장기만 자동 반영 (2026-10-12 밤)

- 결과 화면의 학습 추정에 모델 3개의 값을 나란히 보여준다. 열 이름은 학습 자료를 줄여 쓴 영어다.
  - **Den**: 배포 모델(덴마크 DTB만, 5차)
  - **Both**: FinnGen + DTB(가중치 1)
  - **Fin**: 0.1의 FinnGen axis head
- 막대는 Den 모델 값이다. 오른쪽 끝의 `n/3`은 그 장기를 자기 상위 3개 장기(severity > 0)에 넣은 모델 수다. 장기는 동의 수, 그다음 Den 점수 순으로 정렬한다.
- 검증(`ml/axis_ensemble.py`, 미국 HuDiNe, 규칙 사전 고정): Den 모델 상위 3개 장기의 정밀도(실제로 그 질환에서 평균보다 높은 장기인지)

| 동의 | 정밀도 | 장기 수 |
|---|---|---|
| 3/3 | 0.768 | 921 |
| 2/3 | 0.702 | 849 |
| 1/3 | 0.547 | 636 |

  2개 이상 동의와 1개뿐인 경우의 차이 +0.189 [+0.138, +0.238] → 규칙 통과. **자동 반영("자동" fallback)은 2개 이상 동의한 장기만 쓴다**(`agree_min = 2`). 1/3 장기는 회색으로 보여주기만 한다.
- 주의: HuDiNe는 5차에서 Den 모델을 고를 때도 썼으므로, 이 검증은 완전히 새로운 자료는 아니다.
- 구현: 체크포인트의 `axis_models`(Both, Fin head), `agree_min`. `vulnerability_model.predict_models()`, `agreement()`. 릴리스와 portable 빌드에 함께 실린다. 모델 파일은 약 8 MB 늘었다.
- 테스트: `test_every_model_is_shown_and_only_agreed_organs_are_applied_automatically`.

## 6-1. 기본 모델을 Both로 변경 (사용자 결정)

| 모델 | 미국 HuDiNe | FinnGen 보류 | 덴마크 보류 | 평균 | 최저 |
|---|---|---|---|---|---|
| Den | **0.404** | 0.224 | **0.418** | 0.349 | 0.224 |
| **Both** | 0.360 | **0.334** | 0.394 | **0.363** | **0.334** |

- 미국 자료만 보면 Both가 낮다(−0.044 [−0.064, −0.023]). 세 자료 전체의 평균과 최저 점수는 Both가 낫고, 팀원 자료(FinnGen)도 계속 쓴다. 두 모델의 1위 장기가 같은 질환은 61%다.
- 화면 열 순서: **Both, Den, Fin**. 막대, 정렬, 자동 반영은 Both 기준이다. 이름은 체크포인트에 저장(`axis_label`, `axis_models[].name`).
- Both를 기본으로 한 동의 검증(`axis_ensemble.py --swap-main`, `axis_ensemble_v2.json`): 3/3 0.768, 2/3 0.630, 1/3 0.439. 차이 +0.252 [+0.177, +0.324] → 2개 이상 동의 규칙 유지.
- 축별 HuDiNe 검증에서 **metabolic_endocrine**의 CI 하한이 0 이하라 빈칸으로 둔다.
- Den 기본 버전은 `vuln_biolord.den_main_2026-10-12.pt`에 보존.
