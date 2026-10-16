# ADCTOX 자료 반영 절차 (관리자용)

기준: 2026-10-12, 앱 0.3(배포 준비), 모델 0.2(배포됨).

팀원은 CSV 칸만 채운다(안내문: `docs/archive/team/TEAM_GUIDE.md`). 이 문서는 받은 파일을 검사해 학습과 평가 형식으로 바꾸고, 모델을 다시 만들고, 채택을 판정하는 사람을 위한 것이다.

## 팀원 파일 가져오기 (`ml/team_sheets.py`)

빈 양식은 `data/curated/team_sheets/`에 있다(`$PY -I ml/team_sheets.py make`로 다시 만들 수 있음).

| 받은 파일 | 명령 | 결과 | 다음 단계 |
|---|---|---|---|
| 1번 한 사람 것, 또는 두 사람 것 (+ 불일치 파일을 채운 셋째 것) | `team_sheets.py organs A.csv [B.csv [C.csv]]` | `concept_organs/labels/expert_team_<날짜>.jsonl`, 불일치는 `team_sheets/1_장기판정_불일치_<날짜>.csv` | 과제 1-6 재빌드와 평가 |
| 2번 (두 사람이면 둘 다) | `team_sheets.py picks A.csv [B.csv]` | `train_queries/human_picks_<날짜>.jsonl` | 과제 2 재정렬 학습 자료 |
| 3번 | `team_sheets.py real-inputs F.csv` | `disease_linking/raw/queries_real_v1.json`, 정답 고르기 양식 `team_sheets/3b_실제입력_정답고르기.csv` | 3b를 두 사람에게 보냄 |
| 3b 두 사람 것 (+ 셋째) | `team_sheets.py real-gold A.csv B.csv [C.csv]` | `disease_linking/gold_real_v1.jsonl` | 과제 3-5 평가 |
| 4번 | `team_sheets.py korean F.csv` | `korean/lay_aliases.tsv`에 추가 | `linking_models.py index3` |
| 5번 | `team_sheets.py abbrev F.csv` | `abbreviations/team.tsv`에 추가 | `linking_models.py index2`, `index3` |
| 6번 | (자동 없음) | `data/raw/<출처>/`에 저장 | 과제 4-5 loader 작성 |

- 값이 잘못된 파일은 아무것도 저장하지 않고 "파일 몇 행: 무엇이 문제"를 출력한다. 그 줄만 팀원에게 돌려보낸다.
- 한 사람 파일만 있으면 채운 줄이 모두 라벨이 된다(`confidence: single`, 일치율 없음). 두 사람이면 답이 같은 줄만 라벨이 된다. 일치율이 출력되니 기록해 둔다(1번은 0.7 미만이면 장기 정의를 다시 설명하고 일부를 다시 받는 것이 좋다).
- 엑셀의 일반 "CSV"(CP949)로 저장된 파일도 읽는다.
- 1번 양식은 모델의 현재 답을 보여주지 않는다(검토자가 그 답에 끌리지 않게). 후보 순서는 섞어 두었다.

아래 과제 1~4는 이렇게 들어온 자료로 무엇을 어떻게 고치고 판정하는지다.

| 과제 | 한 줄 요약 | 개선 여지(측정값) | 주로 고칠 파일 |
|---|---|---|---|
| 1. 질환 → 장기 판정 | 질환은 맞게 찾았는데 장기가 틀리는 문제 | 장기 판정이 완벽하면 F1 0.619 → 0.785 (+0.17) | `data/curated/concept_organs/labels/`, `conf/ontology/mondo_organ_axis.yaml`, `ml/linking_models.py` |
| 2. 후보 재정렬과 기준값 | 정답 질환이 상위 10개 안에 있는데 1등이 아닌 문제 | 재정렬과 기준값이 완벽하면 F1 0.619 → 0.705 (+0.09), 개념 정확도 0.62 → 0.85 | `ml/mondo_index.py`의 `link()`, 새 학습 스크립트 |
| 3. 실제 입력 평가 자료 | 지금 평가 자료는 Claude가 만든 질의라 실제 입력과 다를 수 있음 | 측정의 신뢰도 자체 | `data/curated/disease_linking/` 아래 새 파일 |
| 4. 장기 추정 자료 보강 | 학습 추정 모델의 자료 출처와 독립 검증 | 독립 미국 자료 0.36 (현재) | 새 loader + `ml/axis_source_compare.py` |

---

## 0. 공통 준비

### 0-1. 코드와 실행 환경

```bash
git clone https://github.com/ahnhc/ADCToX.git && cd ADCToX
git checkout -b task1-organs          # 과제별 브랜치. main에 직접 push하지 않는다.
```

- 연구실 서버에서 작업하면 연구 환경 Python이 이미 있다: `<python env>/bin/python` (torch, transformers, sentence-transformers, scikit-learn).
- 다른 컴퓨터에서는 Python 3.12에 `torch==2.11.0 transformers==5.19.0 sentence-transformers==6.1.0 numpy pandas scipy scikit-learn pyyaml pyarrow`를 설치한다. GPU가 있으면 빠르지만 없어도 된다(평가 1회 수 분 ~ 수십 분).
- GPU를 고를 때는 `CUDA_VISIBLE_DEVICES=1` 처럼 지정한다. 서버 GPU는 공용이다.

