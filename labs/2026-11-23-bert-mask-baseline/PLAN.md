# Plan: BERT MLM toy baseline shape

Registered 2026-11-23. Add dated notes under Amendments; do not rewrite registered sections.

## Question

Does a one-layer bag-of-embeddings MLM head on a 32-token toy corpus reach finite masked NLL
strictly below chance (`log V`)?

## Motivation

Child of the attention toy lab: give the dashboard a lab with a parent link and a BERT citation
without claiming a real pretrain.

## Prior anchors

Parent: [`2026-11-23-toy-scaled-dot-product`](../2026-11-23-toy-scaled-dot-product/REPORT.md).
Reference: [Devlin et al. 2018](../../references/bert-pretraining/provenance.json).

## Hypotheses and alternatives

- Working: even a shallow head beats chance on its own training tokens.
- Rival: broken masking / softmax would stay at chance.

## Setting

- Vocab 50, seq 32, dim 16, 200 SGD steps, seed 2
- Mask every 4th token
- CPU NumPy only

## Design

Single training curve; compare final masked NLL to `log(vocab)`.

## Success criterion

`final_nll < chance_nll` in `results/toy_mlm_seed2.json`.

## Stop rules

Fixed 200 steps.

## Completion

REPORT cites the JSON. Wiki: none for this exploratory baseline.

## Amendments

None.
