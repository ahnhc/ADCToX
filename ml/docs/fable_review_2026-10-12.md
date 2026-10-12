# Claude Fable 검토 요청

아래 요청과 파일을 함께 전달하면 된다. 이 문서는 Fable에게 자동 전송하지 않았다.

## 읽는 순서

1. [연구 및 구현 현황](research_status_2026-10-12.md): 실제 프로젝트, 실행 방법, UI 변경, 연구 결과와 한계.
2. [모델 정확도 개선 계획](model_accuracy_plan_2026-10-12.md): 앞으로 할 benchmark와 학습 실험, 설계 단계 연결안.
3. [수치 및 소스 스냅샷](../results/review_snapshot_2026-10-12.json): 기존 결과의 정확한 값, paired CI, 데이터 수, 체크포인트 및 파일 해시.
4. [최신 화면 캡처](../../artifacts/terminal-captures/ui-v0.0/): 실제 실행 화면. 같은 폴더의 txt 및 ANSI 기록도 확인 가능.

저장소에 접근할 수 있으면 아래 요청을 그대로 전달한다. 문서만 전달할 경우 원본 코드를 확인하지 못한 판단은 추론으로 표시하도록 요청한다.

## 복사할 검토 요청

```text
ADCTOX 프로젝트의 현재 연구와 다음 실험 계획을 검토해줘.

먼저 다음 세 파일을 읽어줘.
- ml/docs/research_status_2026-10-12.md
- ml/docs/model_accuracy_plan_2026-10-12.md
- ml/results/review_snapshot_2026-10-12.json

지금 중심 제품은 Ubuntu 터미널 ADC 비교 추천기야. 기존 Fable 디자인은
대체로 만족스러운 상태이므로 요청하지 않은 UI 재설계나 기능 추가보다
모델 연구의 타당성, 평가, 우선순위를 검토해줘.

공모전에서는 우리가 학습한 AI 모델을 활용해야 해. 장기 목표는 기존 항체,
링커, payload의 새로운 조합을 제안하는 것이고, 현재 최우선은 질환 이름을
장기로 연결하는 성능과 FinnGen 장기 취약성 모델의 정확도 및 실행 비용을
수치로 비교하는 것이야.

현재 배포 모델은 frozen BioLORD + 직접 학습한 5개 MLP head ensemble이야.
MONDO는 ontology이고 FinnGen은 학습 자료야. 과거 LoRA 실험은 R²를 높였지만
장기 순위 개선은 불확실했어. BioLORD kNN도 반드시 비교해야 해.

아래 사항을 중심으로 비판적으로 평가해줘.

1. 현재 코드의 처리와 문서 설명이 일치하는지 확인해줘.
   특히 resolve의 임계값, 미매핑 입력 Auto 0.25, 상위 3개 장기 반영,
   restriction의 worst_possible/worst_known, ADC 정렬 키를 확인해줘.
2. 질환의 소속 장기, 미래 장기 취약성, ADC 독성 예측이 섞여 있지 않은지 봐줘.
3. split, alias 및 family 중복, 전처리, 후처리의 누수 위험을 검토해줘.
   기존 선택용 seed 결과를 독립 확인 결과로 과장하는 부분도 찾아줘.
4. strongest baseline, 튜닝 예산, 학습 자료량, ensemble 수, 속도 측정이 공정한지 봐줘.
5. 기존 LoRA/null/negative 결과를 고려하면 다음 학습 실험의 우선순위가 합리적인지 봐줘.
6. gold 규모와 annotation 방식, 일차 지표, 통과 기준, CI 계산을 검토해줘.
7. lung hole 같은 모호한 입력과 무의미한 문자열의 거절 정책을 평가해줘.
8. 1등 ADC가 Unclear일 때 입력 보완과 연구 후보 탐색으로 나누는 조건을 검토해줘.
   Unclear를 사용 불가능 또는 금기와 같게 해석하지 않도록 해줘.
9. 새 ADC 조합에 대해 현재 구조 모델이나 AlphaFold가 보장할 수 있는 범위를 봐줘.
10. 공모전에서 실제로 주장할 수 있는 결과와 추가 검증이 필요한 주장을 나눠줘.

출력은 다음 형식으로 부탁해.
- 전체 평가: 강점과 가장 큰 병목을 각각 짧게 설명.
- P0/P1/P2 문제 목록: 문제, 근거 파일/함수/JSON key, 영향, 수정 제안.
- 평가 항목별 점수: 아래 rubric을 1~5점으로 채점하고 근거를 설명.
- 가장 먼저 할 실험 3개: 가설, 비교군, split, 지표, 성공/실패 판정, 필요한 자료.
- 계획에서 삭제하거나 뒤로 미룰 작업.
- 현 상태에서 발표 가능한 문장 3개와 발표하면 안 되는 문장 3개.
- 실행 전 필요한 추가 정보. 추정한 사실과 실제 확인한 사실은 구분.

결과가 좋지 않을 가능성도 포함해서 검토해줘. 새로운 학습, 파일 수정,
UI 변경은 이 검토 요청만으로 수행하지 말고 제안으로 정리해줘.
```