### 0-2. 데이터 받기

묶음은 서버의 `<handoff folder>/`에 있다.

| 파일 | 내용 | 풀 위치 |
|---|---|---|
| `adctox-team-data.tar.gz` | `data/curated/`(평가 자료, 라벨) + `data/raw/` 공개 자료 + MONDO | 저장소 루트에서 `tar xzf` |
| `adctox-team-cache.tar.gz` | 연구용 cache(`ml_cache/`): 색인, 모델, FinnGen 표, 임베딩 | 원하는 곳에서 `tar xzf` |
| `SHA256SUMS` | 두 파일의 체크섬 | `sha256sum -c SHA256SUMS` |

다른 컴퓨터에서는 경로를 환경 변수로 알려 준다.

```bash
export ADCTOX_REPO=$PWD                         # 저장소
export ADCTOX_CACHE=/path/to/ml_cache           # 풀어 둔 cache 폴더
export ADC_RESEARCH_MODE=1                      # 설치된 앱 모델 대신 연구 cache 사용
```

**연구실 서버에서도 cache는 반드시 복사해서 쓴다.** 서버의 기본 cache(`<server ml_cache>`)는 배포 모델을 만드는 원본이다. 색인을 다시 만드는 명령은 cache 안의 파일을 덮어쓴다.

```bash
mkdir -p ~/adctox_cache && tar xzf <handoff folder>/adctox-team-cache.tar.gz -C ~/adctox_cache
export ADCTOX_CACHE=~/adctox_cache/ml_cache
```

알려진 문제: `ml/lab.py`, `ml/mondo_index.py`, `ml/prepare_data.py`, `ml/build_external_linking.py`를 **직접 실행**할 때는 `-I` 없이 실행한다(`python ml/build_external_linking.py`). 다른 스크립트가 불러 쓰는 경우는 문제없다.

### 0-3. 평가 규칙 (모든 과제 공통)

1. **gold는 평가 전용이다.** gold 질의의 정답 개념과 그 부모, 자식 개념은 어떤 학습에도 넣지 않는다. 라벨 loader가 자동으로 걸러내지만(`linking_models.gold_held`), 새 학습 스크립트를 만들면 같은 함수를 쓴다.
2. **dev에서 고르고 test는 마지막에 한 번 본다.** gold 600개는 개념 그룹 단위로 dev 304 / test 296으로 나뉜다(`eval_linking.split_of`, 해시 고정). 기준값, 규칙, 하이퍼파라미터는 dev로만 고른다.
3. **배포 기준을 먼저 적는다.** 실험을 돌리기 전에 PR 설명에 "무엇을 비교하고, 어떤 결과면 채택하는가"를 적는다. 결과를 본 뒤 기준을 바꾸지 않는다.
4. **차이는 paired bootstrap 95% CI로 본다.** 질환 연결은 개념 그룹 단위(`eval_linking.boot`), 외부 corpus는 문서 단위로 다시 뽑는다. CI 하한이 0보다 커야 "개선"이다.
5. **결과는 파일로 남긴다.** `ml/results/benchmarks/<이름>.json`과 `ml/docs/`의 짧은 보고(무엇을, 왜, 결과, 채택 여부). 실패한 실험도 남긴다.

### 0-4. 현재 기준선 (gold test 296개)

| 시스템 | macro-F1 | 무효 입력 통과율 | 설명 |
|---|---|---|---|
| A2 SapBERT 1등, 기준값 0.75 | 0.640 | 0.133 | 연결기 단독 |
| **A4 앱 전체 파이프라인** | **0.660** | **0.000** | 이 숫자를 넘는 것이 목표 |

A4의 입력 유형별 macro-F1: 정식 이름 0.777, 동의어 0.751, 약어 0.514, 오타 0.525, 일상 표현 0.513.
결과 파일: `ml/results/benchmarks/linking_v3_pipeline.json`. 재현: `CUDA_VISIBLE_DEVICES=1 $PY -I ml/eval_linking.py --tag v3_pipeline` (`$PY`는 연구 환경 Python).

### 0-5. 하지 말 것

- COMETA, HuDiNe, FinnGen 원자료, 팀원 워크북을 Git에 올리지 않는다(재배포 조건). `data/raw/`는 이미 `.gitignore`에 있다.
- 배포 cache를 직접 고치지 않는다(0-2).
- 앱 번들(색인, 모델 파일)에 재배포가 막힌 자료에서 나온 문자열을 넣지 않는다. 학습에 쓰는 것은 괜찮다.

---

## 1. 과제 1: 질환 → 장기 판정 개선

### 1-1. 지금 어떻게 동작하나

입력이 MONDO 질환으로 연결되면, 그 질환의 장기는 **색인에 미리 저장된 값**(`mondo_index.npz`의 `axes`)을 읽는다. 이 값은 다음 순서로 만들어진다.

