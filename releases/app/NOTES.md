ADCTOX 0.6.4: 브라우저 화면 마무리. Ubuntu, macOS, Windows 모두 0.6.4다.

- **ADC 상세가 1280 px부터 세 번째 열로 들어간다.** 인체 지도가 먼저 좁아지고 표는 그대로 다 보인다. 그보다 좁은 화면은 전처럼 덮는다.
- **인체 지도가 모든 단계에 있다.** 질환 화면에서는 비어 있고, 검사 수치 화면에서는 기준을 넘는 값의 장기가 켜진다(Hb 9.1 g/dL이면 Blood). AI 장기 분석부터는 전과 같다.
- **결과 화면을 인쇄할 수 있다** (Ctrl-P). Key values, Organ priority, 표, 범례, 열린 ADC의 상세가 A4로 나온다.
- **Pretendard Variable 글꼴을 내장했다** (SIL Open Font License 1.1). 어느 PC에서나 같은 글꼴로 보인다. 앱이 2 MB 커졌다.
- `adctox --update-app`으로 올린 설치본은 다음 실행 때(`--version`이든 `--help`든) `adctox` 옆에 `adctox-web`이 생긴다.

모델은 그대로 0.7이다.

```bash
adctox --update-app
```
