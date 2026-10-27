ADCTOX 0.5.4: 검사값 경계 판정과 AI 분석 화면 수정.

- **bilirubin, AST, ALT의 ULN 배수와 Cockcroft–Gault CLcr를 반올림하지 않고 라벨 기준과 비교한다.** 전에는 bilirubin 3.601 mg/dL(ULN 1.2)이 3.00×ULN으로 반올림되어 Datopotamab deruxtecan의 ">3×ULN" 대신 "≤3×ULN" 규칙을 받았다. 화면에서만 반올림하고, 기준값과 같아 보이지 않게 필요한 만큼 자리를 더 보여 준다(3.001×ULN).
- **AI 분석 중 화면에서 모델 이름을 없앴다.** 실제 진행에 맞춰 "질환 확인 중..." 또는 "장기 분석 중..."을 한 줄로 보여 준다. 캐시된 분석은 바로 결과가 나온다.
- **Organ judge가 실패하면 그렇다고 표시한다.** 이전 MONDO linker로 대체한 경우 "Organ judge 오류 · MONDO linker로 대체"와 Read as의 `linker`가 보인다. 진행할 수 없는 오류는 한 줄로 보여 준다.
- 80×24 터미널에서 분석 표, 우선순위 목록, 결과 목록이 선택한 행을 따라 스크롤되고 머리글이 사라지지 않는다.

모델은 그대로 0.7이다.

```bash
adctox --update-app
```