```
conf/ontology/mondo_organ_axis.yaml (상위 개념 → 장기 규칙, "crosswalk")
data/curated/concept_organs/labels/*.jsonl (개념별 장기 라벨, 지금은 Claude Haiku가 단 것)
        ↓  ml/linking_models.py organs   (축마다 logistic 회귀: SapBERT 이름 벡터 + crosswalk + 상위 개념 표시)
        ↓  dev에서 결합 규칙과 확률 기준값 선택 (learned / union / hybrid / crosswalk)
        ↓  ml/linking_models.py index    (모든 인간 질환 개념의 장기를 계산해 색인에 기록)
mondo_index.npz 의 axes
```

| 파일 | 역할 |
|---|---|
| `conf/ontology/mondo_organ_axis.yaml` | `ancestor_to_axis`: MONDO 상위 개념 id → 장기. 하위 질환은 모두 그 장기를 물려받는다 |
| `data/curated/concept_organs/GUIDE.md` | 13개 장기의 정의와 라벨 규칙 |
| `data/curated/concept_organs/labels/batch_*.jsonl` | Haiku 1차 라벨(보정 기준을 통과한 batch만 사용) |
| `data/curated/concept_organs/labels/relabel_*.jsonl` | Haiku 엄격 재라벨 |
| `data/curated/concept_organs/labels/expert_*.jsonl` | **전문가 라벨(새로 만들 파일). 다른 모든 라벨보다 우선한다** |
| `data/curated/concept_organs/review_queue.csv` | **검토 우선순위 목록(아래 1-3)** |
| `ml/linking_models.py` | `load_organ_labels`(라벨 읽기), `organ_model`(학습), `cmd_organs`(dev 선택, test 보고), `cmd_index`(색인 기록) |
| `ml/results/benchmarks/concept_organs_v1.json` | 현재 장기 모델 결과 |

### 1-2. 무엇이 틀리나 (gold에서 SapBERT가 개념을 맞힌 318개 기준)

crosswalk만 썼을 때 장기가 **빠진** 경우: pulmonary 20, infectious_immune 18, metabolic_endocrine 9, renal 9, 그 외 소수.
장기가 **잘못 붙은** 경우: gastrointestinal 22, metabolic_endocrine 22, musculoskeletal 21, neurologic 17, cardiovascular 13.
crosswalk가 아무 장기도 주지 않는 개념이 9개 있다. 학습 모델로 바꾼 뒤 개념 수준 정확도는 0.578 → 0.651이었지만 CI가 0을 포함했다(+0.072 [−0.023, +0.176]). 라벨 품질이 가장 큰 제약이다.

### 1-3. 작업 A: 전문가 라벨 (가장 효과가 클 것)

`data/curated/concept_organs/review_queue.csv`는 의학 문헌 말뭉치(MedMentions, NCBI Disease)에 자주 나오는 질환 1,718개를 빈도순으로 정리한 것이다.

| 열 | 뜻 |
|---|---|
| `id`, `name` | MONDO 개념 |
| `mentions` | 말뭉치 언급 수(정렬 기준) |
| `current_organs` | 지금 앱이 쓰는 장기 |
| `crosswalk_organs` | 규칙(yaml)만으로 나오는 장기 |
| `disagree` | 1이면 둘이 다르다(374개). **먼저 볼 것** |
| `haiku_label` | Haiku 라벨(있으면) |
| `use` | `training`: 학습에 쓸 개념. `gold_check`: gold 관련 개념(400개)이라 학습에는 쓰지 않고 gold 검증에만 쓴다 |
| `expert_organs`, `expert_scope`, `reviewer`, `note` | **채울 칸** |

절차:
1. 두 사람이 서로 보지 않고 각자 채운다. `expert_organs`는 장기 이름을 `;`로 잇는다(예 `renal;cardiovascular`). `expert_scope`는 `axis`(장기 있음), `no_axis`(13개 장기 어디에도 해당 없음, 예 정신과 질환), `unclear`(판단 불가) 중 하나.
2. 판단 기준은 `GUIDE.md`를 따른다. 핵심은 "**질환 자체가 직접 손상하거나 차지하는 장기**"(약물 독성이 더해지면 이미 손상된 장기에 겹치는 곳)이고 최대 4개다. 드문 합병증이나 나중에 생길 위험만 있는 장기는 넣지 않는다(예: 2형 당뇨 단독은 metabolic_endocrine만, renal은 아님). 감염과 면역 질환은 침범 장기 옆에 infectious_immune을 함께 표시한다.
3. 두 결과가 다른 행은 셋째 사람이 정하거나 둘이 합의한다. 합의 근거를 `note`에 적는다.
4. 확정된 `training` 행을 JSONL로 바꿔 `labels/expert_<이름>_<날짜>.jsonl`로 저장한다.

```json
{"id": "MONDO:0005147", "organs": ["metabolic_endocrine"], "scope": "axis", "confidence": "high", "reviewer": "kim+lee", "note": ""}
{"id": "MONDO:0002050", "organs": [], "scope": "no_axis", "confidence": "high", "reviewer": "kim+lee", "note": "정신과 질환"}
```

