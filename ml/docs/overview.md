# 연구 흐름 한눈에 보기 (2026-10-25)

이 문서는 장기 판정 모델 연구의 전체 흐름과 현재 위치를 정리한다. 앱 사용법은 [README](../../README.md)에 있다. 세부 수치는 각 단계의 문서에 있다.

## 1. 풀려는 문제

환자의 기저질환 입력(한국어·영어·약어·증상 문장)을 받아 아래 두 가지를 정한다.

1. 어떤 MONDO 질환인지
2. 13개 장기 중 어디가 이미 손상됐는지

장기 13개: haematologic, hepatic, cardiovascular, pulmonary, renal, neurologic, gastrointestinal, dermatologic, ocular, otologic, musculoskeletal, metabolic_endocrine, infectious_immune.

앱은 이 장기를 ADC 15종의 라벨 경고(Boxed warning, Warning, Label restriction)와 맞춰 본다. 점수는 모두 **장기 macro-F1**이다.

## 2. 전체 흐름

```
 [데이터]                       [장기 라벨]                    [모델]                           [평가]
 MONDO 질환·동의어 ─┐       v4 (Opus 에이전트, 앱에서 사용) ┐   ① Gemma 판정 모델 (E2B / E4B)  ┐   gold: 처음 보는 질환 600문항
 HPO 표현형·빈도   ─┼──▶    v5 (GPT 3회 + 판정 + 감사)     ├─▶ ② encoder (BiomedBERT 등)     ├─▶ known: 아는 질환, 새 표현
 UMLS 이름·정의    ─┤       v5.1 (involved 재검토)        ┘   ③ ① + ② 결합                   │   dev로 튜닝, test는 마지막 1회
 PubMed 초록       ─┘                                       ④ 처음부터 만든 모델 (X0 → X3)   ┘
```

- **격리 규칙:** gold 질환과 그 부모·자식 질환은 학습 데이터, 라벨 예시, 증류 문장, 사전학습의 구조화 문장에서 모두 뺀다. 그래서 gold는 정말 처음 보는 질환을 재는 시험이 된다.
- **test 규칙:** 튜닝 중에는 dev만 본다. test는 최종 모델을 정한 뒤 한 번만 본다. 10-20부터의 탐색에서는 test를 보지 않았다. 다만 그 전 모델 0.6 단계에서 gold test를 여러 번 열었으므로([gemma_judge.md](gemma_judge.md) 7절), gold test 점수는 완전히 깨끗하지 않다. known test는 한 번도 열지 않았다.

## 3. 용어

| 용어 | 뜻 |
|---|---|
| gold_v0 | 사람이 합의한 장기 정답(600문항, 211개념). 원본이며 바꾸지 않는다 |
| gold_v1 | gold 개념을 v5 기준으로 다시 라벨링한 것. GPT 라벨과 Claude 라벨이 다르면 두 판정자(Claude, GPT)가 A/B로 보고, 둘이 다르면 gold_v0이 정한다 (`ml/gold_v1.py`) |
| known | 학습에 들어간 질환을 새로운 표현으로 묻는 평가(영어 326, 한국어 1,142문항, `ml/known_eval.py`). 정답은 학습에 쓴 라벨표다 |
| primary / involved | v5 라벨의 두 단계. primary는 질환이 생기는 장기, involved는 질환이 직접 손상시키는 다른 장기 |
| E2B / E4B | Gemma 4의 두 크기. 모델 0.6까지 앱은 E2B 앞 18층에 LoRA를 붙여 int8로 썼다 |
| S2d, S5a, S6d … | Gemma 튜닝 설정 이름. S2d = 한국어 포함 기본, S5a = 영어만, S6d/S6e = E4B 영어만. 기록은 [tuning_log.md](tuning_log.md) |
| 결합(hybrid) | encoder가 찾은 질환의 유사도가 기준(0.85) 이상이면 encoder 답을 쓰고, 아니면 Gemma 판정을 쓴다 |
| X0 ~ X3 | 사전학습 모델 없이 처음부터 만든 판정 모델. [scratch_model.md](scratch_model.md) |
| seed 7·8·9 | 같은 설정을 seed 3개로 학습해 평균을 낸다. gold dev는 작아서 bootstrap 95% 구간이 약 ±0.05다. 그 안의 차이는 노이즈로 본다 |

## 4. 단계별 진행

### 4.1 장기 라벨

| 버전 | 만든 방법 | 상태 |
|---|---|---|
| v4 | Claude Haiku 에이전트 150개가 라벨링하고, Opus 에이전트 286개가 검수 (21,032개념, [gemma_judge.md](gemma_judge.md) 3.1절) | 앱이 쓰는 라벨 |
| v5 | GPT(gpt-6.1-sol)가 모든 개념을 독립적으로 3번 라벨링한다. 3번이 다르면 판정하고, 일부는 감사한다. 3,519 세션, 22,638개념. 패스 간 κ는 0.937~0.980 | 완료. [REPORT.md](../../data/curated/concept_organs/v5/REPORT.md) |
| v5.1 | v5의 involved 6,384개를 Haiku 두 명이 규칙([RULE_v5_1.md](../../data/curated/concept_organs/v5/RULE_v5_1.md))으로 다시 본다. 둘 다 빼자고 하면 GPT가 한 번 더 확인한다. 최종 1,218개를 뺐다(선천 구조 이상, 환자 1~2명뿐인 빈도) | 완료. 연구 학습에 사용 |

