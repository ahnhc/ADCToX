# Organ labels v5 실행 보고서

완료: 2026-10-22 09:11 KST. 결과: `labels_v5.jsonl`(22,638줄), `agreement.json`, `DONE`.

## 1. Models and settings

- 라벨링·판정·감사 모두 `gpt-6.1-sol`, reasoning effort `high`이다. transport는 `codex-exec-isolated-dir`(ChatGPT 구독, 호출마다 빈 임시 폴더)이고, 동시 세션은 3개다.
- 세션 수와 시간(KST, `runs.jsonl`):

| 단계 | 기간 | 세션 | 통과 배치 |
|---|---|---|---|
| pass1 | 10-21 00:31 → 07:57 | 917 | 906 |
| pass2 | 10-21 07:58 → 16:09 | 910 | 906 |
| pass3 | 10-21 16:10 → 10-22 02:00 | 909 | 906 |
| adjudicate | 10-22 02:31 → 05:52 | 298 | 297 |
| audit | 10-22 06:21 → 08:59 | 485 | 483 |
| 합계 | 32.5시간 | 3,519 | |

- 세션 시간의 합은 94.4시간이다. 사용량 제한(429/403)으로 멈춘 적은 한 번도 없다.
- 재시도한 21회는 모두 형식 문제였다. 가장 많은 것은 "primary도 없고 no_axis도 아님"이고, 줄 수나 id 순서가 틀린 경우도 있었다. 재시도는 모두 다음 시도에 통과했다.

## 2. First attempt

- 첫 시도(10-20)는 `/tmp/adctox_v5_all.py`와 `/tmp/adctox_v5_fresh.py`로 최대 256개 세션을 동시에 열었다. 그 결과 429와 Cloudflare 403을 받았고, 응답의 72%는 도구로 배치 파일을 읽었다는 이유로 거부됐다.
- Codex 세션이 그 디스패처와 하위 세션을 종료했다. 이전 5패스 출력은 `provenance/old_layout_20261021_002910/`에 보관만 했고 쓰지 않는다. 이전 보고서는 `provenance/REPORT_before_restart.md`에 있다.

## 3. Pilot

`--stage pass1 --limit 4`(100개념)를 Codex 세션이 직접 읽고 점검했다. 전문은 `provenance/REPORT_codex_20261021.md` 3절에 있다.

- **30% 규칙:** 대체로 지켰다. 예를 들어 MONDO:0014935는 청력 15/16, 켈로이드 8/18, 성문하 협착 6/15를 넣고 구개열 5/17을 뺐다.
- **기전 축·입·일시적 소견:** 기전 축(infectious_immune, metabolic_endocrine, haematologic)이 들어갔다. 침샘·잇몸은 gastrointestinal로 분류했다. 일시적 발진은 뺐다.
- **basis:** 42~185자였다.
- **우려:** 표본이 아주 작은 HPO 빈도(1/1, 2/2)를 일반화한 사례가 있다(MONDO:0014098 간, MONDO:0032763 기관지확장).

## 4. Counts

| 결정 방식 | 개념 |
|---|---|
| 3패스 모두 일치 | 19,528 |
| 판정 | 2,876 |
| 감사에서 수정 | 234 |
| 합계 | 22,638 |

- no_axis는 1,443개다. confidence는 high 16,268, medium 6,214, low 156이다.
- primary 수: 0개 1,443 · 1개 13,838 · 2개 5,318 · 3개 2,039. involved가 있는 개념은 4,571개(20%)다.
- vote 직후 확정은 19,671개였다. 그중 143개는 감사에서 수정돼 위 표의 "감사에서 수정"으로 옮겨졌다.

## 5. Agreement

장기별 패스 간 κ(`agreement.json`), 낮은 순:

pulmonary 0.937 · hepatic 0.944 · musculoskeletal 0.945 · gastrointestinal 0.948 · cardiovascular 0.953 · renal 0.953 · ocular 0.956 · haematologic 0.958 · otologic 0.958 · dermatologic 0.961 · neurologic 0.969 · metabolic_endocrine 0.970 · infectious_immune 0.980

- 가장 낮은 축은 pulmonary, hepatic, musculoskeletal이다. 셋 다 다장기 질환에서 involved로 넣을지가 갈리는 축이다. 예를 들면 골격 이상의 빈도, 간 비대·지방간, 호흡 기능 저하를 직접 손상으로 볼지가 갈린다.
- 한 패스와 최종 라벨의 일치는 장기마다 0.985~0.997이다.

## 6. Recurring disagreements