5. `gold_check` 행의 결과는 `data/curated/disease_linking/gold_organ_review.jsonl`에 같은 형식으로 저장한다. gold의 장기 정답이 틀린 것이 확인되면, 고친 gold를 `gold_v1.jsonl`로 만들고(원본 `gold_v0.jsonl`은 그대로 둔다) 이후 평가는 v0와 v1 둘 다 보고한다.

목표량: `disagree=1`인 `training` 행부터 최소 300개. 1,000개 이상이면 모델을 다시 학습할 가치가 크다.

### 1-4. 작업 B: crosswalk 규칙 고치기

검토 중 "이 상위 개념 아래는 전부 이 장기"라는 패턴이 보이면 `conf/ontology/mondo_organ_axis.yaml`의 `ancestor_to_axis`에 추가하거나 고친다. 개별 개념 라벨보다 영향 범위가 넓으므로 변경 이유를 커밋 메시지에 적는다.

### 1-5. 작업 C: 모델 자체 개선 (선택)

`ml/linking_models.py`의 `organ_model`과 `concept_features`. 지금 특징은 SapBERT 이름 벡터, crosswalk(×3), 20회 이상 나오는 상위 개념 표시이고, 축마다 L2 logistic(C=0.5)이다. 시도할 만한 것: MONDO 정의문(definition) 벡터 추가, HPO 연관(`data/raw_big/mondo/2026-10-07/hpoa.tsv`) 특징, 축별 기준값.

### 1-6. 다시 만들고 평가하는 순서

```bash
export ADC_RESEARCH_MODE=1 ADCTOX_CACHE=~/adctox_cache/ml_cache
CUDA_VISIBLE_DEVICES=1 $PY -I ml/linking_models.py organs   # 학습, dev 선택, test 보고 → concept_organs_v1.json
CUDA_VISIBLE_DEVICES=1 $PY -I ml/linking_models.py index    # 색인 v1 다시 쓰기
CUDA_VISIBLE_DEVICES=1 $PY -I ml/linking_models.py index2   # 약어, 증상 블록 다시 붙이기 (index가 지우므로 필수)
$PY -I ml/linking_models.py index3                          # 한국어 이름 다시 붙이기 (필수)
CUDA_VISIBLE_DEVICES=1 $PY -I ml/eval_linking.py --tag task1_v1
```

`index`는 원본 색인(`mondo_index.pre_v1.npz`)에서 새로 만들기 때문에 약어, 증상, 한국어 블록이 빠진다. 그래서 `index2`, `index3`를 꼭 이어서 실행한다.

**채택 기준(제안):** `linking_task1_v1.json`의 A4 test macro-F1이 기준선 0.660 대비 paired CI 하한 > 0, 무효 입력 통과율 0.000 유지. 개념 수준 장기 정확도(`concept_organs_v1.json`)도 함께 보고.

---

## 2. 과제 2: 후보 재정렬과 기준값

### 2-1. 지금 어떻게 동작하나

`ml/mondo_index.py`의 `link(texts)`:
1. 입력을 SapBERT 벡터로 만들고 색인 전체와 비교해 상위 64개 문자열을 뽑는다.
2. 같은 개념을 합쳐 상위 5개 개념(`top`)을 만든다.
3. 1등 유사도가 0.75(`THETA`) 이상이고 질환 판별기(`gate`)를 통과하면 그 개념을 쓴다.
4. 약어표와 근소한 차이(0.02 이내)의 후보로 "다른 의미"(`readings`)를 만든다.

즉 순위는 SapBERT 유사도 하나로만 정해진다.

### 2-2. 무엇이 틀리나 (gold 유효 질의 466개)

| 경우 | 수 |
|---|---|
| 1등이 정답 | 324 |
| 정답이 2~10등 | **76** ← 재정렬로 고칠 수 있음 |
| 정답이 10등 밖 | 66 |
| 정답 개념은 맞지만 유사도가 기준값 미만 | 29 ← 기준값으로 고칠 수 있음 |

유형별로는 약어, 오타, 일상 표현이 약하다(F1 약 0.5).

### 2-3. 할 일

1. **후보 특징 만들기.** 상위 10개 후보마다 다음을 계산한다.
   - SapBERT 유사도, 1등과의 차이
   - BioLORD 유사도(`vulnerability_model._st`)
   - 문자 n-gram TF-IDF 유사도
   - 개념 빈도(`linking_models.mention_counts()`)
   - 동의어 수, 이름 길이
   - 약어표 적중 여부, 입력 유형 추정(약어 형태인가)
2. **재정렬 모델 학습.** 먼저 logistic 회귀나 gradient boosting(정답 후보 = 1, 나머지 = 0)으로 시작한다. cross-encoder는 CPU에서 질의당 30 ms를 넘지 않을 때만 쓴다(앱은 CPU에서도 돈다).
3. **기준값 보정.** 재정렬 점수로 "받아들임 / 거절"을 정한다. 유형별 기준값도 dev에서 시험할 수 있다.

학습 자료(모두 gold 개념 제외):

