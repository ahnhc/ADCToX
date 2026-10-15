ADCTOX 0.3.7: clicks, organ strips, fast organ judgment (with models 0.4).

- **마우스:** 모든 화면을 마우스로 쓸 수 있다.
  - 추천, 선택 목록, 탭, 검사 칸, 선택지, 우선순위 − / +를 클릭한다.
  - 오른쪽 위 `◀ 이전` / `다음 ▶` 버튼, 휠 스크롤.
- **장기 표시:** 장기 글자 설명 대신 `혈간심폐콩위뇌눈피대뼈면귀` 한 줄을 쓴다(초록 = 연결된 장기, 노랑 = 모델 추정).
- **입력:** 빠르게 쳐도 밀리지 않는다.
- **AI 판정 (모델 0.4):** 질환을 정확히 못 찾아도 입력 문장에서 장기를 바로 판정한다.
  - 전체 정확도(gold test macro-F1): 0.747 → 0.811
  - 일상 표현: 0.54 → 0.75

업데이트:

```bash
adctox --update-app
```

```bash
adctox --update-models
```

새 설치:

```bash
curl -fsSL https://raw.githubusercontent.com/ahnhc/ADCToX/main/install.sh | bash      # Linux, macOS
```

```powershell
irm https://raw.githubusercontent.com/ahnhc/ADCToX/main/install.ps1 | iex             # Windows (PowerShell)
```
