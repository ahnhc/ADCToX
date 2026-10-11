# ADC 독성 위험 추천기 (`ml/recommend.py`) — 구현 기술 보고서

> **이 보고서는 개정 전 구현(커밋 `2dfcf7f`)을 기술합니다.** 외부 검토 의견을 반영한 개정(투여 제한 분리, 데이터 정비, 점수 재설계, 학습 모델 기본 Off)은 `ml/docs/recommender_changes.md`에 있습니다. 아래 수식과 수치는 비교용 기록입니다.

작성일: 2026-10-11 · 대상 커밋: `2dfcf7f` + 작업 트리의 미커밋 변경(`ml/recommend.py`의 `render()`/`_summary()` 표시 부분만; 점수 계산 코드는 `2dfcf7f`와 동일)

이 문서는 **구현된 사실만** 기술한다. 코드는 수정하지 않았다. 모든 수치는 아래 스크래치 스크립트(읽기 전용)로 실제 코드·데이터에서 재계산했다.
원래 의도와 구현이 다르면 「의도 ≠ 구현」으로, 코드로 확인할 수 없는 것은 「확인 불가」로, 코드 밖의 의학 지식은 「의학적 관찰(코드와 무관)」로 표시한다.

> 재현 방법: 프로젝트 환경 `/data/hyeongchanahn/envs/adctox/bin/python`에서 `import recommend as RC; RC.recommend([...])`를 호출하면 아래 표의 숫자가 그대로 나온다. 중간값은 `RC.drug_table()`, `RC.patient_weights()`로 얻을 수 있다.

---

## 1. 전체 아키텍처 및 실행 흐름

### 1.1 한 줄 요약

**규칙 기반 점수 계산이 중심이고, 학습된 모델은 한 군데(환자 측 '연관 장기' 가중치)에만 보조로 쓰인다.**

| 구성요소 | 방식 | 위치 |
|---|---|---|
| ADC → 장기별 부담 `T[d,o]` | **규칙 기반**: FDA 라벨 경고 등급 + 라벨 이상반응 표의 Grade≥3 발생률 백분위 | `ml/matcher2.py`, `src/adctox/validation/label_change.py`, `ml/recommend.py:42-49` |
| 질환 → 자기 장기 취약도 | **수작업 테이블**(registry의 organ_axes, severity) | `conf/comorbidity_registry.csv`, `ml/recommend.py:51-55` |
| 질환 → 연관 장기 취약도 | **학습 모델**: BioLORD-2023(동결) 임베딩 + 2-tower MLP, 5-seed 앙상블, FinnGen으로 학습 | `ml/vulnerability_model.py`, 출력 `ml/results/learned_vulnerability.json` |
| 목록에 없는 질환 | 임베딩 유사도(BioLORD 코사인) + MONDO 온톨로지 링크(SapBERT 코사인) + 고정 심각도 | `ml/recommend.py:57-81`, `ml/mondo_index.py` |
| 결합·점수·정렬 | **고정 수식**(가중 평균 → 환자별 min-max 정규화 → 오름차순 정렬) | `ml/recommend.py:83-95` |

ADC의 구조(항체·링커·페이로드)는 점수에 **전혀 쓰이지 않는다.** 구조로 독성을 예측하는 과제는 이 데이터에서 학습되지 않는다는 결과가 나와서(`ml/README.md` Result 3) 약물 쪽은 '예측'이 아니라 '라벨 기록'으로 처리했다.

### 1.2 데이터 흐름 다이어그램

```mermaid
flowchart TD
  subgraph DrugSide[약물 측: 규칙 기반]
    DM[DailyMed 라벨 HTML 스냅샷<br>/data/hyeongchanahn/adctox/raw/dailymed/2026-10-07/<agent>/v*.html<br>14개 ADC, 각 최신 버전] --> LC[label_change.parse_version<br>h1 'WARNING...' → boxed 장기<br>h2 '5.x 제목' → section-5 장기]
    LC --> W[W(d,o) ∈ {0, 0.6, 1.0}]
    XL[팀원 제공 워크북 adc_db.xlsx<br>시트 TOXICITY → ml_cache/tox.pkl] --> INC[matcher2.incidence_table<br>Source type = 'Regulatory label via DailyMed'<br>Grade 3-4 / ≥3 / 3 / 4 행만]
    INC --> R[r(d,o) = 장기별 최대 Grade≥3 %]
    R --> P[P(d,o) = 12개 ADC 내 백분위<br>표 없는 ADC는 0.5]
    W --> T[T = W + (1−W)·0.4·P]
    P --> T
  end
  subgraph PatientSide[환자 측]
    IN[입력: registry ID / 라벨 / 자유 텍스트] --> REG{registry에 있음?}
    REG -- 예 --> OWN[own(c,o) = severity_c if o ∈ organ_axes_c]
    REG -- 아니오 --> FT[BioLORD 코사인 ≥0.80 → 그 registry 항목<br>아니면 MONDO 링크(≥0.75) → 심각도 0.8<br>아니면 코사인 ≥0.60 → 그 registry 항목<br>아니면 자기 장기 없음]
    FG[FinnGen HR 엑셀 → finngen.parquet] --> VM[vulnerability_model.py<br>BioLORD + TwoTower MLP ×5 seed]
    VM --> LV[learned_vulnerability.json<br>ℓ(c,o) ∈ [0,1]]
    VM -. 자유 텍스트는 실시간 predict .-> FT
    OWN --> SC[s(c,o) = max(own, f·ℓ), f=0.5]
    LV --> SC
    FT --> SC
    SC --> S[s(o) = max over 조건 c]
  end
  S --> WGT[w(o) = 1 + λ·s(o), λ=9]
  T --> RAW[raw(d) = 100·Σ w·T / Σ w]
  WGT --> RAW
  RAW --> RISK[Risk(d) = 100·(raw−min)/(max−min)]
  RISK --> OUT[오름차순 정렬 표<br>Primary/Secondary/Tertiary = T·w 상위 장기]
```

### 1.3 실행 흐름 (`ml/recommend.py:225-238`)

1. `--list`면 registry를 출력하고 종료한다(`list_conditions`, 97-101행).
2. 인자가 있으면 질문 없이 그 인자들을 질환으로 실행한다. `--raw`는 원점수 표시, `--lambda N`은 λ 변경(227-228행).
3. 인자가 없고 TTY이면 `wizard()`(198-210행)가 curses 메뉴(`ml/tui.py`)로 질환, λ, 연관 장기 비율, (자유 텍스트가 있으면) MONDO 심각도, 표시 장기 수, Risk 눈금, 색을 묻는다. 고른 값은 **모듈 전역변수**(`LAMBDA`, `LEARNED_FRACTION`, `MONDO_SEVERITY`, `N_ORGANS`)를 덮어쓴다. TTY가 아니면 번호 입력 방식(`_wizard_numbered`, 212-223행)으로 묻는다.
4. `recommend(conds)`(83-95행) → `render()`(105-131행).
5. 대화형이면 "Run again?"을 묻는다. 다시 실행해도 전역변수는 이전 선택값을 유지한다.

### 1.4 주요 파일과 역할

| 파일 | 역할 | 추천기 실행 시 사용 여부 |
|---|---|---|
| `ml/recommend.py` | 추천기 본체(점수, 표시, 메뉴) | 사용 |
| `ml/matcher2.py` | `warnings_table()`(30-41), `incidence_table()`(43-52), 상수 `W_BOXED=1.0, W_SEC5=0.6, W_INC=0.4`(28). `main()`은 평가 실험 | 함수만 import |
| `ml/matcher.py` | `AXES`(24), `DOM`(26-28: 워크북 도메인 → 장기), `auroc`, 경로 상수 `C`, `R`. `burden()`은 폐기된 v1 약물 측 | 상수만 import |
| `src/adctox/validation/label_change.py` | 라벨 HTML 파서. `HEADING_TO_AXIS`(38-69), `NOT_AN_ORGAN`(73-83), `axis_for_heading`(89-97), `parse_version`(112-151) | 사용 |
| `ml/vulnerability_model.py` | 학습 모델: 학습 `train()`(56-64), 예측 `predict()`(67-85), 임베딩 `_st()`(19-28) | 자유 텍스트 입력 시에만 실시간 호출. registry 입력은 JSON 사용 |
| `ml/lab.py` | `TwoTower`(60-66), `load_rows`(37-44), `table`(46-58), 실험 하네스 | 모델 클래스만 |
| `ml/results/learned_vulnerability.json` | 41개 registry 질환의 학습된 z와 severity | 사용 |
| `ml/mondo_index.py` | MONDO 인덱스 `build()`(25-69), `link()`(72-79), `THETA=0.75`(12) | 자유 텍스트 입력 시만 |
| `conf/comorbidity_registry.csv` | 41개 질환: id, label, organ_axes, severity, severity_basis, mondo_id, icd10_prefix, notes | 사용 |
| `conf/ontology/mondo_organ_axis.yaml` | MONDO 조상 이름 → 장기 매핑 | MONDO 인덱스를 만들 때만(`build`) |
| `ml/tui.py` | curses 메뉴 | 대화형일 때만 |
| `conf/hard_flags.yaml` | 라벨 기반 금기 플래그 5개 | **추천기에서 사용하지 않음**(v1 `matcher.py`만 사용) |
| `ml/learned_vulnerability.py` | 이전 SapBERT 버전의 학습 스크립트 | 사용하지 않음. 단, **출력 경로가 같아서**(20행 `OUT`) 다시 실행하면 BioLORD 결과를 덮어쓴다(§8) |

### 1.5 학습 모델 상세 (질환 → 장기 취약도)

- **학습 데이터**: FinnGen 선행질환→결과질환 위험비(hazard ratio) 워크북(`data/raw/atlas/2026-10-10/finngen_outcome_mapping.xlsx`, 시트 `Mapped_Data`, 팀원 제공, 2026-10-09 수령, sha256은 `_manifest.json`에 있음). 필터는 `qc_flag == "OK"`, `0 < HR ≤ 100`이고 남는 행은 59,157개다(`lab.load_rows`, `ml/lab.py:37-44`). 라이선스 방침상 HR 값은 이 보고서에 싣지 않는다(`docs/TEAMMATE_DATA_USE.md`).
- **목표변수**: `y = log(HR)` (선행질환 p, 결과질환 o, lag 구간 l 한 행마다).
- **입력**: 선행질환 이름과 결과질환 이름을 BioLORD-2023으로 임베딩한 768차원 벡터(정규화), 그리고 context one-hot.
- **구조**(`lab.TwoTower`): `a = GELU(Linear(768→256))(p)`, `b = GELU(Linear(768→256))(o)`(각각 dropout 0.25). 여기에 `head = Linear(3·256 + d_ctx → 256) → GELU → Dropout → Linear(256→1)`을 `[a, b, a⊙b, ctx]`에 적용한다.
- **학습**: Huber loss, AdamW(lr 3e-3, wd 1e-2), 배치 8192, 최대 200 epoch, 조기 종료(patience 15)를 쓴다. 검증셋은 선행질환 10%를 seed별로 무작위로 뗀다. y는 표준화한다. seed 0-4로 5개 모델을 만들고 평균한다(`vulnerability_model._train`, 36-54행). 최종 모델은 **전체 데이터로 학습**하며 별도 test set이 없다. 성능 수치는 `ml/lab.py`의 교차검증 실험에서 온다.
- **추론 → 장기 취약도**(`predict`, 67-85행):
  1. 질환 텍스트 x에 대해 193개 결과질환 o마다 모든 lag one-hot의 예측 평균과 5개 모델 평균을 낸다: `ŷ(x,o)`.
  2. `ex(x,o) = ŷ(x,o) − base(o)`. 여기서 `base(o)`는 학습 데이터에서 결과질환 o의 평균 log HR이다(59행).
  3. 장기 a에 대해 `z(x,a) = mean_{o∈a} ex(x,o) / spread(a)`. `spread(a)`는 학습 데이터에서 '(선행질환, 장기)별 평균 초과 log HR'이 선행질환들 사이에서 갖는 표준편차다(61행).
  4. `severity(x,a) = clip(z(x,a) − median_a z(x,·), 0, 1)` (83행). 질환마다 중앙값을 빼므로, 질환이 모든 장기 위험을 올리는 효과는 지워지고 상대적으로 튀는 장기만 남는다. 1 SD를 꽉 찬 값(1.0)으로 보는 것은 선택이며 적합한 값이 아니다.