| 자료 | 위치 | 비고 |
|---|---|---|
| Haiku가 만든 질의 2,200개와 검토 결과 | `data/curated/train_queries/` | 함정 거절률 80% 이상인 검토 batch만 사용(`sapbert_ft_v2.extra_pairs` 참고) |
| 외부 말뭉치 mention(train split) | `data/curated/external/mentions_mondo.jsonl` | `python ml/build_external_linking.py`로 생성. COMETA는 각자 이용 동의 후 `data/raw/cometa/`에 받아야 포함됨 |
| MONDO 동의어와 합성 오타 | `sapbert_ft_pilot.py`의 쌍 생성 코드 | |

### 2-4. 앱에 넣는 방법

- 재정렬 가중치는 색인 파일에 새 키로 저장한다(예 `rr_w`, `rr_b`). 릴리스 스크립트가 색인의 추가 키를 그대로 옮기므로 별도 배포 작업이 필요 없다.
- `link()`에서 `top`을 재정렬 점수로 다시 정렬한다. 키가 없는 옛 색인에서는 지금처럼 동작해야 한다.
- 새 함수를 만들면 `ml/build_portable.py`의 `runtime_modules()` 목록에 함수 이름을 추가한다. `tests/test_ml_recommender.py::test_full_build_gives_the_server_result_for_typed_diseases`가 배포본과 서버 결과가 같은지 확인한다.

**평가:** `eval_linking.py --tag task2_v1`(gold), 그리고 외부 test recall@1(`ml/sapbert_ft_v3.py`의 외부 평가 부분을 재사용). **채택 기준(제안):** A4 test macro-F1 CI 하한 > 0, 무효 입력 통과율 유지, 외부 corpus 중 유의하게 나빠지는 곳 없음, CPU 지연 질의당 +30 ms 이하.

참고: SapBERT 자체를 다시 학습하는 시도는 3번 모두 기준 미달이었다(`ml/ml/docs/archive/model_review_2026-10-12.md` 4차 §2). encoder보다 재정렬 쪽이 여지가 크다.

---

## 3. 과제 3: 실제 입력 평가 자료

### 3-1. 왜 필요한가

지금 gold 600개는 Claude Sonnet이 "환자나 의료진이 칠 법한 입력"을 상상해 만든 것이다. 실제 사용자가 치는 입력(한국어, 줄임말, 섞어 쓰기)과 분포가 다를 수 있다. 숫자가 좋아져도 실제로 좋아졌는지 알 수 없다.

### 3-2. 모으는 방법

- 앱에는 입력 기록 기능이 없다. 별도 양식(설문, 엑셀)으로 모은다.
- 대상: 종양내과 의료진, 연구 간호사, 약사 등. "ADC를 고려하는 환자의 기저질환을 이 칸에 평소처럼 적어 주세요" 형태로 받는다.
- **질환 이름만** 받는다. 환자 이름, 등록번호, 날짜 등 식별 정보는 받지 않는다. 기관 규정상 동의나 심의가 필요한지 먼저 확인한다.
- 입력한 사람이 "의도한 질환"을 옆 칸에 정식 이름으로 같이 적게 하면 라벨링이 쉬워진다.

### 3-3. 파일 형식 (기존 gold와 같은 형식)

질의 파일 `data/curated/disease_linking/raw/queries_real_v1.json` (JSON 배열):

```json
[
  {"qid": "r0001", "query": "당뇨", "category": "lay", "intended": "type 2 diabetes mellitus", "group": "type_2_diabetes", "lang": "ko", "source": "survey_2026_11"},
  {"qid": "r0002", "query": "ckd 3기", "category": "abbrev", "intended": "chronic kidney disease stage 3", "group": "ckd", "lang": "mixed", "source": "survey_2026_11"}
]
```

- `category`: `canonical`(정식 이름), `synonym`, `abbrev`, `typo`, `lay`(일상 표현), `ambiguous`(뜻이 여럿), `non_disease`(질환 아님) 중 하나.
- `group`: 같은 질환을 가리키는 입력끼리 같은 값. dev/test 분할과 bootstrap이 이 단위로 된다.

정답 파일 `data/curated/disease_linking/gold_real_v1.jsonl` (한 줄에 하나):

```json
{"qid": "r0001", "validity": "valid", "concepts": ["MONDO:0005148"], "best": "MONDO:0005148", "organs": ["metabolic_endocrine"], "source": "agreed", "note": "",
 "annotations": {"A": {"validity": "valid", "concepts": ["MONDO:0005148"], "best": "MONDO:0005148", "organs": ["metabolic_endocrine"], "confidence": "high"},
                 "B": {"validity": "valid", "concepts": ["MONDO:0005148"], "best": "MONDO:0005148", "organs": ["metabolic_endocrine"], "confidence": "high"}}}
```

- `validity`: `valid`, `ambiguous`, `non_disease`, `invalid`.
- `concepts`: 정답으로 인정할 MONDO 개념 전부(동의 개념이 여럿일 수 있음). `best`: 가장 정확한 하나.
- `organs`: 이 입력의 정답 장기. 개념의 장기가 아니라 **입력이 뜻하는 환자 상태**로 판단한다.

