# Organ labels v5 실행 보고서 — 진행 중

갱신: 2026-10-21T00:29:47+09:00

## 1. Models and settings
- 모든 라벨링·판정·감사: `gpt-6.1-sol`, reasoning effort `high` (기존 러너 기본값 유지).
- Transport: `codex-exec-isolated-dir`; ChatGPT 구독 인증 사용.
- 지정 Python: `/data/hyeongchanahn/envs/adctox/bin/python`, `ADC_RESEARCH_MODE=1`.
- 파일럿 완료: 4배치/100개. 전체 3패스 러너 PID: 2959800. 동시 워커 3개. `nohup setsid`로 셸에서 분리했으며 PPID=1, SID=2959800 확인.
- 새 실행 세션 수와 제한 대기는 `runs.jsonl` 중 transport가 위 값인 기록 및 `provenance/codex_pilot.log`로 집계 예정.

## 2. First attempt
- 이전 시도는 최대 256개 동시 세션으로 429/403 제한을 받았고, 배치 파일 도구 읽기를 이유로 많은 응답을 거절했다(GPT_TASK.md 기록).
- `/tmp/adctox_v5_fresh.py`를 직접 실행하는 프로세스는 없었으나, 이를 사용하는 `/tmp/adctox_v5_all.py` PID 2252252가 남아 자식 세션을 계속 생성하고 있었다. 해당 디스패처와 이전 ephemeral Sol exec 세션 및 하위 프로세스를 종료했다.
- 종료 후 지정 확인 명령 `pgrep -fc "adctox_v5_fresh|codex exec"` 결과 0 확인. app-server와 현재 대화 세션은 종료하지 않았다.
- 기존 5패스 출력은 `provenance/old_layout_20261021_002910/`로 prepare가 보관했으며 새 패스에 사용하지 않는다. 이전 보고서는 `provenance/REPORT_before_restart.md`에 보존했다.

## 3. Pilot
- `--stage pass1 --limit 4` 완료: `b_0000.jsonl`~`b_0003.jsonl`, 총 100개. 러너 결과 `ok: 4`.
- 100개 출력 라인을 직접 읽고 입력의 이름·정의·부모와 대조했다. 빈도·정의 충돌이 있는 사례는 HPO와 상세 입력도 확인했다. 별도로 기존 validator로 4배치의 ID·순서·형식을 재확인했다.
- **30% 규칙:** PGK1 결핍 MONDO:0010392는 신경계 30~79%를 포함하고 신장·망막 5~29%를 제외했다. MONDO:0014935는 청력 15/16, 켈로이드 8/18, 성문하 협착 6/15를 포함하고 구개열 5/17을 제외했다. MONDO:0008970는 2/2 대동맥 축착 기록보다 집계 빈도 5~29%를 우선해 심혈관을 제외했다. 명확한 30% 미만 합병증의 일괄 과잉 추가는 보이지 않았다.
- **기전 축:** 감염·면역 질환(예: MONDO:0800144, MONDO:0018003, MONDO:0018813), 대사 질환(MONDO:0017728, MONDO:0040500), 혈액 질환(MONDO:0015165, MONDO:0030711)에 해당 primary 축이 반영됐다.
- **입·침샘:** MONDO:0006357, MONDO:0044740의 침샘 종양을 gastrointestinal로 분류했다. MONDO:0008389는 잇몸 증식·구강 이상 30~79%로 gastrointestinal involved를 부여했다.
- **일시적 소견:** MONDO:0019434의 전신형 소아 관절염 발진을 일시적 소견으로 제외했다. 근긴장이상(MONDO:0044811, MONDO:0011200)의 근수축을 별도의 근육 손상으로 확대하지 않았다.
- **basis:** 공백 없음, 길이 42~185자(상한 200). 파일럿 no_axis는 7개이며 최종 집계는 아니다.
- **경계/우려 사례:** MONDO:0014098의 간 침범 1/1, MONDO:0032763의 기관지확장 2/2 등 작은 표본의 일반화에는 불확실성이 남는다. MONDO:0006146은 부위 불명 chondroid hamartoma를 폐로 추정해 medium으로 기록했다. MONDO:0000715의 림프절 carcinoma를 no_axis로 보는 선택은 림프절의 축 매핑이 명시적이지 않아 경계 사례다. MONDO:0010490의 GI involved는 반복 구토·역류/기능장애가 직접 손상 요건을 충분히 충족하는지 검토 여지가 있다. MONDO:0013556의 폐 제한성 환기장애 3/7과 섬유화 1/7의 해석도 경계다.
- MONDO:0019788은 비분비성 종양 정의와 카테콜아민 관련 HPO가 충돌하는 점을 basis에 명시하고 추가 합병증 축을 붙이지 않았다.
- 전체적으로 지정한 다섯 점검 항목에서 광범위한 누락·과잉 패턴은 관찰하지 못했지만, 위 항목은 오류 가능성이 남는 관찰 사항이다. 지침·입력·출력은 수정하지 않았고 다른 패스에 이 의견이나 파일럿 결과를 제공하지 않았다.