- **검증 결과**(`ml/README.md`, `ml/results/*.json`): 이 수치는 `lab.py` 교차검증에서 온 것이다.
  - unseen ICD family 기준 BioLORD 동결: R² 0.655, 장기 순위 이득(lookup 대비) +0.057 [+0.033, +0.085](비교: SapBERT 0.622).
  - 학습 없는 kNN이 장기 순위 지표에서 MLP와 차이가 없다.
  - registry 41개 sanity check AUROC는 0.80-0.86이다. 단, 이는 '자기 장기 회복'을 본 것이고 교차 장기 취약도를 검증한 것이 아니다.
  - **추천에 쓰였을 때의 비순환 검증에서는 우연 수준과 구별되지 않았다**: 발생률만 쓴 경우 0.462 vs 가중치 없음 0.429, 차이 +0.033 [−0.018, +0.087].
- **구현 결함(이번 분석에서 발견, §8.1-C)**: 학습 시 context에서 domain one-hot이 잘려 나가 lag one-hot만 들어가지만(`vulnerability_model.py:40`, `lab.py:85`), 추론 시에는 domain 비트를 1로 채운다(`vulnerability_model.py:76`). 실측 영향은 작다(41개 질환 평균 |severity 차| ≤ 0.011, top-1 일치율 동일 0.512).

---

## 2. 데이터 출처 및 데이터베이스 구조

### 2.1 출처 목록

| 데이터 | 실제 파일 | 출처 | 수동/자동 | 날짜 추적 |
|---|---|---|---|---|
| 라벨 경고(boxed, section 5) | `/data/hyeongchanahn/adctox/raw/dailymed/2026-10-07/<agent>/v<N>.html` + `_manifest.json` | DailyMed SPL(setid, 버전, 날짜, sha256이 manifest에 있음). fetched_at 2026-10-07T07:56:57Z | **자동 파싱**(정규식) | manifest에는 버전 날짜가 있지만 **추천기는 날짜를 사용하거나 출력하지 않는다**(`matcher2.py:34`가 `date=None`으로 호출). 경로의 스냅샷 날짜(2026-10-07)는 하드코딩되어 있다 |
| 라벨 이상반응 표 Grade≥3 % | `data/raw/atlas/2026-10-10/adc_db.xlsx` 시트 TOXICITY → `ml_cache/tox.pkl` | 팀원 제공 워크북(2026-10-09 수령). 행마다 `Source`(DailyMed setid URL), `Source table`(표 이름과 행 번호), `Source cell verbatim`이 있다 | 워크북 **작성 방식은 확인 불가**(수동 전사인지 자동 추출인지 코드로 알 수 없다). 우리 코드는 필터·집계만 한다 | 행에 setid는 있지만 **라벨 버전/날짜가 없다**. 경고에 쓴 라벨 버전과 같은 버전에서 전사됐는지는 확인 불가 |
| ADC 이름 | 같은 워크북 시트 ADC_MASTER → `ml_cache/master.pkl` | 팀원 워크북 | – | – |
| 질환 → 장기, 심각도 | `conf/comorbidity_registry.csv` | 프로젝트 저장소. 커밋 `25d48e9`(2026-10-07)에 추가됐고 `5eb2f6d`에서 MONDO 핀을 수정했다. `severity_basis` 열에 근거가 자유 텍스트로 적혀 있다(예: "Child-Pugh B/C excluded", "CrCl < 30 excluded") | **수동** | 문헌 인용이 없다. 근거 문장의 출처는 확인 불가 |
| 학습된 연관 장기 | `ml/results/learned_vulnerability.json` | FinnGen 워크북으로 학습한 모델 | 자동(학습) | 생성 스크립트 `ml/vulnerability_model.py` |
| MONDO | `data/raw_big/mondo/2026-10-07/mondo.obo` → `ml_cache/mondo_index.npz` | MONDO v2026-10-06, CC BY 4.0 | 자동 | yaml에 snapshot 날짜가 있다 |

### 2.2 FDA 라벨에서 실제로 쓰는 항목

| 라벨 항목 | 처리 |
|---|---|
| **Boxed Warning** | 첫 번째 `<h1>` 중 텍스트가 "WARNING"으로 시작하는 것의 **제목 문자열만** 쓴다(`label_change.py:115-120`). 이를 `\band\b`, `,`, `;`로 쪼갠 각 조각에 `axis_for_heading`을 적용한다(143-146행). 박스 **본문은 읽지 않는다.** |
| **Warnings and Precautions (section 5)** | `<h2>` 중 "5.N 제목" 형태인 것의 **제목만** 쓴다(122-127행). 제목 하나는 첫 번째로 맞는 정규식의 장기 하나로만 매핑된다. 본문은 읽지 않는다. |
| **Adverse Reactions (section 6)** | 라벨 HTML을 직접 파싱하지 않는다. **워크북에 전사된 표 행**을 쓴다(`Source type == "Regulatory label via DailyMed"`, `Canonical observation == True`). Grade 3-4 / Grade ≥3 / Grade 3 / Grade 4 행만 쓰고 Any grade, Grade 2-4, Grade 5는 쓰지 않는다. |
| **Use in Specific Populations (section 8; 8.6 신장애, 8.7 간장애)** | **사용하지 않는다.** |
| **Contraindications (section 4)** | **사용하지 않는다.** |
| Dosage and Administration(용량 조절) | **사용하지 않는다.** |
| Clinical Pharmacology(PK) | **사용하지 않는다.** |

신장·간 기능 장애 관련 정보는 section-5 **제목**에 들어 있을 때만 우연히 반영된다. 실제로 브렌툭시맙의 "5.6 Increased Toxicity in the Presence of Severe Renal Impairment"는 renal W&P로, "5.7 … Hepatic Impairment"는 hepatic W&P로 잡힌다. 다른 ADC의 8.6/8.7 권고(데이터 부족, 투여 회피 등)는 반영되지 않는다.

**발생률과 중증도**: Grade≥3 발생률만 반영한다. 사망(Grade 5)과 any-grade 빈도는 반영하지 않는다. 중증도는 '경고 등급(boxed/W&P)'과 'Grade≥3로 한정한 것'으로만 간접적으로 들어간다.

### 2.3 ADC별 데이터 대응표

추천 대상 ADC는 **DailyMed 스냅샷 폴더에 있는 14개**다(`recommend.drug_table`: `ids = sorted(wt)`). 워크북에는 표가 있지만 라벨 폴더가 없는 belantamab mafodotin과 moxetumomab pasudotox는 **제외**된다.

| ADC (id) | 상표 | DailyMed setid | 사용 버전 / 날짜 | boxed 제목 → 장기 | 워크북 Grade≥3 행 수 / 표 수 | 워크북 setid 일치 | 비고 |
|---|---|---|---|---|---|---|---|
| brentuximab-vedotin | ADCETRIS | 3904f8dd… | v38 / Nov 17, 2025 | PML → neurologic | 9 / 9 | 일치 | 단독요법 행 |
| datopotamab-deruxtecan | DATROWAY | 2950227c… | v18 / Jun 03, 2026 | 없음 | 53 / 53 | 일치 | |
| enfortumab-vedotin | PADCEV | b5631d3e… | v18 / Aug 17, 2026 | SERIOUS SKIN REACTIONS → dermatologic | 75 / 75 | 일치 | 46행이 병용(Monotherapy=No) |
| gemtuzumab-ozogamicin | MYLOTARG | 32fd2bb2… | v19 / Dec 22, 2025 | HEPATOTOXICITY → hepatic | **없음** | – | 백분위 0.5로 대체 |
| inotuzumab-ozogamicin | BESPONSA | cc7014b1… | v8 / Feb 09, 2026 | HEPATOTOXICITY/VOD → hepatic (post-HSCT NRM 조각은 비장기로 제외) | 83 / 83 | 일치 | |
| loncastuximab-tesirine | ZYNLONTA | af54af12… | v15 / Jun 17, 2026 | 없음 | 6 / 6 | 일치 | 표가 매우 적다 |
| mirvetuximab-soravtansine | ELAHERE | 00c424b5… | v14 / Feb 16, 2026 | OCULAR TOXICITY → ocular | 61 / 61 | 일치 | |
| pivekimab-sunirine | DECNUPAZ | 508b6ff8… | v2 / Jun 01, 2026 | HEPATOTOXICITY/VOD → hepatic | **없음** | – | 백분위 0.5로 대체. ADC_MASTER에 없어 이름을 id에서 만든다 |
| polatuzumab-vedotin | POLIVY | 20a16ab2… | v15 / Aug 28, 2026 | 없음 | 60 / 60 | 일치 | **60행 전부 병용**(R-CHP 등) |
| sacituzumab-govitecan | TRODELVY | 57a597d2… | v20 / Jun 29, 2026 | NEUTROPENIA AND DIARRHEA → **haematologic만**(§8.1-A 버그) | 96 / 96 | 일치 | |
| telisotuzumab-vedotin | EMRELIS | bc04f980… | v3 / Jul 10, 2025 | 없음 | 30 / 30 | 일치 | |
| tisotumab-vedotin | TIVDAK | c9fe3f32… | v10 / Nov 21, 2025 | OCULAR TOXICITY → ocular | 60 / 60 | 일치 | |
| trastuzumab-deruxtecan | ENHERTU | 7e67e73e… | v28 / May 28, 2026 | ILD and EMBRYO-FETAL → pulmonary | 299 / 299 | 일치 | 47행 병용 |
| trastuzumab-emtansine | KADCYLA | 23f3c1f4… | v35 / Apr 03, 2026 | HEPATOTOXICITY, CARDIAC TOXICITY, EMBRYO-FETAL → hepatic, cardiovascular | 77 / 63 | 일치 | Grade 3과 4 행을 두 시험(EMILIA, KATHERINE)에 걸쳐 합산함(§8.1-B) |

워크북 행의 setid는 경고를 읽은 DailyMed 라벨과 모두 같은 제품이다. **같은 버전인지는 확인 불가**하다.

### 2.4 Section-5 제목 → 장기 (파싱 결과 전체)

`python`으로 `parse_version`을 직접 실행한 결과다(boxed는 위 표에 있음). 제목 옆이 매핑된 장기이고, `None`은 비장기로 제외된 것이다.

