ADCTOX 0.3.1: search as you type, symptom search, macOS, one-line installers.

- **입력 즉시 추천:** 첫 화면에 질환 목록이 없다.
  - 질환명을 입력하면 아래에 추천이 바로 뜨고, 한 글자마다 바뀐다.
  - 한국어, 영어, 약어, 초성(ㄷㄴ), 오타(diabetis) 모두 된다.
  - 입력을 잠시 멈추면 AI(SapBERT) 추천을 덧붙인다.
- **증상·문장으로 찾기:** TAB을 누르면 증상, 치료, 문장으로 질환을 찾는다. 예: `투석 중이고 숨이 차요`.
- **모델 업데이트 키:** 글자가 검색창에 입력되므로 `U`에서 `Ctrl+U`로 바꿨다.
- **macOS (Apple silicon) 지원**과 운영체제별 한 줄 설치:

```bash
curl -fsSL https://raw.githubusercontent.com/ahnhc/ADCToX/main/install.sh | bash      # Linux, macOS
```

```powershell
irm https://raw.githubusercontent.com/ahnhc/ADCToX/main/install.ps1 | iex             # Windows (PowerShell)
```

이미 설치했다면 `adctox --update-app`. 모델 묶음은 0.2 그대로다.