### 3-4. 라벨링 절차 (기존 gold와 같게)

1. 후보 목록 만들기: `ml/build_linking_pools.py`가 여러 검색기(SapBERT, BioLORD, 문자 TF-IDF)의 상위 후보를 섞어 질의당 평균 15개 목록을 만든다. 51행의 질의 파일 경로(`raw/queries_v0.json`)와 출력 파일 이름을 새 파일로 바꿔 실행한다.
2. 두 사람이 `data/curated/disease_linking/ANNOTATION_GUIDE.md`에 따라 서로 보지 않고 라벨링(A, B). 기존 예시는 `annot/shard_*_A.jsonl`, `shard_*_B.jsonl`.
3. 불일치는 셋째 사람이 조정. `ml/merge_linking_gold.py prepare`(조정 목록 생성) → 조정 → `ml/merge_linking_gold.py finalize`로 합친다. 스크립트 안의 파일 경로를 `real_v1`용으로 바꾼다. 결과를 `gold_real_v1.jsonl`로 저장.
4. 일치도(개념, 장기)를 `agreement_real_v1.json`에 기록.

### 3-5. 평가

```bash
CUDA_VISIBLE_DEVICES=1 $PY -I ml/eval_linking.py --queries data/curated/disease_linking/raw/queries_real_v1.json \
    --gold data/curated/disease_linking/gold_real_v1.jsonl --tag real_v1
```

새 질의 묶음에는 반드시 새 `--tag`를 준다(시스템 출력이 tag별로 캐시된다).

**목표량:** 질의 300개 이상, 질환 그룹 150개 이상(이 정도면 F1의 95% CI 폭이 대략 ±0.05). 그중 한국어 입력 200개 이상(지금 한국어는 평가 자료가 전혀 없다). 실제 입력 자료는 **평가 전용**으로 두고 학습에 쓰지 않는다.

---

## 4. 과제 4: 장기 추정 자료 보강

### 4-1. 지금 어떻게 동작하나

장기를 찾지 못한 입력에 "학습 추정"을 보조로 보여준다. 질환 이름의 BioLORD 벡터를 넣으면 13개 장기 점수가 나오는 작은 신경망이다.

| 화면 이름 | 학습 자료 |
|---|---|
| **Both (기본)** | FinnGen + 덴마크 DTB |
| Den | 덴마크 DTB |
| Fin | FinnGen |

세 모델의 검증 점수(독립 미국 자료 HuDiNe와 각 보류 자료에서, 질환 하나 안의 장기 순위가 실제와 맞는 정도인 Spearman의 평균)는 `ml/ml/docs/archive/model_review_2026-10-12.md`와 `ml/results/benchmarks/axis_ensemble_v2.json`에 있다. FinnGen이 들어간 수치는 `docs/`, `report/`의 문서에 옮기지 않는다(`tests/test_licence_posture.py`). 세 모델 중 2개 이상이 고른 장기만 자동 반영한다. Metabolic 장기는 검증을 통과하지 못해 빈칸이다.

관련 파일: `ml/vulnerability_model.py`(목표값 `axis_targets`, 학습 `_train_axis`), `ml/axis_dtb_augment.py`(`dtb_targets`: 덴마크 자료 loader), `ml/axis_source_compare.py`(`hudine_targets`, 모델 비교), `ml/axis_ensemble.py`(동의 규칙), `ml/axis_reliability.py`(ICD-10 → 장기 매핑 `ICD_AXIS`).

### 4-2. 작업 A: FinnGen 자료 출처 확인 (워크북 제공자에게)

`finngen_outcome_mapping.xlsx`(2026-10-09 수령)에 대해 다음을 확인해 문서로 받는다.
1. FinnGen 릴리스(R10이 맞는가)와 추출 경로(Risteys 생존분석 결과인가, 다른 분석인가).
2. **어떤 쌍을 골랐는가.** 지금 표에는 가능한 질환 쌍의 일부만 있고 대부분 유의한 쌍이다. 유의한 쌍만 고른 것인지, 상위 N개인지, 다른 기준인지.
3. **고르기 전 전체 쌍**(유의하지 않은 쌍 포함)을 받을 수 있는가. 받을 수 있으면 아래 4-4 형식으로.
4. 각 쌍의 환자 수(N), lag 정의, 성별/연령 층화 여부.

전체 쌍이 있으면 "선별된 쌍만 배운다"는 지금의 가장 큰 편향을 없앨 수 있다.

### 4-3. 작업 B: 새 독립 검증 자료

지금 독립 검증에 쓰는 미국 HuDiNe는 모델을 고를 때도 썼기 때문에 완전히 새 자료가 아니다. 학습에도 선택에도 쓰지 않은 코호트가 하나 더 필요하다.

후보(모두 기관 신청 필요): 국민건강보험공단 표본코호트, 건강보험심사평가원 환자표본, UK Biobank, 일본 JMDC, 대만 NHIRD. 이미 출판된 질환 쌍 표(논문 부록)도 가능하다. 원자료가 아니라 **질환 쌍 요약 통계**만 있으면 된다(4-4 형식).