- **brentuximab**: 5.1 Peripheral Neuropathy→neurologic, 5.2 Anaphylaxis and Infusion Reactions→infectious_immune, 5.3 Hematologic Toxicities→haematologic, 5.4 Serious/Opportunistic Infections→infectious_immune, 5.5 Tumor Lysis Syndrome→metabolic_endocrine, 5.6 Increased Toxicity … Severe Renal Impairment→renal, 5.7 … Hepatic Impairment→hepatic, 5.8 Hepatotoxicity→hepatic, 5.9 PML→neurologic, 5.10 Pulmonary Toxicity→pulmonary, 5.11 Serious Dermatologic Reactions→dermatologic, 5.12 GI Complications→gastrointestinal, 5.13 Hyperglycemia→metabolic_endocrine, 5.14 Embryo-Fetal→None
- **datopotamab**: 5.1 ILD/Pneumonitis→pulmonary, 5.2 Ocular Adverse Reactions→ocular, 5.3 Stomatitis→gastrointestinal, 5.4 Embryo-Fetal→None
- **enfortumab**: Skin Reactions→dermatologic, Hyperglycemia→metabolic_endocrine, Pneumonitis/ILD→pulmonary, Peripheral Neuropathy→neurologic, Ocular Disorders→ocular, Infusion Site Extravasation→None, Embryo-Fetal→None
- **gemtuzumab**: Hepatotoxicity incl. VOD→hepatic, Infusion-Related Reactions→infectious_immune, Hemorrhage→cardiovascular, QT Prolongation→cardiovascular, AML Adverse-Risk Cytogenetics→None, Embryo-Fetal→None
- **inotuzumab**: Hepatotoxicity/VOD→hepatic, Post-Transplant NRM→None, Myelosuppression→haematologic, Infusion Related Reactions→infectious_immune, QT Prolongation→cardiovascular, Embryo-Fetal→None
- **loncastuximab**: Effusion and Edema / Capillary Leak→cardiovascular, Myelosuppression→haematologic, Infections→infectious_immune, Hepatotoxicity→hepatic, Cutaneous Reactions→dermatologic, Embryo-Fetal→None
- **mirvetuximab**: Ocular Disorders→ocular, Pneumonitis→pulmonary, Peripheral Neuropathy→neurologic, Embryo-Fetal→None
- **pivekimab**: Hepatotoxicity/VOD→hepatic, Infusion-Related Reactions→infectious_immune, Edema→cardiovascular, Sulfite Allergic Reactions→infectious_immune, Embryo-Fetal→None
- **polatuzumab**: Peripheral Neuropathy→neurologic, Infusion-Related Reactions→infectious_immune, Myelosuppression→haematologic, Serious and Opportunistic Infections→infectious_immune, PML→neurologic, Tumor Lysis→metabolic_endocrine, Hepatotoxicity→hepatic, Infusion Site Extravasation→None, Embryo-Fetal→None
- **sacituzumab**: Neutropenia→haematologic, Diarrhea→gastrointestinal, Hypersensitivity/IRR→infectious_immune, Nausea and Vomiting→gastrointestinal, Reduced UGT1A1 Activity→metabolic_endocrine, Embryo-Fetal→None
- **telisotuzumab**: Peripheral Neuropathy→neurologic, ILD/Pneumonitis→pulmonary, Ocular Surface Disorders→ocular, IRR→infectious_immune, Embryo-Fetal→None
- **tisotumab**: Ocular Adverse Reactions→ocular, Peripheral Neuropathy→neurologic, Hemorrhage→cardiovascular, Pneumonitis→pulmonary, Severe Cutaneous Adverse Reactions→dermatologic, Embryo-Fetal→None
- **trastuzumab deruxtecan**: ILD/Pneumonitis→pulmonary, Neutropenia→haematologic, Left Ventricular Dysfunction→cardiovascular, Embryo-Fetal→None
- **trastuzumab emtansine**: Hepatotoxicity→hepatic, LV Dysfunction→cardiovascular, Embryo-Fetal→None, Pulmonary Toxicity→pulmonary, IRR/Hypersensitivity→infectious_immune, Hemorrhage→cardiovascular, Thrombocytopenia→haematologic, Neurotoxicity→neurologic, Extravasation→None

모든 라벨에서 `unmapped`(매핑 실패)는 0건이다. boxed 경고가 없는 5개 라벨(datopotamab, loncastuximab, polatuzumab, telisotuzumab 등)에서는 `<h1>WARNINGS AND PRECAUTIONS</h1>`이 "boxed 제목"으로 잡힌다. 다만 장기가 하나도 매핑되지 않으므로 결과에는 영향이 없다(§8.1-F).

---

## 3. 질환-장기 취약도 매핑 알고리즘

### 3.1 입력 해석 (`patient_weights`, `ml/recommend.py:57-81`)

입력 문자열 c는 다음 순서로 해석한다.

1. `c`가 registry `id`와 정확히 같거나, `c.lower()`가 registry `label`의 소문자와 같으면 → **registry 경로**(69-71행).
2. 그 밖은 **자유 텍스트 경로**(72-80행):
   - `sims = BioLORD(c) · BioLORD(registry label)`(정규화된 코사인), `k = argmax`.
   - `sims[k] ≥ REG_NEAR(0.80)` → registry 항목 k의 자기 장기와 severity를 쓴다.
   - 아니면 MONDO 링크(`mondo_index.link`: SapBERT CLS 임베딩 코사인으로 MONDO 이름과 EXACT 동의어 중 최근접을 찾음)의 `sim ≥ THETA(0.75)`이고 장기가 하나 이상이면 → 그 장기들에 `MONDO_SEVERITY(0.80)`을 준다.
   - 아니면 `sims[k] ≥ MATCH_COS(0.60)` → registry 항목 k의 자기 장기를 빌려 온다.
   - 아니면 자기 장기 없음(학습값만).
   - 학습값 `ℓ`은 `VM.predict([c])`로 실시간 계산한다.
3. 부분 문자열, 동의어, 약어 매칭은 없다(registry 경로는 완전 일치만).

### 3.2 질환별 벡터

장기 집합 `A` = {haematologic, hepatic, cardiovascular, pulmonary, renal, gastrointestinal, neurologic, ocular, dermatologic, metabolic_endocrine, musculoskeletal, infectious_immune, otologic} (13개, `matcher.py:24`).

조건 c, 장기 o에 대해:

```
own(c,o)  = severity_c   if o ∈ organ_axes_c   else 0            # recommend.py:51-55, registry 값
ℓ(c,o)    = learned severity (learned_vulnerability.json)         # [0,1]
s(c,o)    = max( own(c,o),  f · ℓ(c,o) ),   f = LEARNED_FRACTION = 0.5     # recommend.py:71 / 80
```

### 3.3 여러 질환의 결합

```
s(o) = max_c s(c,o)              # recommend.py:81  np.maximum.reduce
```

**합산하지 않고 최댓값을 쓴다.** 따라서:
- 같은 장기의 질환을 여러 개 넣어도 그 장기 값은 가장 큰 severity 하나다. 중복으로 부풀지 않는다.
- 다만 질환을 하나 더할 때마다 다른 장기의 `f·ℓ` 후보가 늘어난다. `s`는 입력이 늘수록 **단조 증가만** 하고 줄지 않는다. 중복 입력도 교차 장기 가중치는 바꾼다(§6.6).
- 포함 관계(예: CKD 4-5 ⊂ CKD, 투석 ⊂ CKD 5)를 인식하는 로직은 **없다.** max 연산 때문에 결과적으로 큰 값이 남을 뿐이다.

### 3.4 가중치(severity) 근거

- registry `severity`(0.4-1.0)는 **수작업 값**이다. `severity_basis` 열의 문장은 주로 "임상시험 제외기준에서 흔한가"를 근거로 한다(예: `ckd_stage_3` 0.7 "CrCl < 30-60 floors common", `ckd_stage_4_5` 1.0 "CrCl < 30 excluded"). 수치를 정한 공식이나 문헌은 확인 불가다. 저장소 테스트 `tests/test_severity_is_a_preference.py`라는 이름이 시사하듯, 프로젝트 자체가 이 값을 '선호(preference)'로 다룬다.
- `f = 0.5`: 코드 주석(7-8행)은 "half the learned"라고만 말한다. 이 값을 고른 실험은 저장소에 **없다**(휴리스틱).
- `MONDO_SEVERITY = 0.8`: 주석은 "one fixed value, not fitted"(35행).

### 3.5 중증도·검사 수치

- **검사 수치(eGFR, CrCl, LVEF, Child-Pugh, 빌리루빈 등)는 입력받지 않는다.** 중증도는 registry 항목이 갈라 놓은 범주(ckd_stage_3 vs ckd_stage_4_5 등)의 severity로만 들어간다.
- 같은 장기 안의 중증도 차이는 `own`에만 반영된다. 학습값 ℓ은 질환 이름 텍스트에서 나오므로 단계 구분이 약하다(아래 표에서 ckd_stage_3의 renal ℓ=0.736 > ckd_stage_4_5 0.627).

### 3.6 요청된 조합의 실제 계산

`learned_vulnerability.json`에서 읽은 실제 값이다(표시는 0인 장기 생략).

**(a) ckd_stage_3 + ckd_stage_4_5 + dialysis**

| 장기 | ckd_stage_3 s | ckd_stage_4_5 s | dialysis s | **max** |
|---|---|---|---|---|
| renal | max(0.7, 0.5·0.736)=**0.700** | max(1.0, 0.314)=**1.000** | max(1.0, 0.324)=**1.000** | **1.000** |
| haematologic | 0.5·0.629=0.315 | 0.286 | 0.220 | 0.315 |
| neurologic | 0.294 | 0.203 | 0.157 | 0.294 |
| cardiovascular | 0.087 | 0.002 | 0.206 | 0.206 |
| gastrointestinal | 0 | 0.204 | 0.103 | 0.204 |
| metabolic_endocrine | 0.093 | 0.047 | 0.042 | 0.093 |
| ocular | 0.037 | 0 | 0 | 0.037 |

→ renal은 1.0 하나로 끝난다(합산 없음). 세 개를 넣은 것과 `ckd_stage_4_5` 하나만 넣은 것의 차이는 교차 장기 값(haem 0.286→0.315, neuro 0.203→0.294, cardio 0.002→0.206 등)뿐이다. 이 차이만으로도 순위가 바뀐다(§6.6: 4_5 단독에서는 loncastuximab이 3위, 세 개를 넣으면 pivekimab/gemtuzumab이 3위).

**(b) heart_failure + reduced_lvef**

| 장기 | heart_failure s | reduced_lvef s | **max** |
|---|---|---|---|
| cardiovascular | max(1.0, 0.5)=1.000 | max(1.0, 0.5)=1.000 | **1.000** |
| metabolic_endocrine | 0.420 | 0.291 | 0.420 |
| neurologic | 0.219 | 0.427 | 0.427 |
| haematologic | 0.349 | 0.373 | 0.373 |
| pulmonary | 0.303 | 0.368 | 0.368 |
| renal | 0.301 | 0.007 | 0.301 |

→ 심혈관은 1.0이다(중복 효과 없음). `reduced_lvef`가 neurologic과 pulmonary를 올려서 HF 단독과 순위가 달라진다(§6.6).

### 3.7 데이터가 없는 질환

- registry에 없는 텍스트는 §3.1의 대체 경로를 탄다. 모든 경로가 실패해도 학습값 `f·ℓ`은 항상 있다. 모델은 어떤 텍스트에도 값을 낸다.
- 학습값이 0인 장기(질환 중앙값 이하인 장기)는 `w=1`로 기본 가중치만 받는다.
- 노출력(prior_anthracycline, prior_chest_radiation 등)은 registry상 `MONDO:0000001`(root "disease")로 핀 되어 있다. 학습 모델에는 "Prior anthracycline exposure"라는 텍스트가 들어간다. 실제 학습값에는 **cardiovascular가 0**이다(z 1.241 < 중앙값 1.520). 즉 모델은 안트라사이클린 심독성을 알지 못하고, 심혈관 0.6은 registry 수작업 값에서만 온다.

---

## 4. ADC-장기 독성 매핑 알고리즘

### 4.1 장기 분류 체계

13개 축(§3.2)이다. 라벨 파서에는 `constitutional` 축도 있지만 `AXES`에 없어서 버려진다. 생식독성(Embryo-Fetal)은 `NOT_AN_ORGAN`으로 제외된다.

### 4.2 경고 층 `W[d,o]` (`matcher2.warnings_table`, 30-41행)

```
W[d,o] = 1.0   if o ∈ boxed_axes(d)                     # 39행 (덮어씀)
       = 0.6   elif o ∈ section5_axes(d)                # 37행
       = 0     otherwise
```

- 장기 하나에 W&P 제목이 여러 개 있어도 0.6 하나다(개수 무시).
- 매핑 규칙(`HEADING_TO_AXIS`, 위에서부터 **첫 번째로 맞는 패턴 하나**):
  - pulmonary: interstitial lung | pneumonitis | pulmonary tox | respiratory
  - hepatic: hepatotox | hepatic | veno-occlusive | sinusoidal obstruction | liver
  - haematologic: neutropeni | thrombocytopeni | anemia | myelosuppress | hematologic | cytopeni | leukopeni | bone marrow
  - neurologic: peripheral neuropath | neurotox | neurologic | progressive multifocal | leukoencephalopath | demyelinat
  - ocular: ocular | keratopath | corneal | eye | visual | blurred vision
  - cardiovascular(1): cardiomyopath | cardiac | left ventricular | ejection fraction | QT prolong
  - cardiovascular(2): hemorrhage | bleeding | thrombosis/embol | capillary leak | hypotension | vascular | effusion | edema
  - renal: renal | nephrotox | kidney
  - gastrointestinal: gastrointestinal | diarrh | colitis | pancreatitis | bowel | stomatitis | mucositis | nausea | vomiting
  - dermatologic: dermatolog | cutaneous | skin | stevens-johnson | toxic epidermal | rash | alopecia
  - metabolic_endocrine: hyperglyc | hypoglyc | diabet | endocrine | metabol | tumor lysis | thyroid | ugt1a
  - infectious_immune: infection | opportunistic | sepsis | immunosuppress | hepatitis b
  - otologic: ototox | hearing | audi
  - infectious_immune: infusion reaction | hypersensitivity | anaphyla | sulfite allergic
  - constitutional(버려짐): fatigue | pyrexia | fever | asthenia
