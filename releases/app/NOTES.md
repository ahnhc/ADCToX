ADCToX 0.7.3: automatic app updates

- The installed app checks GitHub for a newer release at every start and every 10 minutes while running, then downloads, verifies and switches to it by itself. Set ADCTOX_NO_AUTO_UPDATE=1 to turn it off, ADCTOX_AUTO_RESTART=1 to restart a running server at once.
- Structure Studio: comparison drawer against the approved ADC, wider side drawer, Auto Optimize under Fc engineering, clearer bystander and normal-tissue wording.

Apps before 0.7.3 need `adctox --update-app` once. Models remain at 0.8. This release has the Linux/macOS archive only; the Windows zip stays at 0.7.1.