## 4. Counts
- manifest: 개념 22,638개, 3패스, 배치당 25개, 패스당 906배치.
- settled/adjudicated/audit-corrected/no_axis: 아직 미집계.

## 5. Agreement
3패스 완료 후 집계.

## 6. Recurring disagreements
판정 완료 후 decisions의 상위 10개 이유와 각 2개 예시를 기재.

## 7. Audit
미실행. 무작위 표본 수정률이 5%를 넘으면 보고 후 중지한다.

## 8. Problems / 현재 상태와 재개
- GUIDE_v5.md, ADJUDICATE.md, AUDIT.md, 입력 파일은 수동 편집하지 않았다. 입력과 배치는 지정 prepare 명령으로만 재생성했다. 스크립트 변경 없음. 새 러너를 작성하지 않았다.
- 평가 데이터 경로를 직접 열거나 평가 개념을 탐색하지 않았다.
- 첫 nohup 파일럿 실행은 셸 종료 후 유지되지 않아 출력 없이 종료됐다. 유지되는 exec 세션으로 파일럿을 완료했고, 본 실행은 `nohup setsid`로 분리했다. 이는 기존 지정 Python 러너를 실행하는 셸 방식만 바꾼 것이다.
- 현재 3패스 라벨링이 백그라운드에서 진행 중이다. vote·adjudicate·audit·assemble은 아직 수행하지 않았다. 최종 산출물과 DONE은 아직 없다.
- 전체 작업은 약 2,700 세션과 며칠이 예상되므로 이번 대화 종료 시점의 상태와 재개 절차를 여기에 남긴다. 백그라운드 러너는 패스 완료까지만 수행하며, 다음 단계는 별도로 진행해야 한다.
- 파일럿 로그: `data/curated/concept_organs/v5/provenance/codex_pilot.log`.
- 본 실행 로그: `data/curated/concept_organs/v5/provenance/codex_passes.log`.
- 아래 명령은 모두 저장소 루트 `/home/hyeongchanahn/CONI/adctox`에서 실행한다.

```bash
# 먼저 실행 상태와 로그 확인. 살아 있으면 중복 실행하지 않는다.
ps -p 2959800 -o pid,ppid,sid,etime,args
tail -n 30 data/curated/concept_organs/v5/provenance/codex_passes.log
# 종료된 경우에만 같은 러너를 재개 (완료 배치는 자동 건너뜀):
ADC_RESEARCH_MODE=1 nohup setsid /data/hyeongchanahn/envs/adctox/bin/python ml/relabel_v5_codex.py --stage all --workers 3 > data/curated/concept_organs/v5/provenance/codex_passes.log 2>&1 < /dev/null &
```

제한 대기는 러너가 15/30/60분 처리하므로 재시작 반복이나 워커 증설을 하지 않는다. 제한 대기가 대략 시간당 1회보다 잦으면 기존 러너와 해당 하위 exec를 안전하게 종료한 뒤 `--workers 2`로 재개한다. 전체 동시 codex exec는 4개를 넘기지 않는다.

패스 러너 종료 후 다음을 수행한다. 누락·무효가 있으면 위 러너로 먼저 채운다.

```bash
for k in 1 2 3; do ADC_RESEARCH_MODE=1 /data/hyeongchanahn/envs/adctox/bin/python ml/relabel_v5.py check --stage pass$k; done
# 세 패스 모두 missing=0, invalid=0일 때만:
ADC_RESEARCH_MODE=1 /data/hyeongchanahn/envs/adctox/bin/python ml/relabel_v5.py vote
ADC_RESEARCH_MODE=1 nohup setsid /data/hyeongchanahn/envs/adctox/bin/python ml/relabel_v5_codex.py --stage adjudicate --workers 3 > data/curated/concept_organs/v5/provenance/codex_adjudicate.log 2>&1 < /dev/null &
```

판정 러너가 종료된 뒤 `check --stage adjudicate`를 통과시키고, GPT_TASK.md 6~8단계의 audit 생성·실행·check, 무작위 표본 수정률 확인을 수행한다. 5% 초과면 보고 후 멈추고, 아니면 assemble 및 8개 섹션의 최종 보고서를 작성한다. prepare와 파일럿은 완료했으므로 다시 준비하지 않는다. DONE·labels_v5.jsonl·agreement.json·REPORT.md 확인 전에는 완료로 보고하지 않는다.

마지막 상태 확인: 2026-10-21T00:33:42+09:00. 새 transport 기록 4개, 성공 4개, 제한 기록 0개. 실행 중인 세션은 완료 후 기록된다.