라벨 버전별 Gemma E2B 재학습 결과(S5a 설정, dev 영어, seed 3개 평균):

| 라벨 | gold_v0 | gold_v1 |
|---|---|---|
| v4 | **0.862** | 0.805 |
| v5 | 0.844 | 0.810 |
| v5.1 | 0.856 | **0.819** |

BiomedBERT-large(encoder, seed 3개)도 같은 모양이다. gold_v0은 v4 0.786 → v5.1 0.774로 내려가고, gold_v1은 0.736 → 0.747로 오른다.

- 차이는 모두 노이즈 범위 안이다. v5.1이 두 gold에서 가장 고르게 나와 이후 연구 학습에는 v5.1을 쓴다.
- known은 정답이 각자 학습한 라벨표라서 라벨 버전끼리 비교하는 데 쓸 수 없다.
- gold_v1을 만들 때 각 회사 모델이 자기 회사 라벨을 더 고르는 편향이 보였다(33건 중 26건씩). 그래서 두 판정자가 같을 때만 확정한다.

### 4.2 Gemma와 encoder (앱에 들어갈 후보)

영어 기준 현재 최선(dev, seed 3쌍, v4 라벨): **BiomedBERT-large + Gemma 결합**. encoder 장기 출력을 쓰고 기준은 0.85다.

| 결합 | gold 영어 | known 영어 | 영어 평균 |
|---|---|---|---|
| e5 + Gemma S2d (이전 기준선) | 0.841 | 0.820 | 0.831 |
| BiomedBERT-large + E2B S5a | 0.845 | 0.878 | 0.862 |
| BiomedBERT-large + E4B (규칙 통과분) | 0.863 | 0.882 | 0.873 |

- E4B는 실행 세 번 중 한 번꼴로 덜 학습된 채 끝난다. 그래서 학습 val organ loss가 0.13 미만인 실행만 받는다.
- 크기 대비 이득을 생각하면 앱 후보는 E2B 결합이다.
- 전체 표는 [sweep_1027.md](sweep_1027.md)에 있다.

### 4.3 처음부터 만든 모델 (메인 목표)

외부 사전학습 가중치 없이 학습한다. BERT 구조를 무작위 가중치에서 시작하고, tokenizer도 직접 만든다.

| 단계 | 들어가는 것 |
|---|---|
| 사전학습(빈칸 맞히기) | 공개 의학 텍스트만. PubMed 초록 86%, UMLS 이름·정의 12%, MONDO·HPO 1%, 의약품 라벨·임상시험 문서 0.5%. 일반 텍스트(웹, 위키백과)는 없다 |
| 판정 학습 | 질환 이름과 표현, 프로젝트가 만든 장기 라벨(v5.1), 튜닝한 Gemma의 장기 확률(증류 목표) |

장기 라벨과 증류 목표는 이 프로젝트가 만든 학습 목표다. 다른 모델의 가중치나 지식을 가져온 것이 아니다.

| 모델 | 사전학습 | gold_v0 영어 | known 영어 |
|---|---|---|---|
| X1 | 긴 사전학습 없음 (질환 이름과 UMLS 이름으로 학습, seed 3개) | 0.593 | 0.734 |
| XP2 | BERT-medium, PubMed·UMLS 30시간 | 0.695 | 0.775 |
| X2 | BERT-base, 전체 단어 마스킹, UMLS·MONDO·HPO 10배, 48시간 + Gemma 증류 | **0.702** | **0.807** |
| 참고: BiomedBERT-large 튜닝 (seed 3개) | Microsoft의 PubMed 사전학습 모델 | 0.786 | 0.876 |

- **Gemma 증류:** 튜닝한 Gemma가 47만 개 질환 이름에 낸 장기 확률을 함께 배운다. gold와 평가 문장은 빠진다. gold는 약 +0.03 오른다.
- 사전학습 24시간 → 48시간은 점수를 올리지 못했다. 그래서 **X3(BERT-large, 335M, GPU 3장, 32시간)**를 학습 중이다. 결과는 10-26 밤에 나온다.

## 5. 최종 결과 (test, 2026-10-26 한 번 채점)

최종 구성은 dev에서 미리 정한 규칙으로 골랐다: **x2te = X2 + 영어 오타·약어 쌍 + 기록 읽기**([scratch_model.md](scratch_model.md) "최종 구성 선택"). 그 뒤 test를 한 번 열었다.