### 4-4. 질환 쌍 자료 형식

CSV, UTF-8, 한 행이 (선행 질환, 후행 질환[, lag]) 하나.

| 열 | 필수 | 예 | 설명 |
|---|---|---|---|
| `exposure_code` | 예 | `E11` | 선행 질환 코드 |
| `exposure_system` | 예 | `ICD10` | `ICD10`, `ICD9`, `KCD`, `FinnGen`, `MONDO` |
| `exposure_name_en` | 예 | `Type 2 diabetes mellitus` | 영어 이름(모델 입력) |
| `outcome_code` | 예 | `N18` | 후행 질환 코드 |
| `outcome_system` | 예 | `ICD10` | |
| `outcome_name_en` | 권장 | `Chronic kidney disease` | |
| `effect_type` | 예 | `HR` | `HR`, `RR`, `OR` |
| `effect` | 예 | `1.84` | 1이면 관계 없음 |
| `ci_low`, `ci_high` | 권장 | `1.71`, `1.98` | 95% 신뢰구간 |
| `p` | 권장 | `1e-12` | |
| `n_exposed`, `n_cases` | 권장 | `52031`, `1840` | |
| `lag_years` | 선택 | `0`, `1`, `5` | 시간 창 |
| `selection` | 예 | `all_pairs` | `all_pairs`(전부) 또는 `significant_only` 등 선택 기준 |
| `cohort` | 예 | `NHIS-NSC 2002-2019` | 출처 |

장기는 후행 질환 코드로 정한다. ICD-10은 `axis_reliability.ICD_AXIS`, ICD-9은 `axis_source_compare.ICD9_AXIS`를 쓴다. 다른 체계면 같은 형태의 범위표를 만든다.

### 4-5. 받은 자료를 넣는 방법

1. loader를 만든다. `axis_dtb_augment.dtb_targets()`처럼 `(codes, names, T)`를 돌려준다(T: 질환 × 13장기, 결과 질환 평균 대비 초과 log 효과의 장기별 평균을 장기별 표준편차로 나눈 값, 없는 장기는 NaN).
2. 검증용이면 `axis_source_compare.py`의 심판(`hudine_targets`) 옆에 새 심판으로 추가해 Both, Den, Fin을 모두 채점한다.
3. 학습용이면 `specs`에 새 조합을 추가하고, **학습에 쓰지 않은 자료로** 비교한다.
4. 배포는 기준 통과 후 `axis_ensemble.py --write`로 모델 파일을 갱신하고, 관리자가 모델 릴리스를 만든다.

**채택 기준(제안):** 새 독립 자료에서 질환 내 순위 점수가 현재 Both 대비 paired CI 하한 > 0, 기존 세 자료 중 어디서도 유의하게 나빠지지 않음. 장기별로는 CI 하한 > 0인 장기만 표시.

주의: 이 모델은 "자연 경과에서 같이 생기는 질환"을 배운 것이지 ADC 독성을 배운 것이 아니다. 화면에서도 "추정"으로만 쓴다.

---

## 5. 추가 학습에 쓸 수 있는 데이터 형식 총정리

| 고치려는 부분 | 필요한 라벨 | 형식(예) | 최소 양 | 넣을 곳 | 읽는 코드 |
|---|---|---|---|---|---|
| 질환 → 장기 | 개념별 장기 | JSONL `{"id": "MONDO:...", "organs": [...], "scope": "axis\|no_axis\|unclear", "confidence", "reviewer", "note"}` | 300 (권장 1,000+) | `data/curated/concept_organs/labels/expert_*.jsonl` | `linking_models.load_organ_labels` |
| 질환 → 장기(규칙) | 상위 개념별 장기 | YAML `ancestor_to_axis: {MONDO:...: [axis]}` | 수정 단위 | `conf/ontology/mondo_organ_axis.yaml` | `mondo_index.build`, `linking_models` |
| 후보 재정렬, SapBERT | 입력 → 정답 개념 | JSONL `{"query": "ckd", "concept": "MONDO:0005300", "category": "abbrev", "lang": "en", "source": "..."}` | 2,000+ | `data/curated/train_queries/` 아래 새 파일 | 새 재정렬 스크립트, `sapbert_ft_v2.extra_pairs` 참고 |
| 질환 판별기 | 입력 → 유효 여부 | JSONL `{"text": "...", "label": "valid\|invalid\|ambiguous\|non_disease"}` | 500+ | `data/curated/train_queries/` | `linking_models.gate_training_set` |
| 약어 후보 | 약어 → 질환 목록 | TSV `약어<TAB>MONDO:...;MONDO:...` | 수정 단위 | 새 파일, `abbreviation_table` 병합 | `linking_models.abbreviation_table` |
| 한국어 입력 | 한국어 → 영어 질환명 | TSV `한국어<TAB>English name` | 수정 단위 | `data/curated/korean/lay_aliases.tsv` | `linking_models.korean_table` → `index3` |
| 평가(실제 입력) | 질의 + gold | 3-3의 두 파일 | 300+ | `data/curated/disease_linking/` | `eval_linking.py --queries --gold` |
| 학습 추정 | 질환 쌍 효과 | 4-4의 CSV | 질환 300개 이상 | `data/raw/<출처>/` | 새 loader → `axis_source_compare.py` |