- **하나의 독성이 여러 장기에 영향을 주는 경우**: 제목 하나는 장기 하나로만 간다. 예를 들어 "Nausea and Vomiting"은 GI 하나다. 한 제목에 두 장기가 섞여 있으면 패턴 순서상 앞선 장기만 남는다. boxed 제목은 `and`, `,`, `;`로 쪼개므로 여러 장기가 가능하다. 다만 `and`는 **소문자만** 인식한다(§8.1-A).

### 4.3 발생률 층 (`matcher2.incidence_table`, 43-52행)

워크북 TOXICITY 시트에서 `Canonical observation == True`, `Source type == "Regulatory label via DailyMed"`이고 `Incidence percent`가 숫자인 행만 쓴다. 용어는 `term = lower(strip(Raw AE term))`로 정규화한다.

```
cum(d,τ,dom)  = max  pct  over rows with Grade ∈ {"Grade 3-4", "Grade >=3"}        # 47행
part(d,τ,dom) = sum  pct  over rows with Grade ∈ {"Grade 3", "Grade 4"}            # 48행 (모든 표에 걸쳐 합산)
r(d,τ,dom)    = max(cum, part)                                                     # 49행
axis(dom)     = DOM[ 첫 '/' 앞 도메인 ]     (matcher.py:26-28)                       # 50행
r(d,o)        = max_{τ: axis=o} r(d,τ) / 100,   해당 행이 없으면 0                     # 51행
```

- `DOM` 매핑: Cardiac/Vascular→cardiovascular, Skin→dermatologic, Metabolic/Endocrine→metabolic_endocrine, Renal→renal, Hematologic→haematologic, Pulmonary→pulmonary, Ocular→ocular, Hepatic→hepatic, GI→gastrointestinal, Neurologic→neurologic, Musculoskeletal→musculoskeletal, Infection/Immune→infectious_immune.
- **버려지는 도메인**(Grade≥3 행 기준): General(57행), Investigations(32), Unspecified site(7), Psychiatric(3).
- 도메인은 **워크북에 이미 적힌 값**이고 우리 코드가 분류하지 않는다. 그래서 실험실 이상치가 장기로 들어간다. 예: "increased amylase"는 GI(Dato-DXd GI 38%의 출처), "creatinine increased"는 renal, "urinary tract infection"은 renal(tisotumab renal 5%), "pneumonia"는 pulmonary(polatuzumab 16%), "decreased potassium"은 metabolic.
- 적응증·용량·단독/병용(`Monotherapy` 열)을 **구분하지 않고** 모든 표의 최댓값을 쓴다. polatuzumab의 표는 전부 병용요법(R-CHP 등)이다.

**백분위** (`recommend.drug_table`, 42-49행):

```
D_tab = 라벨 표가 있는 ADC (12개)
P(d,o) = rank_avg( r(·,o) over D_tab )_d / |D_tab|      d ∈ D_tab      # 46행, pandas rank(pct=True, method="average")
P(d,o) = 0.5                                             d ∉ D_tab (gemtuzumab, pivekimab)    # 45행
T(d,o) = W(d,o) + (1 − W(d,o)) · 0.4 · P(d,o)                                                # 47행
```

결과적으로 T는 다음 범위에 있다.
- boxed: T = 1.0
- W&P: T ∈ [0.6 + 0.16·(1/12), 0.76] = [0.613, 0.76]
- 경고 없음: T ∈ [0.033, 0.40]

### 4.4 '데이터 없음'의 처리 (위험도 0인가?)

**아니다. T는 절대 0이 되지 않는다(최솟값 0.0333).** 순위 백분위는 동점을 평균 순위로 처리하므로 다음과 같이 된다.

| 상황 | 예 | P | T(경고 없음) |
|---|---|---|---|
| 표에 그 장기의 Grade≥3 행이 없고, 12개 중 11개가 0 | cardiovascular(inotuzumab만 4%) | 6/12 = 0.50 | **0.200** |
| 12개 모두 0 | otologic | 6.5/12 = 0.542 | **0.217** (모든 ADC 동일) |
| 12개 중 4개가 0 | renal(dato, ino, lonca, mirv) | 2.5/12 = 0.208 | **0.083** |
| 라벨 표 자체가 없음 | gemtuzumab, pivekimab | 0.5 (모든 장기) | **0.200** |

같은 "0%"라도 장기마다 T가 다르다(0.083 / 0.2 / 0.217). 이는 그 장기에서 **다른 ADC 몇 개가 0인지**에 따라 정해지는 산술적 부산물이다.

### 4.5 계산된 행렬 (실제 값)

**W (경고 층)**: 1.0 = boxed, 0.6 = W&P

| ADC | haem | hep | cardio | pulm | renal | GI | neuro | ocular | derm | metab | musc | infect | oto |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Brentuximab | .6 | .6 | 0 | .6 | .6 | .6 | **1** | 0 | .6 | .6 | 0 | .6 | 0 |
| Datopotamab | 0 | 0 | 0 | .6 | 0 | .6 | 0 | .6 | 0 | 0 | 0 | 0 | 0 |
| Enfortumab | 0 | 0 | 0 | .6 | 0 | 0 | .6 | .6 | **1** | .6 | 0 | 0 | 0 |
| Gemtuzumab | 0 | **1** | .6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | .6 | 0 |
| Inotuzumab | .6 | **1** | .6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | .6 | 0 |
| Loncastuximab | .6 | .6 | .6 | 0 | 0 | 0 | 0 | 0 | .6 | 0 | 0 | .6 | 0 |
| Mirvetuximab | 0 | 0 | 0 | .6 | 0 | 0 | .6 | **1** | 0 | 0 | 0 | 0 | 0 |
| Pivekimab | 0 | **1** | .6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | .6 | 0 |
| Polatuzumab | .6 | .6 | 0 | 0 | 0 | 0 | .6 | 0 | 0 | .6 | 0 | .6 | 0 |
| Sacituzumab | **1** | 0 | 0 | 0 | 0 | .6 | 0 | 0 | 0 | .6 | 0 | .6 | 0 |
| Telisotuzumab | 0 | 0 | 0 | .6 | 0 | 0 | .6 | .6 | 0 | 0 | 0 | .6 | 0 |
| Tisotumab | 0 | 0 | .6 | .6 | 0 | 0 | .6 | **1** | .6 | 0 | 0 | 0 | 0 |
| T-DXd | .6 | 0 | .6 | **1** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| T-DM1 | .6 | **1** | **1** | .6 | 0 | 0 | .6 | 0 | 0 | 0 | 0 | .6 | 0 |

**r: 장기별 최대 Grade≥3 %** (— = 라벨 표 없음)

| ADC | haem | hep | cardio | pulm | renal | GI | neuro | ocular | derm | metab | musc | infect | oto |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Brentuximab | 49 | 0.9 | 0 | 0 | 2.8 | 0 | 0 | 0 | 0 | 7.0 | 0 | 0 | 0 |
| Datopotamab | 11 | 2.4 | 0 | 0 | 0 | 38 | 0 | 6.0 | 0.6 | 3.5 | 0.6 | 1.4 | 0 |
| Enfortumab | 17 | 9.0 | 0 | 0 | 8.0 | 32 | 0 | 0 | 0 | 19 | 0 | 0 | 0 |
| Gemtuzumab | — | — | — | — | — | — | — | — | — | — | — | — | — |
| Inotuzumab | 96 | 27 | 4.0 | 4.0 | 0 | 13 | 2.0 | 0 | 4.0 | 11 | 2.0 | 28 | 0 |
| Loncastuximab | 30 | 21 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 8.0 | 0 | 0 | 0 |
| Mirvetuximab | 7.0 | 2.0 | 0 | 0.5 | 0 | 7.0 | 4.0 | 11 | 0 | 4.0 | 1.0 | 0 | 0 |
| Pivekimab | — | — | — | — | — | — | — | — | — | — | — | — | — |
| Polatuzumab | 87 | 1.4 | 0 | 16 | 4.4 | 9.0 | 1.6 | 0 | 0.7 | 18 | 0.5 | 2.2 | 0 |
| Sacituzumab | 53 | 4.1 | 0 | 0 | 2.3 | 0 | 0 | 0 | 0 | 7.8 | 0 | 0 | 0 |
| Telisotuzumab | 10 | 4.8 | 0 | 6.0 | 1.2 | 0.6 | 11 | 1.2 | 0 | 4.8 | 0 | 0 | 0 |
| Tisotumab | 7.0 | 3.3 | 0 | 0 | 5.0 | 4.0 | 7.0 | 3.2 | 1.6 | 2.1 | 1.0 | 0 | 0 |
| T-DXd | 51 | 9.0 | 0 | 2.4 | 1.9 | 8.0 | 0.5 | 0 | 0.6 | 20 | 1.3 | 0.9 | 0 |
| T-DM1 | 23* | 8.3 | 0 | 0.8 | 0.3 | 1.6 | 2.2 | 0 | 0 | 5.5 | 1.8 | 0 | 0 |

\* T-DM1 haem 23%는 두 시험의 Grade 3과 Grade 4를 합한 값(14+3+4+2)이다. 표 하나 기준 최대는 17%다(§8.1-B).
주목할 점: **sacituzumab GI가 0**이다. 라벨에는 diarrhea가 boxed인데도 그렇다. 워크북의 sacituzumab GI Grade≥3 행은 출처가 논문(`Primary clinical publication`)으로 표시되어 있어 라벨 필터에서 빠진다(§8.3-7). Dato-DXd GI 38은 amylase 증가다.

각 값의 출처 용어(상위)는 다음과 같다.
- Brentuximab haem: neutrophils decreased 49 / renal: creatinine increased 2.8
- Dato-DXd GI: increased amylase 38, stomatitis 8 / ocular: keratitis 6
- Mirvetuximab ocular: keratopathy 11, blurred vision 9 / neuro: peripheral neuropathy 4
- Telisotuzumab neuro: peripheral neuropathy 11 / pulm: pneumonia 6, ILD 3.6 / renal: creatinine 1.2
- Sacituzumab haem: decreased neutrophil count 53 / renal: decreased CrCl 2.3
- T-DXd haem: neutrophil 51 / pulm: ILD 2.4 / metab: potassium 20
- Polatuzumab haem: lymphocyte count decreased 87 (병용) / pulm: pneumonia 16
- Inotuzumab haem: neutrophil 96 / infect: infection 28 / metab: tumor lysis 11

**P: 백분위** (boxed 칸은 T에 영향이 없으므로 생략)

