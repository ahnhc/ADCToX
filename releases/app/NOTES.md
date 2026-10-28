ADCTOX 0.5.7: AI 분석이 CPU에서 훨씬 빨라졌다. 이번 버전은 Ubuntu와 macOS용이고, Windows는 0.5.5 그대로다.

- **CPU 스레드를 최대 4개로 쓴다.** 전에는 코어 수만큼 스레드를 띄워, 질환 몇 개를 분석할 때 대부분의 스레드가 서로 기다렸다. 24코어 서버에서 질환 4개 분석이 14~19초에서 1.1~1.4초로 줄었다. `ADCTOX_THREADS` 또는 직접 정한 `OMP_NUM_THREADS`가 있으면 그 값을 따른다.

모델은 그대로 0.7이다.

```bash
adctox --update-app
```