판정 `decisions`에서 가장 많았던 (장기, 결정)과 예시 개념:

| # | 장기 → 결정 | 건수 | 예시 |
|---|---|---|---|
| 1 | musculoskeletal → none | 269 | MONDO:0009748, MONDO:0003370 |
| 2 | musculoskeletal → involved | 212 | MONDO:0001586, MONDO:0976226 |
| 3 | neurologic → primary | 176 | MONDO:0800180, MONDO:0000550 |
| 4 | musculoskeletal → primary | 176 | MONDO:0017081, MONDO:0020479 |
| 5 | neurologic → involved | 173 | MONDO:0980992, MONDO:0017182 |
| 6 | ocular → none | 153 | MONDO:0030261, MONDO:0017091 |
| 7 | ocular → involved | 152 | MONDO:0015781, MONDO:0001586 |
| 8 | gastrointestinal → none | 138 | MONDO:0100361, MONDO:0023100 |
| 9 | gastrointestinal → primary | 122 | MONDO:0007257, MONDO:0002014 |
| 10 | metabolic_endocrine → primary | 117 | MONDO:0006944, MONDO:0100646 |

- 가장 많이 갈린 것은 증후군의 골격 소견을 involved로 볼지(1·2)였다. 소수 환자에서만 보고된 빈도, 그리고 발달 이상과 손상의 구분 때문이다.
- 그다음은 primary가 하나인지 둘인지(3·4·9·10)였다. 예를 들어 신경근육 질환에서 neurologic과 musculoskeletal을 함께 primary로 둘지가 갈렸다.
- 마지막은 눈·입 소견의 경계(6~8)였다. 안검하수와 입술 병변을 ocular·gastrointestinal로 볼지가 갈렸다.

## 7. Audit

대상은 4,825개념(483배치)이고, 이 중 234개를 고쳤다.

| 감사 이유 | 수정 / 대상 | 비율 |
|---|---|---|
| 부모 질환의 정의 장기가 빠짐 | 161 / 2,483 | 6.5% |
| v4와 장기 2개 이상 다름 | 113 / 2,315 | 4.9% |
| confidence low | 9 / 162 | 5.6% |
| **확정분 무작위 3%** | **9 / 576** | **1.6%** |

- 한 개념이 이유 여러 개에 걸릴 수 있어 대상 수의 합은 4,825보다 크다.
- 무작위 표본의 수정률 1.6%는 멈춤 기준 5%보다 낮다. 그래서 assemble을 진행했다.

## 8. Problems

- GUIDE_v5.md, ADJUDICATE.md, AUDIT.md, 입력 파일과 `ml/relabel_v5*.py`는 수정하지 않았다.
- 3패스가 끝난 뒤(10-22 02:00) Codex 세션은 다음 단계로 넘어가지 않았다. 그 세션의 마지막 보고서 갱신은 10-21 00:33이었다. 그래서 4~7단계(vote, adjudicate, audit, assemble)와 이 보고서는 Claude가 GPT_TASK.md의 같은 명령과 같은 러너·모델·설정으로 수행했다. 라벨 내용은 모두 gpt-6.1-sol 세션이 썼고, Claude가 쓰거나 고친 라벨은 없다.
- `audit` 명령을 실수로 한 번 더 실행했다. merged()의 안전 검사("audit incomplete")에 걸려 멈췄고, 이미 만든 감사 배치는 바뀌지 않았다.
- 규칙에 대한 관찰은 하나다. 표본이 1~2명인 HPO 빈도에도 30% 규칙이 그대로 적용된다. 판정과 감사가 일부를 걸렀지만, 표본 크기에 따른 하한은 규칙에 없다.

## 9. 이 보고서 이후: v5.1 (2026-10-22 ~ 10-23)

8절의 관찰과 선천 구조 이상 문제 때문에 involved 장기만 다시 검토했다.
- 규칙은 [RULE_v5_1.md](RULE_v5_1.md)에 있다. GUIDE_v5.md는 바꾸지 않았다.
- 결과 파일:
  - `review_v5_1.jsonl`: 검토한 장기 6,384개와 각 투표
  - `labels_v5_1.jsonl`: Haiku 두 명이 모두 뺀 1,375개를 반영한 라벨
  - `labels_v5_1_final.jsonl`: 그중 GPT가 남기라고 한 156개를 되살리고 최종 1,218개를 뺀 라벨
- 학습 결과는 [ml/docs/relabel_v5_plan.md](../../../../ml/docs/relabel_v5_plan.md) 결과 절에 있다.