| test, 영어, seed 3개 평균 | gold_v0 | gold_v1 | known | 평균 (gold_v0, known) |
|---|---|---|---|---|
| 튜닝 안 한 Gemma E2B | 0.739 | 0.725 | 0.432 | 0.586 |
| Gemma E2B v51a (튜닝) | 0.834 | 0.828 | 0.588 | 0.711 |
| X2 (처음부터) | 0.694 | 0.699 | 0.678 | 0.686 |
| **x2te (처음부터, 최종)** | 0.778 | 0.789 | 0.667 | **0.723** |
| x2te + Gemma (유사도 0.8 이상이면 x2te) | 0.836 | 0.839 | 0.674 | **0.755** |

- 문항 수: gold test 296문항(영어 유효 질문), known test 168문항.
- x2te는 미리 정한 기준(gold_v0과 known 평균)에서 Gemma v51a보다 0.012 높다. 다만 seed별 paired bootstrap 95% 구간은 0을 포함한다(gold_v0 −0.05 [−0.11, +0.01], known +0.08 [−0.03, +0.15], seed 7). "통계적으로 낫다"가 아니라 "비슷하거나 조금 낫다"로 말한다.
- 결합은 처음 보는 질환에서 Gemma와 같고(0.836 대 0.834), 아는 질환에서 0.09 높다.
- gold test는 0.6 단계에서 여러 번 열린 적이 있다(위 test 규칙). known test는 이번에 처음 열었다.
- 원자료: `ml/results/benchmarks/final_test.json`.

**앱 교체 기준 (2026-10-25 결정):** 처음부터 만든 모델이 Gemma 판정 모델을 넘을 때까지 앱은 Gemma로 돌아간다. 그동안 처음부터 만든 모델을 계속 학습한다.

**교체 (2026-10-27):** test에서 기준을 넘어(위 표), 앱 0.5.0과 모델 0.7부터 x2te 단독으로 판정한다(`ScratchJudge/`, `ml/scratch_runtime.py`). 아래 표는 교체를 정할 때 쓴 dev 기록이다.

비교 조건은 아래와 같다.
- 같은 v5.1 라벨로 학습한 Gemma E2B 판정 모델(v51a)과 비교한다.
- 점수는 dev 영어, seed 3개 평균이다.
- 기준은 gold_v0과 known의 평균이다.

| | gold_v0 | gold_v1 | known | 평균 (gold_v0, known) |
|---|---|---|---|---|
| Gemma E2B v51a (넘어야 할 기준) | 0.856 | 0.819 | 0.696 | **0.776** |
| X2 | 0.702 | 0.679 | 0.807 | 0.754 |

- X2는 아는 질환(known)에서는 이미 Gemma보다 0.11 높다.
- 처음 보는 질환(gold)에서는 0.15 낮다. 이 차이를 줄이는 것이 핵심이다.

**X2 + Gemma 결합 (2026-10-25, 저장된 문항별 결과로 계산):** X2가 찾은 질환의 유사도가 기준 이상이면 X2 답을 쓰고, 아니면 Gemma 답을 쓴다.

| | gold_v0 | gold_v1 | known | 평균 | X2가 답한 known 비율 |
|---|---|---|---|---|---|
| Gemma 단독 | 0.856 | 0.819 | 0.696 | 0.776 | 0% |
| X2 단독 | 0.702 | 0.679 | 0.807 | 0.754 | 100% |
| X2 ≥ 0.95, 아니면 Gemma | 0.839 | 0.807 | 0.734 | 0.786 | 15% |
| X2 ≥ 0.9, 아니면 Gemma | 0.829 | 0.797 | 0.767 | 0.798 | 30% |
| X2 ≥ 0.85, 아니면 Gemma | 0.820 | 0.789 | 0.799 | 0.809 | 45% |
| **X2 ≥ 0.8, 아니면 Gemma** | 0.812 | 0.780 | **0.819** | **0.816** | 63% |

- 기준은 dev에서 고른 값이라 조금 낙관적이다.
- known dev는 158문항(112개념)이고, 논문 속 질환 언급이다. 환자 기저질환 입력과는 분포가 다르다.

평가는 영어 장기 F1만 본다(2026-10-25부터 한국어 점수는 재지 않는다). 다른 문서 표에 있는 한국어 칸은 그 전 기록이다.

## 6. 문서 지도

| 문서 | 내용 |
|---|---|
| [gemma_judge.md](gemma_judge.md) | 모델 0.6까지 앱의 Gemma 판정 모델 구조와 평가 |
| [tuning_log.md](tuning_log.md) | 모든 튜닝 실행의 데이터·설정·점수 기록 |
| [sweep_1027.md](sweep_1027.md) | 10-20~27 Gemma·encoder·결합 탐색 |
| [relabel_v5_plan.md](relabel_v5_plan.md) | 장기 라벨 v5 계획과 결과 |
| [scratch_model.md](scratch_model.md) | 처음부터 만든 모델 X0~X3 |
| [reproduce.md](reproduce.md) | 학습부터 비교 보고서까지 재현하는 명령 |
| [data_inventory.md](data_inventory.md) | 데이터 목록과 출처 |