## 평가 rubric

| 항목 | 1점 | 3점 | 5점 |
|---|---|---|---|
| 과제 정의 | 질환 분류와 독성 예측 혼동 | 역할 구분 있으나 목표와 지표 불일치 | 과제, gold, 사용 범위가 일치 |
| 데이터와 split | 누수 또는 정답 순환 | group split 있으나 별도 확인 부족 | 독립 gold, fold-safe 처리, 확인 자료 명확 |
| baseline 공정성 | 약한 baseline만 비교 | 강한 baseline 있으나 예산 차이 | 동일 자료와 예산의 강한 대조군 포함 |
| 통계와 주장 | 점 추정만으로 우수성 주장 | CI 있으나 다중 비교 처리 부족 | paired group CI, 사전 기준, 주장 범위 명확 |
| 제품 연결 | 평가가 제품 동작과 다름 | 일부 후처리 및 예외만 평가 | 배포 후처리와 거절 및 통합 경로 검증 |
| 속도 재현성 | 단일 실행 시간 | CPU/GPU 일부 조건 기재 | cold/warm/cache, p95, 메모리, 장비 조건 명확 |
| 설계 확장 | 새 조합 안전성을 근거 없이 주장 | 제약과 한계 일부 존재 | 후보 생성과 구조 검토, 실험 검증 역할 분리 |

점수는 benchmark 정확도와 합산하지 않는다. 종합점수만으로 실행을 승인하지 않고 P0 문제의 해결 여부를 우선한다.

## 원본 확인 시 우선 볼 파일

| 내용 | 파일 |
|---|---|
| 현재 제품 동작 | `ml/recommend.py`, `ml/form.py`, `ml/tui.py` |
| 실제 배포 모델 | `ml/vulnerability_model.py` |
| MONDO 연결 | `ml/mondo_index.py`, `conf/ontology/mondo_organ_axis.yaml` |
| 비교 및 통계 | `ml/lab.py`, `ml/lab_ft.py`, `ml/paired.py`, `ml/results/lab/` |
| 라벨 판단 | `ml/restrictions.py`, `conf/label_restrictions.yaml`, `ml/drug_evidence.py` |
| 기존 음성 결과 | `ml/results/learned_addon.json`, `ml/results/task_d*.json`, `docs/MODEL_CARD.md`, `report/findings.md` |
| 새 조합의 현재 범위 | `src/adctox/design/enumerate.py`, `conf/design_space.yaml` |

## 검토 자료의 상태

현재 작업 디렉터리에는 미커밋 UI 변경이 있다. HEAD만 보고 검토하면 최신 화면과 다른 코드를 읽을 수 있다. 제공된 스냅샷의 해시와 working tree를 기준으로 한다. 로컬 캐시와 원본 워크북이 없는 환경에서는 모든 추론 및 학습을 그대로 재현할 수 없다. 이 경우 확인하지 못한 결과를 직접 재현했다고 서술하지 않는다.

외부 연구는 각 문서에 연결한 원 논문과 공식 문서를 기준으로 확인한다. 기존 README, 기술 보고서, 최신 코드 사이의 차이는 현황 문서의 버전 설명을 참고한다.