모든 라벨 파일은 `reviewer`(누가)와 `source`(어디서)를 남긴다. 기계 라벨(LLM)과 사람 라벨은 파일 이름으로 구분한다(`expert_*`는 사람 검토만).

---

## 6. 데이터셋 목록 (묶음 `adctox-team-data.tar.gz`)

| 경로 | 내용 | 출처, 조건 | 쓰는 곳 |
|---|---|---|---|
| `data/curated/disease_linking/` | gold 600개, 후보 목록, 두 사람 라벨과 조정 결과 | 이 프로젝트(Claude Sonnet 라벨) | 모든 과제의 평가 |
| `data/curated/concept_organs/` | 개념별 장기 라벨 2,298개(사용분), 가이드, `review_queue.csv` | 이 프로젝트(Claude Haiku 라벨) | 과제 1 |
| `data/curated/train_queries/` | 생성 질의 2,200개와 검토 | 이 프로젝트(Haiku) | 과제 2 |
| `data/curated/korean/lay_aliases.tsv` | 한국어 일상어 → 영어 | 이 프로젝트 | 한국어 입력 |
| `data/raw_big/mondo/2026-10-07/` | MONDO 온톨로지, HPO 연관표 | CC BY 4.0 | 질환 사전, 장기 규칙 |
| `data/raw/hpo/` | Human Phenotype Ontology | CC BY 4.0, 출처 표시 | 증상 연결 |
| `data/raw/specialist_lrabr/LRABR` | NLM 약어 목록 | NLM 이용 조건(공개) | 약어 후보 |
| `data/raw/kcd/` | 심평원 상병마스터(한, 영) | 공공누리 1유형(출처 표시) | 한국어 입력 |
| `data/raw/ncbi_disease/` | NCBI Disease Corpus | 공개(NIH) | 과제 2 학습, 외부 평가 |
| `data/raw/bc5cdr/` | BioCreative V CDR | 연구 목적 공개 | 과제 2 |
| `data/raw/medmentions/` | MedMentions st21pv | CC0 | 과제 2, 개념 빈도 |
| `data/raw/dtb_siggaard2020/` | 덴마크 질환 궤적(77,294쌍) | CC BY 4.0 | 과제 4 (Both, Den 학습) |
| `data/raw/jensen_trajectories/` | 덴마크 궤적(Jensen 2014) | 논문 부록 | 참고(같은 등록자료라 독립 검증 아님) |
| `data/raw/hudine/` | 미국 Medicare 동반질환망(HuDiNe) | **학술 목적만** | 과제 4 심판 |
| `data/raw/icd9cm/` | CMS ICD-9-CM 이름 | 공공 | HuDiNe 이름 |
| `data/raw/DATASETS_2026-10-12.md` | 위 자료의 URL, 라이선스, 열 설명 | | |

묶음에 **없는** 것:
- **COMETA(Reddit 일상 표현):** 이용 동의서가 필요하다. 각자 받아 `data/raw/cometa/`에 둔다.
- **팀원 워크북(ADC DB, FinnGen 매핑):** 제공자가 가지고 있다. 원본 위치는 `data/raw/atlas/2026-10-10/`.
- **외부 mention 통합 파일(`data/curated/external/`):** `python ml/build_external_linking.py`로 다시 만든다.

cache 묶음 `adctox-team-cache.tar.gz`:
- 색인: `mondo_index.npz`(현재), `mondo_index.pre_v1.npz`(재생성 원본)
- 모델: `vuln_biolord.pt`(배포 모델), `vuln_biolord.finngen_axis_2026-10-12.pt`(Fin 모델)
- 연구용 표와 벡터: `finngen.parquet`(FinnGen 표), `emb_biolord.npz`, `sapbert.npz`(질환 이름 벡터)
- 판별기: `gate_v1.npz`
- 팀원 ADC DB에서 만든 표: `tox.pkl`, `master.pkl`

---

## 7. 제출 체크리스트

- [ ] 과제별 브랜치, PR 설명에 **실험 전에 정한 채택 기준**
- [ ] `ml/results/benchmarks/<이름>.json`과 `ml/docs/<이름>.md`(목적, 방법, 결과, 채택 여부, 실패 포함)
- [ ] gold test는 마지막에 한 번만 봤음
- [ ] 테스트 통과: `.venv/bin/python -m pytest tests/test_model_updates.py tests/test_terminal_layout.py tests/test_ml_recommender.py -q`
- [ ] 라벨 파일에 `reviewer`, `source` 기록, 재배포 제한 자료는 커밋하지 않음
- [ ] 앱에 들어가는 변경(색인 키, `link()` 수정)은 portable 빌드 테스트 통과

질문과 결과 공유는 PR 댓글로 한다. 모델 배포(색인, 모델 파일 교체와 릴리스)는 관리자가 한다.
