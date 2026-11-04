# COVID-Fact evaluation summary

| Split | Model | Prompt | Mode | N | Acc | Macro F1 | Weighted F1 | Invalid | 95% CI |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| test | liquid/lfm2.5-1.2b | few_shot | retrieved | 60 | 71.7% | 0.6679 | 0.7145 | 0 | [60.0%, 83.3%] |
| test | qwen3-0.6b | zero_shot | retrieved | 60 | 58.3% | 0.5823 | 0.5899 | 0 | [45.0%, 71.7%] |

## Per-class metrics

| Split | Model | Prompt | Mode | Class | P | R | F1 | Support |
|---|---|---|---|---|---:|---:|---:|---:|
| test | liquid/lfm2.5-1.2b | few_shot | retrieved | SUPPORTED | 0.5556 | 0.5263 | 0.5405 | 19 |
| test | liquid/lfm2.5-1.2b | few_shot | retrieved | REFUTED | 0.7857 | 0.8049 | 0.7952 | 41 |
| test | qwen3-0.6b | zero_shot | retrieved | SUPPORTED | 0.4211 | 0.8421 | 0.5614 | 19 |
| test | qwen3-0.6b | zero_shot | retrieved | REFUTED | 0.8636 | 0.4634 | 0.6032 | 41 |

## Paper reference values (COVID-Fact, ACL 2021)

- RoBERTa-large with gold evidence: 83.5% accuracy / 82.0 F1 (Table 4).
- RoBERTa-large with top-5 retrieved evidence: 84.7% accuracy / 83.0 F1.
- Claim-only classifier: 67.5% accuracy / 40.0 macro F1.
- COVID-FEVER transfer: 43.3% accuracy.
- Top-5 retrieval: P 22.27 / R 52.37 / F1 31.25 (Table 5).