| ADC | haem | hep | cardio | pulm | renal | GI | neuro | ocular | derm | metab | musc | infect | oto |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Brentuximab | .667 | .083 | .5 | .292 | .750 | .167 | – | .375 | .333 | .500 | .250 | .375 | .542 |
| Datopotamab | .333 | .333 | .5 | .292 | .208 | 1.0 | .250 | .917 | .708 | .167 | .583 | .833 | .542 |
| Enfortumab | .417 | .792 | .5 | .292 | 1.0 | .917 | .250 | .375 | – | .917 | .250 | .375 | .542 |
| Gemtuzumab | .5 | – | .5 | .5 | .5 | .5 | .5 | .5 | .5 | .5 | .5 | .5 | .5 |
| Inotuzumab | 1.0 | – | 1.0 | .833 | .208 | .833 | .667 | .375 | 1.0 | .750 | 1.0 | 1.0 | .542 |
| Loncastuximab | .583 | .917 | .5 | .292 | .208 | .167 | .250 | .375 | .333 | .667 | .250 | .375 | .542 |
| Mirvetuximab | .125 | .250 | .5 | .583 | .208 | .583 | .833 | – | .333 | .250 | .708 | .375 | .542 |
| Pivekimab | .5 | – | .5 | .5 | .5 | .5 | .5 | .5 | .5 | .5 | .5 | .5 | .5 |
| Polatuzumab | .917 | .167 | .5 | 1.0 | .833 | .750 | .583 | .375 | .833 | .833 | .500 | .917 | .542 |
| Sacituzumab | – | .500 | .5 | .292 | .667 | .167 | .250 | .375 | .333 | .583 | .250 | .375 | .542 |
| Telisotuzumab | .250 | .583 | .5 | .917 | .500 | .333 | 1.0 | .750 | .333 | .333 | .250 | .375 | .542 |
| Tisotumab | .125 | .417 | .5 | .292 | .917 | .500 | .917 | – | .917 | .083 | .708 | .375 | .542 |
| T-DXd | .750 | .792 | .5 | – | .583 | .667 | .500 | .375 | .708 | 1.0 | .833 | .750 | .542 |
| T-DM1 | .500 | – | – | .667 | .417 | .417 | .750 | .375 | .333 | .417 | .917 | .375 | .542 |

**T = W + (1−W)·0.4·P (최종 약물 부담)**

| ADC | haem | hep | cardio | pulm | renal | GI | neuro | ocular | derm | metab | musc | infect | oto |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Brentuximab | .707 | .613 | .200 | .647 | .720 | .627 | 1.00 | .150 | .653 | .680 | .100 | .660 | .217 |
| Datopotamab | .133 | .133 | .200 | .647 | .083 | .760 | .100 | .747 | .283 | .067 | .233 | .333 | .217 |
| Enfortumab | .167 | .317 | .200 | .647 | .400 | .367 | .640 | .660 | 1.00 | .747 | .100 | .150 | .217 |
| Gemtuzumab | .200 | 1.00 | .680 | .200 | .200 | .200 | .200 | .200 | .200 | .200 | .200 | .680 | .200 |
| Inotuzumab | .760 | 1.00 | .760 | .333 | .083 | .333 | .267 | .150 | .400 | .300 | .400 | .760 | .217 |
| Loncastuximab | .693 | .747 | .680 | .117 | .083 | .067 | .100 | .150 | .653 | .267 | .100 | .660 | .217 |
| Mirvetuximab | .050 | .100 | .200 | .693 | .083 | .233 | .733 | 1.00 | .133 | .100 | .283 | .150 | .217 |
| Pivekimab | .200 | 1.00 | .680 | .200 | .200 | .200 | .200 | .200 | .200 | .200 | .200 | .680 | .200 |
| Polatuzumab | .747 | .627 | .200 | .400 | .333 | .300 | .693 | .150 | .333 | .733 | .200 | .747 | .217 |
| Sacituzumab | 1.00 | .200 | .200 | .117 | .267 | .627 | .100 | .150 | .133 | .693 | .100 | .660 | .217 |
| Telisotuzumab | .100 | .233 | .200 | .747 | .200 | .133 | .760 | .720 | .133 | .133 | .100 | .660 | .217 |
| Tisotumab | .050 | .167 | .680 | .647 | .367 | .200 | .747 | 1.00 | .747 | .033 | .283 | .150 | .217 |
| T-DXd | .720 | .317 | .680 | 1.00 | .233 | .267 | .200 | .150 | .283 | .400 | .333 | .300 | .217 |
| T-DM1 | .680 | 1.00 | 1.00 | .707 | .167 | .167 | .720 | .150 | .133 | .167 | .367 | .660 | .217 |

### 4.6 요청된 독성 유형별 표현 상태

| 독성 | 경고 층에서 | 발생률 층에서 | 관찰 |
|---|---|---|---|
| **안구독성** | mirvetuximab·tisotumab boxed(1.0). Dato-DXd·enfortumab·telisotumab W&P(0.6) | keratopathy, keratitis, blurred vision, dry eye가 ocular로 간다 | 라벨 등급은 정확히 반영된다. 환자에게 안구 취약성이 없으면 w≈1이라 boxed여도 기여가 작다(§6.4) |
| **ILD/폐렴** | T-DXd boxed. Dato-DXd·enfortumab·mirvetuximab·telisotumab·tisotumab·T-DM1·brentuximab W&P | "pneumonia"(감염)도 pulmonary로 들어가 ILD와 섞인다(polatuzumab 16% = pneumonia) | ILD와 감염성 폐렴이 구분되지 않는다 |
| **중증 피부반응** | enfortumab boxed. brentuximab·loncastuximab·tisotumab W&P | rash 등 | SJS/TEN은 "Serious dermatologic/cutaneous" 제목으로 간접적으로만 잡힌다 |
| **중증 설사** | sacituzumab: 라벨 boxed인데 **GI는 W&P 0.6으로만 잡힌다(파서 버그)** | sacituzumab GI 발생률이 0으로 집계된다 | **과소표현**. 고치면 이 환자 사례에서 sacituzumab Risk가 26.3→36.1, 4위→5위로 바뀐다(§8.1-A) |
| **혈액학적 독성** | sacituzumab boxed. 그 외 W&P 다수 | 대부분 lab(호중구·림프구·혈소판 감소) | gemtuzumab은 라벨 표가 없어 P=0.5 → T_haem=0.2로, 12개 표 보유 ADC 대부분보다 **낮다**(의학적 관찰: 실제 골수억제가 큰 약물이다). polatuzumab 87%는 병용요법 값이다 |

---

## 5. 위험 점수 계산식과 파라미터

### 5.1 변수 정의

| 기호 | 의미 | 범위 | 코드 |
|---|---|---|---|
| d | ADC (14개) | – | `ids` |
| o | 장기 (13개) | – | `AXES` |
| c | 입력 질환 | – | `conditions` |
| W(d,o) | 라벨 경고 등급 | {0, 0.6, 1} | `matcher2.py:30-41` |
| P(d,o) | Grade≥3 발생률 백분위 | (0,1], 표 없으면 0.5 | `recommend.py:45-46` |
| T(d,o) | 약물 장기 부담 | [0.033, 1] | `recommend.py:47` |
| own(c,o) | registry 자기 장기 severity | [0,1] | `recommend.py:51-55` |
| ℓ(c,o) | 학습된 연관 장기 severity | [0,1] | JSON 또는 `VM.predict` |
| f | LEARNED_FRACTION | 기본 0.5 | `recommend.py:24` |
| s(o) | 환자 장기 취약도 | [0,1] | `recommend.py:81` |
| λ | LAMBDA | 기본 9 | `recommend.py:26` |
| w(o) | 장기 가중치 | [1, 1+λ] | `recommend.py:85` |

### 5.2 전체 수식

```
(1) T(d,o)   = W(d,o) + (1 − W(d,o)) · 0.4 · P(d,o)
(2) s(c,o)   = max( own(c,o), f · ℓ(c,o) )
(3) s(o)     = max_c s(c,o)
(4) w(o)     = 1 + λ · s(o)
(5) raw(d)   = 100 · Σ_o w(o)·T(d,o) / Σ_o w(o)            # 가중 평균 × 100
(6) Risk(d)  = 100 · (raw(d) − min_d' raw(d')) / (max_d' raw(d') − min_d' raw(d'))     (분모가 0이면 전부 0)
(7) 순서     = argsort(raw) 오름차순                          # recommend.py:85
(8) c(d,o)   = w(o)·T(d,o);   표시 장기 = c 상위 N_ORGANS개 (c>0)
    share(d,o) = c(d,o) / max_o w(o)                         # recommend.py:94, 색 기준
```

### 5.3 파라미터별 분석

#### `weak-organ multiplier = x10` (λ = 9)

1. **정의/위치**: `w(o) = 1 + λ·s(o)`(85행). x10은 `1+λ`, 즉 s=1인 장기가 일반 장기(s=0)의 10배 비중이라는 뜻이다. 메뉴는 `EMPHASIS`(169행)에서 x5/x10/x15(λ=4/9/14)를 고르고, CLI `--lambda N`은 λ를 직접 준다.
2. **근거**: 주석(26-28행)과 README에 따르면 ILD 환자에서 T-DXd(boxed pulmonary)가 x3-x6에서는 14개 중 12위였고 x8 이상에서 14위(가장 위험)가 됐다. 그래서 여유를 두고 x10을 골랐다. 프로젝트 원래 기본값은 `src/adctox/design/search.py:128`의 `lam=2.0`(x3)이다.
3. **성격**: **휴리스틱이고 명시된 선호값이다.** 한 사례(ILD + T-DXd)의 '기대 순위'를 맞추도록 고른 값이며, 연구나 임상 결과로 검증되지 않았다.
4. **변경 시 영향**(§6.6 실측): 이 환자에서 λ=0(가중치 없음)이면 순위가 2: Mirv, 3: Teli, 4: Piv/Gem, 6: Saci, 7: Lonca, 8: T-DXd, 9: Tiso…로 바뀐다. λ=2-99에서는 상위 3개(Dato, Mirv, Teli)와 최하위(Brentuximab)가 고정이고 중간 순위가 이동한다(예: T-DXd 9위(λ=2) → 11위(λ≥9), Enfortumab과 Tisotumab의 교차). λ가 커질수록 점수는 s=1인 장기(이 환자는 renal, cardio)의 T만으로 정렬되는 쪽으로 수렴한다.

#### `linked organs = 0.5` (f, LEARNED_FRACTION)

1. **정의/위치**: `s(c,o) = max(own, f·ℓ)`(71, 80행). f=0.5이면 학습된 연관 장기는 최대 0.5까지만 올라가고, 그때 가중치는 최대 1+9·0.5 = 5.5배다. 자기 장기(최대 10배)를 넘을 수 없게 한 장치다.
2. **근거**: 주석은 "half the learned"뿐이다. 고르기 위한 실험은 없다. 비순환 검증에서 학습 가중치 자체의 이점이 유의하지 않았다(+0.033 [−0.018, +0.087]).
3. **성격**: **휴리스틱.**
4. **영향**(실측): f=0이면 Mirvetuximab이 최저(0.0), Dato 0.6, 최고는 **T-DM1**(Brentuximab은 79.2)이다. f=1이면 Lonca가 Saci 앞으로 온다. 이 환자에서는 f가 1위/최하위까지 바꾼다.

#### `organs per ADC = 3` (N_ORGANS)

1. **정의/위치**: 표에 표시할 장기 수(92행 `np.argsort(-contrib)[:N_ORGANS]`). **점수와 순위에는 전혀 영향이 없다.**
2. 코드 기본값은 **2**(25행, 메뉴 기본 index 1 = "2")다. 제공된 실행 결과의 3은 사용자가 메뉴에서 고른 값이다.
3. 선택 기준은 `c(d,o) = w(o)·T(d,o)`(환자 가중치 × 약물 부담)가 큰 순서다. `c>0` 조건은 T≥0.033이라 항상 참이다. 그래서 **근거(경고·발생률)가 전혀 없는 장기도 3번째에 표시될 수 있다**(예: Dato-DXd Tertiary = Cardiovascular, 경고 없음·발생률 0%, T=0.2인데 w=10이라 2.0이 됨).
4. 색: `share = c/max w`가 ≥0.5면 빨강, ≥0.25면 노랑, ≥0.1이면 초록, 그 밖은 회색(115행). 태그는 W로 정한다: 1.0 → "(Boxed)", 0.6 → "(Warn)", 0 → 없음.

#### `Risk scale = 0–100 relative`

1. **정의/위치**: 식 (6), 86행. `--raw` 또는 메뉴 "Raw"를 고르면 식 (5)의 raw를 표시한다. 색과 게이지는 항상 relative Risk 기준이다(125-126행).
2. **성격**: 표시용 정규화이며 순위는 raw와 같다.
3. **의미**:
   - **0 = 이 환자에게 이 14개 중 raw가 가장 낮은 ADC**이고, 100 = 가장 높은 ADC다. 0은 "위험 없음"이 아니다.
   - 중간값은 선형 보간일 뿐 확률이 아니다.
   - 차이가 과장될 수 있다. 이 사례에서 Dato와 Mirv의 raw 차는 0.205점인데 Risk로는 0.7이 된다. 전체 raw 범위가 29.36점이므로 Risk 1 = raw 0.29점이다.
   - ADC 집합이 바뀌면(예: 라벨 폴더가 추가·삭제되면) 모든 Risk가 바뀐다.
