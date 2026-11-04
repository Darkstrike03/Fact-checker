# COVID-Fact evaluation summary

| Split | Model | Prompt | Mode | N | Acc | Macro F1 | Weighted F1 | Invalid | 95% CI |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| dev | liquid/lfm2.5-1.2b | few_shot | gold | 419 | 59.4% | 0.5836 | 0.6089 | 0 | [54.9%, 64.0%] |
| dev | liquid/lfm2.5-1.2b | zero_shot | gold | 419 | 33.7% | 0.2783 | 0.2005 | 0 | [29.6%, 37.7%] |

## Per-class metrics

| Split | Model | Prompt | Mode | Class | P | R | F1 | Support |
|---|---|---|---|---|---:|---:|---:|---:|
| dev | liquid/lfm2.5-1.2b | few_shot | gold | SUPPORTED | 0.4099 | 0.7000 | 0.5170 | 130 |
| dev | liquid/lfm2.5-1.2b | few_shot | gold | REFUTED | 0.8020 | 0.5467 | 0.6502 | 289 |
| dev | liquid/lfm2.5-1.2b | zero_shot | gold | SUPPORTED | 0.3186 | 1.0000 | 0.4833 | 130 |
| dev | liquid/lfm2.5-1.2b | zero_shot | gold | REFUTED | 1.0000 | 0.0381 | 0.0733 | 289 |

## Paper reference values (COVID-Fact, ACL 2021)

- RoBERTa-large with gold evidence: 83.5% accuracy / 82.0 F1 (Table 4).
- RoBERTa-large with top-5 retrieved evidence: 84.7% accuracy / 83.0 F1.
- Claim-only classifier: 67.5% accuracy / 40.0 macro F1.
- COVID-FEVER transfer: 43.3% accuracy.
- Top-5 retrieval: P 22.27 / R 52.37 / F1 31.25 (Table 5).
