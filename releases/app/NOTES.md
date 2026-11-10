ADCToX 0.7.5: bilingual layout refinement, bar alignment, and responsive design chart

- Verified KO/EN layout and docked-drawer responsiveness across all three workspace modes so labels, badges, and studio pills never wrap awkwardly or collide.
- Aligned horizontal comparison bars across spotlight cards, matrix rows, and studio panels, and removed the 3D rotation overlay hint.
- Fixed the Patient-Tailored ADC Design scatter plot (`ResizeObserver` + dynamic DPR sizing) so opening/closing the side drawer or switching tabs never distorts the chart.
- Streamlined the scoring explanation to focus directly on the safety and efficacy calculation formulas.

Apps at 0.7.3+ update automatically; older apps need `adctox --update-app` once. Models remain at 0.8.