4. **raw의 의미**: '라벨 경고·발생률 백분위로 만든 장기 부담 T'의 환자 가중 평균 × 100이다. 확률이 아니다. 이론적 범위는 [3.33, 100]이며 0은 불가능하다. 따라서 docstring 12행 "0% = none touched"는 실제 구현과 다르다(§8.1-D). 경고가 전혀 없고 모든 장기에서 백분위가 최저인 가상 ADC도 raw ≥ 3.3이다.

### 5.4 최종 점수의 성격

- 절대적 부작용 발생 확률: **아니다.**
- 상대 점수: **그렇다.** raw는 약물 간 백분위(상대)와 등급 상수의 가중 평균이다.
- 정규화: 두 겹이다. ① 발생률은 ADC 간 백분위로, ② 표시 Risk는 환자별 min-max로 정규화된다.

---

## 6. 실제 환자 사례의 계산 과정 재현

입력: `nafld, ckd_stage_3, ckd_stage_4_5, dialysis, heart_failure, reduced_lvef, prior_anthracycline, coronary_artery_disease`. 파라미터는 λ=9, f=0.5다(사용자 출력과 같음).

### 6.1 질환별 벡터 (own, ℓ, s_c)

학습 z는 `learned_vulnerability.json`의 값이다(FinnGen HR 아님).

| 조건 | own (registry) | ℓ > 0 인 장기 (학습 severity) | s_c > 0 |
|---|---|---|---|
| nafld | hepatic 0.4 | hep 1.0, GI .858, musc .867, neuro .389, haem .312, metab .130 | hep **.5**(=.5·1.0 > .4), GI .429, musc .433, neuro .194, haem .156, metab .065 |
| ckd_stage_3 | renal 0.7 | renal .736, haem .629, neuro .589, metab .187, cardio .174, ocular .073 | renal **.7**, haem .315, neuro .294, metab .093, cardio .087, ocular .037 |
| ckd_stage_4_5 | renal 1.0 | renal .627, haem .572, GI .408, neuro .407, metab .095, cardio .003 | renal **1.0**, haem .286, GI .204, neuro .203, metab .047, cardio .002 |
| dialysis | renal 1.0 | renal .647, haem .439, cardio .413, neuro .315, GI .206, metab .084 | renal **1.0**, haem .220, cardio .206, neuro .157, GI .103, metab .042 |
| heart_failure | cardio 1.0 | cardio 1.0, metab .840, haem .698, pulm .605, renal .601, neuro .437 | cardio **1.0**, metab .420, haem .349, pulm .303, renal .301, neuro .219 |
| reduced_lvef | cardio 1.0 | cardio 1.0, neuro .853, haem .746, pulm .735, metab .581, renal .014 | cardio **1.0**, neuro .427, haem .373, pulm .368, metab .291, renal .007 |
| prior_anthracycline | cardio 0.6 | oto .500, derm .445, GI .420, haem .223, musc .215, infect .176 (**cardio 0**) | cardio **.6**, oto .25, derm .223, GI .21, haem .111, musc .107, infect .088 |
| coronary_artery_disease | cardio 0.6 | cardio 1.0, metab .893, haem .544, renal .377, neuro .294, pulm .173 | cardio **.6**(=max(.6,.5)), metab .447, haem .272, renal .188, neuro .147, pulm .086 |

### 6.2 환자 벡터 s, 가중치 w

| 장기 | s = max_c | 결정한 조건 | w = 1+9s |
|---|---|---|---|
| cardiovascular | 1.000 | heart_failure / reduced_lvef (own) | **10.000** |
| renal | 1.000 | ckd_stage_4_5 / dialysis (own) | **10.000** |
| hepatic | 0.500 | nafld (0.5·학습 1.0) | 5.500 |
| metabolic_endocrine | 0.447 | coronary (학습) | 5.019 |
| musculoskeletal | 0.433 | nafld (학습) | 4.900 |
| gastrointestinal | 0.429 | nafld (학습) | 4.862 |
| neurologic | 0.427 | reduced_lvef (학습) | 4.841 |
| haematologic | 0.373 | reduced_lvef (학습) | 4.359 |
| pulmonary | 0.368 | reduced_lvef (학습) | 4.308 |
| otologic | 0.250 | prior_anthracycline (학습) | 3.250 |
| dermatologic | 0.223 | prior_anthracycline (학습) | 3.003 |
| infectious_immune | 0.088 | prior_anthracycline (학습) | 1.792 |
| ocular | 0.037 | ckd_stage_3 (학습) | 1.329 |
| **합계 Σw** | | | **63.1614** |

renal과 cardio가 각각 Σw의 15.8%, hepatic이 8.7%를 차지한다. 나머지 66%는 학습된 연관 장기와 기본 가중치 1에서 온다.

### 6.3 14개 ADC 전체: 장기별 기여 c = w·T → raw → Risk

| # | ADC | haem | hep | cardio | pulm | renal | GI | neuro | ocular | derm | metab | musc | infect | oto | **Σc** | **raw** | **Risk** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Datopotamab deruxtecan | .581 | .733 | 2.000 | 2.786 | .833 | 3.695 | .484 | .992 | .851 | .335 | 1.143 | .597 | .704 | 15.735 | 24.912 | **0.00** |
| 2 | Mirvetuximab soravtansine | .218 | .550 | 2.000 | 2.987 | .833 | 1.134 | 3.550 | 1.329 | .400 | .502 | 1.388 | .269 | .704 | 15.864 | 25.117 | **0.70** |
| 3 | Telisotuzumab vedotin | .436 | 1.283 | 2.000 | 3.216 | 2.000 | .648 | 3.679 | .957 | .400 | .669 | .490 | 1.183 | .704 | 17.666 | 27.970 | **10.41** |
| 4 | Sacituzumab govitecan | 4.359 | 1.100 | 2.000 | .503 | 2.667 | 3.047 | .484 | .199 | .400 | 3.480 | .490 | 1.183 | .704 | 20.615 | 32.639 | **26.32** |
| 5 | Loncastuximab tesirine | 3.022 | 4.107 | 6.800 | .503 | .833 | .324 | .484 | .199 | 1.962 | 1.338 | .490 | 1.183 | .704 | 21.949 | 34.751 | **33.52** |
| 6 | Gemtuzumab ozogamicin | .872 | 5.500 | 6.800 | .862 | 2.000 | .972 | .968 | .266 | .601 | 1.004 | .980 | 1.219 | .650 | 22.692 | 35.928 | **37.52** |
| 7 | Pivekimab sunirine | .872 | 5.500 | 6.800 | .862 | 2.000 | .972 | .968 | .266 | .601 | 1.004 | .980 | 1.219 | .650 | 22.692 | 35.928 | **37.52** |
| 8 | Tisotumab vedotin | .218 | .917 | 6.800 | 2.786 | 3.667 | .972 | 3.614 | 1.329 | 2.242 | .167 | 1.388 | .269 | .704 | 25.073 | 39.696 | **50.36** |
| 9 | Enfortumab vedotin | .727 | 1.742 | 2.000 | 2.786 | 4.000 | 1.783 | 3.098 | .877 | 3.003 | 3.747 | .490 | .269 | .704 | 25.224 | 39.936 | **51.18** |
| 10 | Polatuzumab vedotin | 3.255 | 3.447 | 2.000 | 1.723 | 3.333 | 1.458 | 3.356 | .199 | 1.001 | 3.681 | .980 | 1.338 | .704 | 26.475 | 41.917 | **57.92** |
| 11 | Trastuzumab deruxtecan | 3.139 | 1.742 | 6.800 | 4.308 | 2.333 | 1.296 | .968 | .199 | .851 | 2.008 | 1.633 | .538 | .704 | 26.519 | 41.985 | **58.16** |
| 12 | Inotuzumab ozogamicin | 3.313 | 5.500 | 7.600 | 1.436 | .833 | 1.621 | 1.291 | .199 | 1.201 | 1.506 | 1.960 | 1.362 | .704 | 28.526 | 45.163 | **68.98** |
| 13 | Trastuzumab emtansine | 2.964 | 5.500 | 10.000 | 3.044 | 1.667 | .810 | 3.485 | .199 | .400 | .836 | 1.797 | 1.183 | .704 | 32.590 | 51.598 | **90.90** |
| 14 | Brentuximab vedotin | 3.081 | 3.373 | 2.000 | 2.786 | 7.200 | 3.047 | 4.841 | .199 | 1.962 | 3.413 | .490 | 1.183 | .704 | 34.277 | 54.270 | **100.00** |

검산: `raw = 100·Σc/63.1614`, `Risk = 100·(raw − 24.9119)/29.3576`. 사용자 출력(0.0, 0.7, 10.4, 26.3, 37.5, 100.0)과 정확히 일치한다.

표시 장기(N=3, share = c/10)와 태그는 다음과 같다.

| # | ADC | Primary | Secondary | Tertiary |
|---|---|---|---|---|
| 1 | Datopotamab | GI (Warn) .369 | Pulmonary (Warn) .279 | Cardiovascular (태그 없음) .200 |
| 2 | Mirvetuximab | Neurologic (Warn) .355 | Pulmonary (Warn) .299 | Cardiovascular (태그 없음) .200 |
| 3 | Telisotuzumab | Neurologic (Warn) .368 | Pulmonary (Warn) .322 | Renal (태그 없음) .200 |
| 4 | Sacituzumab | Haematologic (Boxed) .436 | Metabolic (Warn) .348 | GI (Warn) .305 |
| 5 | Loncastuximab | Cardiovascular (Warn) .680 | Hepatic (Warn) .411 | Haematologic (Warn) .302 |
| 6 | Gemtuzumab | Cardiovascular (Warn) .680 | Hepatic (Boxed) .550 | Renal (태그 없음) .200 |
| 7 | Pivekimab | Cardiovascular (Warn) .680 | Hepatic (Boxed) .550 | Renal (태그 없음) .200 |
| 8 | Tisotumab | Cardiovascular (Warn) .680 | Renal (태그 없음) .367 | Neurologic (Warn) .361 |
| 9 | Enfortumab | Renal (태그 없음) .400 | Metabolic (Warn) .375 | Neurologic (Warn) .310 |
| 10 | Polatuzumab | Metabolic (Warn) .368 | Hepatic (Warn) .345 | Neurologic (Warn) .336 |
| 11 | T-DXd | Cardiovascular (Warn) .680 | Pulmonary (Boxed) .431 | Haematologic (Warn) .314 |
| 12 | Inotuzumab | Cardiovascular (Warn) .760 | Hepatic (Boxed) .550 | Haematologic (Warn) .331 |
| 13 | T-DM1 | Cardiovascular (Boxed) 1.000 | Hepatic (Boxed) .550 | Neurologic (Warn) .349 |
| 14 | Brentuximab | Renal (Warn) .720 | Neurologic (Boxed) .484 | Metabolic (Warn) .341 |

### 6.4 왜 Datopotamab deruxtecan = 0.0 인가

1. 이 환자에서 가장 무거운 두 장기 cardio(w=10)와 renal(w=10)에서 Dato-DXd는:
   - cardio: 경고 없음, 발생률 0% → 12개 중 11개 동점 → P=0.5 → T=0.2 → c=2.0. 경고 없는 모든 ADC가 같은 값이다.
   - renal: 경고 없음, 발생률 0%(4개 동점) → P=0.208 → T=0.083 → c=0.833. 14개 중 최저 그룹이다(Ino, Lonca, Mirv와 같음).
2. boxed 경고가 하나도 없다. W&P 세 개(pulm, ocular, GI)는 이 환자의 중간 가중치 장기(4.3, 1.33, 4.86)에 걸려 있다.
3. 가장 큰 기여는 GI 3.695다(W&P 0.6 + amylase 증가 38%로 GI 백분위 1.0 → T 0.76).
4. 합계 Σc = 15.735로 14개 중 최소 → Risk 0.

