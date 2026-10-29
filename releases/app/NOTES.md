ADCTOX 0.6.1: ADC 상세에서 라벨 절 번호를 뺐다. Ubuntu, macOS, Windows 모두 0.6.1이다.

- **경고 이름만 보인다.** `Lung  !!  Interstitial Lung Disease/Pneumonitis`처럼 장기 옆에 라벨 경고 이름만 나온다(전에는 `Boxed INTERSTITIAL LUNG DISEASE; 5.1 Interstitial Lung Disease/Pneumonitis`). Boxed warning 이름이 5절 제목에 들어 있으면 한 번만 나온다.
- payload 기전 문장 끝의 `[12.1]` 같은 표시를 뺐다. `--plain` 출력도 같다.

모델은 그대로 0.7이다.

```bash
adctox --update-app
```

Windows는 0.5.5 다음 버전으로 이번에 바로 0.6.1이 된다. 0.5.6부터 0.6.0까지의 변화도 함께 들어 있다.
