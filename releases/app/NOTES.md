ADCTOX 0.6.9: Label restriction이 환자의 무엇이 라벨의 어떤 규칙에 걸렸는지 보인다. Ubuntu, macOS, Windows 모두 0.6.9다.

- **Label restriction은 두 줄이다.** `Patient`는 걸린 환자 쪽(Heart failure, Bilirubin 1.67×ULN, 또는 LVEF not entered)이고, `Label`은 라벨의 규칙("Monitor with bilirubin >1.5 to 3×ULN", "Not studied if LVEF < 50%")이다.
- **Indication은 문장으로 보인다.** "Approved for" 또는 "Not approved for" 입력한 암, 그 아래에 All approved uses 목록이다.
- **마우스를 올리면 뜨는 설명은 요약 한 줄과 항목 줄이다.**
- Windows 설치 확인에서 브라우저 화면까지 열어 본다.

모델은 그대로 0.7이다.

```bash
adctox --update-app
```