즉 "이 환자의 심장·신장에 라벨 경고가 없고, 신장 lab 이상 발생률도 표에 없다"는 점이 결정했다. **경고가 없다는 사실이 안전성 입증과 같은 취급을 받는다**(§7.2).

### 6.5 왜 Mirvetuximab soravtansine = 0.7 인가

- cardio 2.0과 renal 0.833은 Dato와 **완전히 같다**(둘 다 경고 없음, 같은 동점 그룹).
- boxed ocular(T=1.0)지만 이 환자 ocular w = 1.329(s=0.037)라 기여는 1.329에 그친다.
- Dato와의 장기별 차이 (Mirv − Dato):

| 장기 | 차이 | 이유 |
|---|---|---|
| neurologic | **+3.066** | Mirv W&P PN(.733) vs Dato 없음(.100), w=4.841 |
| ocular | +0.337 | boxed 1.0 vs W&P .747, w=1.329 |
| pulmonary | +0.201 | P .583 vs .292 |
| musculoskeletal | +0.245 | |
| metabolic | +0.167 | |
| GI | **−2.561** | Dato W&P + amylase 38% (.760) vs Mirv 경고 없음 (.233) |
| dermatologic | −0.451 | |
| haematologic | −0.363 | Mirv 7%(최저 동점) vs Dato 11% |
| infectious | −0.328 | |
| hepatic | −0.183 | |
| cardio, renal, oto | 0 | |
| **합계** | **+0.129** | |

- raw 차 = 0.129/63.1614·100 = 0.205점 → Risk = 0.205/29.358·100 = **0.70**.
- 사실상 동점이다. 신경 W&P와 GI(amylase 백분위)가 서로 상쇄한 결과이고, 두 값 모두 파라미터와 백분위 산술에 민감하다(f=0이면 순서가 뒤집힌다).

### 6.6 그 밖의 주요 값

- **Telisotuzumab 10.4**: Dato 대비 renal +1.167(creatinine 1.2% → P .5 → T .2), neuro +3.195(W&P PN), infect +0.586(IRR W&P), hepatic +0.55. GI는 −3.05로 상쇄된다.
- **Sacituzumab 26.3**: haem boxed 4.359, metab W&P(UGT1A1 제목) 3.48, GI W&P 3.047, renal 2.667(CrCl 감소 2.3% → P .667). **diarrhea boxed가 누락된 상태의 값이다.**
- **Pivekimab = Gemtuzumab 37.5**(완전 동점): 둘 다 라벨 표가 없어(P=0.5 전부) T 벡터가 같다. cardio W&P(edema / hemorrhage·QT) 6.8, hepatic boxed 5.5, renal 0.2→2.0. 표시 순서는 `np.argsort`의 동점 처리 결과이며 의미가 없다.
- **Brentuximab 100**: renal W&P "Increased Toxicity in the Presence of Severe Renal Impairment"(T .72 × 10 = 7.2), neuro boxed PML 4.841, 그 외 W&P 9개 장기. 이 라벨은 section 5 제목이 14개로 가장 많아서 경고가 넓게 퍼져 있다.

### 6.7 민감도 (실측, 같은 8개 조건)

순서는 낮음→높음이고 괄호 안이 Risk다.

| 설정 | 결과 |
|---|---|
| λ=0 (x1) | Dato 0, Mirv 1.3, Teli 13.2, Piv/Gem 13.9, Saci 17.3, Lonca 19.6, **T-DXd 38.3**, Tiso 44.5, Enfo 55.1, Pola 57.4, Ino 60.2, T-DM1 72.3, Brent 100 |
| λ=2 (x3, 프로젝트 원 기본값) | Dato 0, Mirv .9, Teli 11.4, Saci 23.1, Lonca 28.5, Gem/Piv 28.9, Tiso 48.2, T-DXd 50.9, Enfo 52.6, Pola 57.7, Ino 65.8, T-DM1 84.1, Brent 100 |
| λ=4 (x5) | … Tiso 49.4, Enfo 51.8, T-DXd 54.8, Pola 57.8 … |
| **λ=9 (x10, 기본)** | 위 표와 같음 |
| λ=14 (x15) | Dato 0, Mirv .7, Teli 10.2, Saci 26.9, Lonca 34.4, Gem/Piv 39.0, Tiso 50.7, Enfo 50.9, Pola 58.0, T-DXd 59.4, Ino 69.5, T-DM1 92.1, Brent 100 |
| λ=99 | … **Enfo 50.5 < Tiso 51.4**(교차) … |
| f=0 (학습 미사용) | **Mirv 0**, Dato .6, Teli 14.2, Saci 18.7, Enfo 39.4, Pola 43.8, Lonca 54.0, T-DXd 56.7, Tiso 63.1, Piv/Gem 67.4, Ino 75.4, Brent 79.2, **T-DM1 100** |
| f=0.25 | … Brent 97.5, T-DM1 100 |
| f=0.75 | Dato 0, Mirv .7, Teli 9.3, Saci 26.6, Lonca 29.3 … |
| f=1.0 | Dato 0, Mirv .8, Teli 8.5, **Lonca 26.5 < Saci 26.8** … |
| 중복 제거 [nafld, ckd_4_5, heart_failure, CAD] | **Mirv 0, Dato 4.2**, Teli 8.4, Saci 35.7, Lonca 37.9, Gem/Piv 47.1, Enfo 47.6, Tiso 48.0, Pola 60.8, T-DXd 67.3, Ino 77.3, T-DM1 99.1, Brent 100 |
| ckd_3 + ckd_4_5 + dialysis | Dato 0, Mirv 4.9, Piv/Gem 13.4, Lonca 13.8, Teli 15.6, Ino 33.5, T-DXd 35.1, Saci 36.7, Tiso 41.2, Enfo 45.7, T-DM1 50.0, Pola 53.1, Brent 100 |
| ckd_4_5 단독 | Dato 0, Mirv .3, Lonca 7.2, Gem/Piv 7.3, Teli 12.2, … Brent 100 |
| heart_failure + reduced_lvef | Dato 0, Mirv 17.2, Teli 25.8, … Brent 86.4, T-DM1 100 |
| heart_failure 단독 | Dato 0, Mirv 9.8, … Brent 81.3, T-DM1 100 |
| s=0 (취약성 없음) raw | Dato 30.28, Mirv 30.59, Teli 33.36, Gem/Piv 33.54, Saci 34.33, Lonca 34.87, Tiso 40.67, Enfo 43.15, Pola 43.69, Ino 44.33, T-DXd≈T-DM1(47.18로 출력, 이름 키 충돌로 하나만 표시), Brent 53.64 |

해석(사실만):
- s=0일 때도 Dato와 Mirv가 가장 낮고 Brentuximab이 가장 높다. 이 환자 사례의 양 끝은 **환자 정보보다 약물 측 T의 평균(경고 개수와 백분위)이 크게 좌우한다.**
- 의미상 중복인 입력을 빼면 1위가 바뀐다(Dato→Mirv).

---

## 7. ADC 순위 결정 알고리즘

| 질문 | 구현 사실 |
|---|---|
| 적응증·암종 고려 | **하지 않는다.** 14개 ADC를 적응증과 무관하게 한 표에서 비교한다. 입력에 암종이 없다 |
| 표적 항원·바이오마커 | **하지 않는다.** (`src/adctox/comorbidity/target_expression.py`가 저장소에 있지만 추천기와 연결되어 있지 않다) |
| 승인 여부·사용 조건 | DailyMed 스냅샷 폴더에 있으면 포함한다. 승인 상태, 라인, 병용 조건은 확인하지 않는다 |
| 금기·투여 회피 필터링 | **하지 않는다.** 제외(hard filter) 단계가 없고 모든 ADC가 점수만 받는다. `conf/hard_flags.yaml`도 쓰지 않는다 |
| 데이터 없을 때 낮게 평가될 가능성 | **있다.** ① 경고 없음 → T ≤ 0.4. ② 발생률 표에 없는 장기 → 동점 백분위로 낮은 값. ③ 표 없는 ADC → P=0.5. haem처럼 다른 ADC들이 높은 장기에서는 상대적으로 '안전'하게 보인다(gemtuzumab haem 0.2) |
| 정렬 방식 | `np.argsort(raw)` 오름차순 단순 정렬(85행). 동점 규칙은 정의되어 있지 않다 |
| Primary/Secondary/Tertiary | `c(d,o) = w(o)·T(d,o)` 내림차순 상위 N개(92행). 경고 유무와 무관하게 기여가 크면 표시된다 |

### 7.1 표시 규칙

- Risk 색: Risk < 33.4 초록, < 66.7 노랑, 그 이상 빨강(111행). 게이지 ○◔◑◕●는 Risk를 20 단위로 나눈 것이다.
- 장기 셀 색은 share 기준이다(§5.3). 장기 셀 태그는 라벨 등급 기준이다.

### 7.2 "경고 없음" vs "안전성 입증"

**알고리즘은 둘을 구별하지 않는다.** W=0은 "라벨 section 5 제목에 그 장기가 없다"는 뜻일 뿐이다. 다음 경우들은 모두 같은 W=0으로 처리된다.
- 해당 집단(예: 중증 신장애, 심부전)에서 연구된 적이 없는 경우
- 라벨이 section 8에서 "데이터 없음"이나 "권고 없음"이라고 하는 경우
- 시험에서 그런 환자를 제외한 경우

발생률 층도 '시험에 포함된 환자의 Grade≥3 빈도'일 뿐, 취약 환자에서의 빈도가 아니다. 이 사례에서 Dato-DXd가 0점인 것은 "심부전·투석 환자에서 안전하다는 근거가 있다"는 뜻이 **아니다.**

---

## 8. 검증 상태와 구현상의 한계

### 8.1 이번 분석에서 확인한 구현 결함 (수정하지 않음)

| ID | 결함 | 위치 | 원인 | 실측 영향 |
|---|---|---|---|---|
| **A** | boxed 제목의 대문자 "AND"를 분리하지 못한다 → sacituzumab "NEUTROPENIA AND DIARRHEA"에서 GI boxed 누락 | `label_change.py:143` `re.split(r"\band\b|,|;", …)`에 `re.IGNORECASE`가 없다 | 대소문자 구분 정규식. 전체 문자열이 첫 패턴(haematologic)에만 매칭된다 | sacituzumab GI T .627→1.0이어야 한다. 이 환자에서 Risk 26.3→36.1, 순위 4→5 |
| **B** | Grade 3 행과 Grade 4 행을 **표(시험)에 걸쳐** 합산 | `matcher2.py:48` `groupby([ADC, term, domain]).pct.sum()` | 표 ID로 묶지 않았다 | T-DM1에만 해당(EMILIA + KATHERINE). haem 23% vs 표 단위 최대 17%. T 변화 ≤ 0.017, 이 사례 순위 변화 없음 |
| **C** | 학습/추론 context 불일치 | 학습: `vulnerability_model.py:40`(`lab.py:85`도 같음) `torch.cat([eye[li], eye[nl+di]],1)[:, :nl+nd]` → domain 비트가 잘려 **lag만** 들어간다. 추론: 76행이 domain 비트를 1로 채운다 | 슬라이스 오류. `lab.py`의 모든 실험도 domain 정보 없이 학습됐다 | 학습되지 않은 입력 가중치가 작용한다. 41개 질환 평균 \|Δseverity\| 0.002-0.011, top-1 일치율 동일(0.512) |
| **D** | docstring "0% = none touched"가 구현과 다르다 | `recommend.py:12` | T 최솟값 0.033(백분위가 0이 될 수 없다) | raw는 0이 불가능하다. 설명 오류 |
| **E** | 근거 없는 장기가 Primary/Secondary/Tertiary로 표시될 수 있다 | `recommend.py:92` `contrib[k] > 0` | T>0이 항상 성립 | 이 사례에서 Dato, Mirv, Gem, Piv의 Tertiary와 Tiso, Enfo의 renal |
| **F** | boxed가 없는 라벨에서 `<h1>WARNINGS AND PRECAUTIONS</h1>`을 boxed 제목으로 잡는다 | `label_change.py:116-120` (`startswith("WARNING")`) | 접두어 판정 | 현재는 매핑되는 장기가 없어서 결과 영향이 없다. 제목 문구가 바뀌면 잘못된 boxed가 생길 수 있다 |
| **G** | 두 스크립트가 같은 출력 파일을 쓴다 | `ml/learned_vulnerability.py:20`과 `ml/vulnerability_model.py:93`이 모두 `ml/results/learned_vulnerability.json`에 쓴다 | 레거시 스크립트를 그대로 둠 | 레거시(SapBERT) 스크립트를 다시 실행하면 추천기 입력이 조용히 바뀐다 |
| **H** | 동점 순서가 정의되어 있지 않다 | `recommend.py:85` `np.argsort` (기본 quicksort, 불안정 정렬) | – | Gem/Piv처럼 완전 동점이면 표시 순서가 임의다 |

