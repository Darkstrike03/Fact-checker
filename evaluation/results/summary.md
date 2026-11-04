# COVID-Fact evaluation summary

| Split | Model | Prompt | Mode | N | Acc | Macro F1 | Weighted F1 | Invalid | 95% CI |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| test | liquid/lfm2.5-1.2b | few_shot | gold | 401 | 64.3% | 0.6301 | 0.6548 | 0 | [59.6%, 68.8%] |
| test | liquid/lfm2.5-1.2b | zero_shot | gold | 401 | 34.7% | 0.2812 | 0.2049 | 0 | [29.9%, 39.4%] |
| test | qwen3-0.6b | few_shot | gold | 401 | 33.9% | 0.2765 | 0.2016 | 0 | [29.4%, 38.7%] |
| test | qwen3-0.6b | zero_shot | gold | 401 | 54.6% | 0.5413 | 0.5578 | 0 | [50.1%, 59.4%] |

## Per-class metrics

| Split | Model | Prompt | Mode | Class | P | R | F1 | Support |
|---|---|---|---|---|---:|---:|---:|---:|
| test | liquid/lfm2.5-1.2b | few_shot | gold | SUPPORTED | 0.4667 | 0.7000 | 0.5600 | 130 |
| test | liquid/lfm2.5-1.2b | few_shot | gold | REFUTED | 0.8107 | 0.6162 | 0.7002 | 271 |
| test | liquid/lfm2.5-1.2b | zero_shot | gold | SUPPORTED | 0.3316 | 1.0000 | 0.4981 | 130 |
| test | liquid/lfm2.5-1.2b | zero_shot | gold | REFUTED | 1.0000 | 0.0332 | 0.0643 | 271 |
| test | qwen3-0.6b | few_shot | gold | SUPPORTED | 0.3265 | 0.9769 | 0.4894 | 130 |
| test | qwen3-0.6b | few_shot | gold | REFUTED | 0.7500 | 0.0332 | 0.0636 | 271 |
| test | qwen3-0.6b | zero_shot | gold | SUPPORTED | 0.3870 | 0.6846 | 0.4944 | 130 |
| test | qwen3-0.6b | zero_shot | gold | REFUTED | 0.7602 | 0.4797 | 0.5882 | 271 |

## Paper reference values (COVID-Fact, ACL 2021)

- RoBERTa-large with gold evidence: 83.5% accuracy / 82.0 F1 (Table 4).
- RoBERTa-large with top-5 retrieved evidence: 84.7% accuracy / 83.0 F1.
- Claim-only classifier: 67.5% accuracy / 40.0 macro F1.
- COVID-FEVER transfer: 43.3% accuracy.
- Top-5 retrieval: P 22.27 / R 52.37 / F1 31.25 (Table 5).
