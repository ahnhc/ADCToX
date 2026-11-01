ADCTOX 0.6.5: 화면의 숫자가 무슨 뜻인지 화면에 적었다. Ubuntu, macOS, Windows 모두 0.6.5다.

- **AI 장기 분석의 %는 AI 확신도다.** 이 질환이 그 장기에 관련된다는 판단의 확신도이며 부작용 확률이 아니라고 Organs 열 제목 아래에 적었다.
- **결과 화면의 Organ priority는 Review order가 됐다.** 먼저 검토할 장기 순서이고 위험도 순위가 아니라고 적었다.
- **ADC 상세를 네 부분으로 나눴다.** Indication(입력한 암에 승인됐는지), Label restriction, 환자 장기의 경고, 그 밖의 장기의 경고. 아래 안내는 `Enter 상세 근거 보기`다.
- **검사 수치 화면에서 빈 칸은 미입력, 기준을 넘지 않은 값은 기준 이내로 보인다.** 기준(예: AST > 3 x ULN, CTCAE G2)은 마우스를 올리면 보인다.

모델은 그대로 0.7이다.

```bash
adctox --update-app
```