### 8.2 임의로 정한 가정과 상수 (모두 미검증 휴리스틱)

| 상수 | 값 | 위치 | 근거 |
|---|---|---|---|
| W_BOXED / W_SEC5 | 1.0 / 0.6 | `matcher2.py:28` | 선택값. 실험 없음 |
| W_INC | 0.4 | 같음 | 선택값. "경고가 항상 우위"가 되도록 정했다 |
| 표 없는 ADC의 P | 0.5 | `recommend.py:45` | "중앙값으로 두어 경고가 결정하게" |
| λ | 9 | `recommend.py:26` | T-DXd/ILD 한 사례의 기대 순위 |
| f | 0.5 | `recommend.py:24` | 실험 없음 |
| REG_NEAR / MATCH_COS | 0.80 / 0.60 | `recommend.py:34,36` | 실험 없음 |
| MONDO THETA | 0.75 | `mondo_index.py:12` | 결과를 보기 전에 고정했다(문서 주장) |
| MONDO_SEVERITY | 0.8 | `recommend.py:35` | 고정 |
| Z_FULL(1 SD = 1.0) | 1 | `vulnerability_model.py:83` | 선택값 |
| registry severity | 0.4-1.0 | csv | 수작업. 제외기준 빈도 서술 |
| 결합 연산 | max (조건 간), 가중 평균 (장기 간) | `recommend.py:81,85` | 설계 선택 |

### 8.3 데이터 누락·매핑 문제 가능성

1. Section 4(금기), section 8(특정 집단), 용량 조절, PK를 쓰지 않는다. 신장·간장애 정보가 대부분 빠진다.
2. 경고는 제목만 읽는다. 본문에 나오는 장기는 놓친다.
3. 제목 하나는 장기 하나다(첫 매칭). 정규식 순서에 따라 분류가 정해진다. 예: "Hemorrhage"→cardiovascular, "Infusion reactions"→infectious_immune, "PML"→neurologic, "Tumor lysis"·"UGT1A1"→metabolic.
4. 발생률 도메인은 워크북에 적힌 값을 그대로 쓴다. lab 이상(amylase→GI, creatinine→renal), 감염(UTI→renal, pneumonia→pulmonary)이 장기 독성으로 섞인다.
5. 병용요법 행이 섞인다. polatuzumab은 100% 병용이고 enfortumab, T-DXd는 일부다.
6. 적응증과 용량이 다른 여러 표의 **최댓값**을 쓴다.
7. sacituzumab GI Grade≥3 발생률이 0으로 집계된다. 워크북에서 sacituzumab의 diarrhea, nausea, vomiting Grade≥3 행은 모두 `Source type = "Primary clinical publication"`이다. `Regulatory label via DailyMed` 행에는 lab 이상 표만 있어서 라벨 필터가 이 행들을 빼 버린다. 즉 "라벨 표만 쓴다"는 필터가 라벨 본문(6장)의 임상 이상반응 표 전사 누락과 맞물려 생긴 결과다. 다른 ADC에도 같은 유형의 누락이 있는지는 전수 확인하지 않았다.
8. 라벨 표가 없는 ADC 2개(gemtuzumab, pivekimab)는 모든 장기 P=0.5다.
9. 워크북의 라벨 버전과 DailyMed 스냅샷 버전의 일치 여부는 확인 불가다.
10. 상호 배타적이지 않은 장기 축 때문에, 같은 생리적 문제가 다른 축으로 나뉘거나 한 축에 섞일 수 있다(예: 심부전에서 부종·출혈·QT·LVEF가 모두 cardiovascular 한 축).

### 8.4 중복 질환 입력에 따른 편향

자기 장기는 max라서 부풀지 않는다. 하지만 입력을 늘릴수록 교차 장기 s가 단조 증가하므로 Σw 구성이 바뀌고, 이 때문에 순위가 달라진다. 이 사례에서 중복을 제거하면 1위가 Dato→Mirv로 바뀐다(§6.7).

### 8.5 FDA 경고 수준과 점수의 불일치 가능성

- boxed(1.0)라도 환자 가중치가 낮은 장기면 기여가 작다(Mirv ocular 1.33). 의도된 설계다.
- W&P가 많은 라벨(brentuximab 9개 장기)은 기본 가중치 1 덕분에 누적되어 높게 나온다. 반대로 W&P가 적은 라벨은 낮게 나온다. **경고 개수가 점수를 끌어올리는 효과**가 있으며, 제목을 얼마나 잘게 나눴는지 같은 라벨 작성 관행에 의존한다.
- 파서 버그(§8.1-A) 때문에 실제 boxed가 W&P로 내려간 사례가 있다.

### 8.6 근거 부족 약물의 과도한 안전 평가

§4.4와 §7.2의 메커니즘에 해당한다. 특히 신규 또는 적응증이 좁은 ADC는 라벨 section 5가 짧고 표가 적다. 그래서 점수가 낮아지는 경향이 구조적으로 존재한다(이 사례의 하위 3개: Dato-DXd W&P 3개, Mirv 3개, Telisotuzumab 4개).

### 8.7 상대 정규화 왜곡

- Risk는 해당 14개 집합 안에서의 min-max다. 0.2점 raw 차가 0.7 Risk가 된다.
- 최고/최저 ADC 하나만 바뀌어도 모든 Risk가 다시 매겨진다.
- 발생률 백분위도 집합 의존적이다. 표 있는 ADC가 추가되면 기존 ADC의 P가 바뀐다.

### 8.8 검증된 것 / 검증되지 않은 것

| 항목 | 상태 | 근거 |
|---|---|---|
| FinnGen 질환→결과 log HR 예측(교차검증) | 검증됨(통계적) | `ml/README.md`, `ml/results/lab/` |
| 학습 취약도가 registry 자기 장기를 회복 | sanity check(AUROC 0.80-0.86) | `ml/results/validate_registry.json` |
| 발생률 층이 라벨 경고 장기를 회복 | AUROC 0.670 [0.557, 0.781], 12개 약물 | `ml/results/matcher2.json` |
| 학습 가중치가 매칭을 개선 | **유의하지 않음**(비순환 +0.033 [−0.018, +0.087]) | 같음 |
| 최종 Risk가 실제 환자 독성과 관련 | **검증 없음** | – |
| λ, f, 0.6, 0.4 등 상수 | **검증 없음** | – |
| registry severity | **검증 없음**(수작업) | – |
| 임상 결과(입원, 중단, Grade≥3 발생)와의 대조 | **없음** | – |

### 8.9 테스트 현황

- `tests/`에는 테스트 파일 59개가 있지만 **모두 `src/adctox/`용**이다. `ml/` 모듈(recommend, matcher2, vulnerability_model, mondo_index, tui)을 import하는 테스트는 **0개**다(grep 확인).
- `label_change.py`(src)의 매핑 정확성을 대문자 "AND" 같은 사례로 검증하는 테스트는 확인하지 못했다.
- 테스트가 없는 핵심 기능:
  - `drug_table`의 T 계산
  - `patient_weights`의 결합
  - `recommend`의 정규화와 정렬
  - 자유 텍스트 경로의 임계값 분기
  - 표시 태그와 W의 일치
  - 학습/추론 context 일관성
  - 파이프라인 회귀(같은 입력 → 같은 출력)
- 존재하는 검증은 실험 스크립트(`matcher2.main`, `validate_registry.py`, `lab.py` 등)의 일회성 평가다.

---

## 9. 전체 시스템에 대한 기술적·의학적 평가

### 9.1 기술적 평가 (구현 기준)

- **재현성**: 결정적(deterministic)이다. 같은 입력이면 같은 출력이 나오고, 이번 재계산이 사용자 출력과 소수점까지 일치했다. 다만 자유 텍스트 경로는 GPU 모델 추론에 의존한다.
- **투명성**: 점수는 T 행렬과 w 벡터의 내적으로 완전히 분해된다(§6.3). 각 T는 라벨 제목과 워크북 행으로 거슬러 올라갈 수 있다.
- **수학적 성질**:
  - raw는 T의 볼록 결합(가중 평균)이다. w>0이므로 raw ∈ [min_o T, max_o T]이다.
  - s는 입력에 대해 단조 증가한다.
  - λ→∞이면 s=max인 장기의 T만으로 정렬된다. λ=0이면 T의 단순 평균으로 정렬된다.
  - 장기 간 상관(축 간 중복)은 고려하지 않는다.
- **취약 지점**: 상수 다수가 미검증이다(§8.2). 파서 정규식은 대소문자와 첫 매칭에 의존한다. 동점 백분위 산술이 '데이터 없음'에 값을 부여한다. 학습/추론 불일치가 있다(영향 작음). 테스트가 없다.
- **학습 모델의 역할**: 최종 점수에서 학습값은 연관 장기의 w(최대 5.5배)를 정하는 데만 쓰인다. 그 효과가 매칭 성능을 높인다는 증거는 없다(§8.8). 이 사례에서도 f 값이 1위와 최하위를 바꿀 만큼 영향이 크다.

### 9.2 의학적 관찰 (코드와 무관한 외부 지식; 검증자가 확인 필요)

아래는 구현 사실이 아니라, 구현 결과를 해석할 때 고려할 일반 의학 지식이다.
1. ADC는 적응증(암종, 표적 발현, 치료 라인)이 서로 달라 실제로는 서로 대체할 수 없다. 적응증을 무시한 14개 비교는 '같은 환자에게 고를 수 있는 선택지 목록'이 아니다.
2. 신장·간 기능 장애의 실질 정보는 라벨 section 2(용량 조절), 8.6/8.7, 12.3(PK)에 있다. 이 시스템은 이를 쓰지 않는다. 투석·말기 신부전 환자 자료가 없다는 것은 흔히 "권고 불가"를 뜻하는데, 시스템에서는 '경고 없음'이 되어 점수를 낮춘다.
3. 심부전/LVEF 저하 환자에서 HER2 표적 ADC(T-DM1 boxed cardiac, T-DXd LV dysfunction W&P)는 높게 나온다. 라벨 내용과 방향은 일치한다.
4. 안트라사이클린 노출력의 심혈관 위험은 학습 모델에 잡히지 않는다(학습 cardio=0). registry 수작업 값 0.6에만 의존한다.
5. 라벨 boxed 경고는 '중대성'의 신호이고 빈도의 신호가 아니다. W&P 개수는 라벨 작성 관행의 영향을 받는다. 둘을 0.6과 1.0이라는 고정 수치로 합산하는 것의 임상적 의미는 정의되어 있지 않다.
6. Grade≥3 발생률은 시험 적격 환자(장기 기능이 정상 범위인 환자)에서 측정된 값이다. 기저질환자의 위험을 직접 나타내지 않는다.

### 9.3 이 보고서가 다루지 않은 것

- 원본 라벨 HTML과 워크북 셀 하나하나의 대조 검증(라벨 6장 표가 워크북에 빠짐없이 전사됐는지).
- `lab.py` 교차검증 수치 자체의 재실행. README와 결과 JSON을 인용했다.
- 자유 텍스트 경로의 사례별 정확도(MONDO 링크 정확도는 별도 평가가 저장소에 없다. registry 대상 23/41 정확 ID, 36/41 장기 겹침은 `ml/link_mondo.py` 결과로 보고된 바 있다).
