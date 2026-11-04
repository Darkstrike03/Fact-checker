# COVID-Fact Resources

This folder contains the COVID-Fact paper and the official RTE-format dataset splits used for evaluation.

## Citation

Arkadiy Saakyan, Tuhin Chakrabarty, and Smaranda Muresan. 2021.
COVID-Fact: Fact Extraction and Verification of Real-World Claims on COVID-19 Pandemic.
In Proceedings of the 59th Annual Meeting of the Association for Computational Linguistics
and the 11th International Joint Conference on Natural Language Processing (Volume 1: Long Papers),
pages 2116-2129, Online. Association for Computational Linguistics.

- ACL Anthology: https://aclanthology.org/2021.acl-long.165/
- arXiv: https://arxiv.org/abs/2106.03794
- Official code and data: https://github.com/asaakyan/covidfact

The paper PDF in this folder is the supplied ACL 2021 paper. The table values used in
this project were cross-checked against the published ACL/arXiv version.

## Dataset files

The files are the official `RTE-covidfact` splits:

- `COVID_FACT_DATASET/train.tsv`: 3,263 rows
- `COVID_FACT_DATASET/dev.tsv`: 419 rows
- `COVID_FACT_DATASET/test.tsv`: 401 rows

Each row contains:

- `index`: row identifier
- `sentence1`: evidence sentence (premise)
- `Sentence2`: claim (hypothesis)
- `label` or `entailment`: binary label

The column is named `label` in train/test and `entailment` in dev.

## Label alignment

The project does not invent new verdict labels for evaluation. The mapping is:

| Dataset label | Paper label | Allowed output |
|---|---|---|
| `entailment` | SUPPORTED | `SUPPORTED` |
| `not_entailment` | REFUTED | `REFUTED` |

The primary UI label follows the same mapping. `ABSTAIN` is reserved for a future
abstention mode and must not be mapped to either dataset label.
