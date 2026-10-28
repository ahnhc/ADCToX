ADCTOX 0.6.1: ADC 상세에서 라벨 절 번호를 뺐다. 이번 버전은 Ubuntu와 macOS용이고, Windows는 0.5.5 그대로다.

- **경고 이름만 보인다.** `Lung  !!  Interstitial Lung Disease/Pneumonitis`처럼 장기 옆에 라벨 경고 이름만 나온다(전에는 `Boxed INTERSTITIAL LUNG DISEASE; 5.1 Interstitial Lung Disease/Pneumonitis`). Boxed warning 이름이 5절 제목에 들어 있으면 한 번만 나온다.
- payload 기전 문장 끝의 `[12.1]` 같은 표시를 뺐다. `--plain` 출력도 같다.

모델은 그대로 0.7이다.

```bash
adctox --update-app
```
