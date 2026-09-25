---
title: Probability Rules and Bayes Theorem
subject: Statistics
topic: Probability
tags: probability, bayes, conditional probability, independence
---
## Basic Rules
- $0 \leq P(A) \leq 1$, all outcomes sum to 1
- complement: $P(A^c) = 1 - P(A)$
- addition rule: $P(A \cup B) = P(A) + P(B) - P(A \cap B)$. mutually exclusive -> the intersection is 0
- multiplication rule: $P(A \cap B) = P(A) \cdot P(B|A)$
- independent events: $P(A \cap B) = P(A)P(B)$, knowing A tells you nothing about B. independent is NOT the same as mutually exclusive!

## Conditional Probability
$P(A|B) = \frac{P(A \cap B)}{P(B)}$, probability of A given B already happened. shrinks the sample space to B. use a tree diagram or two way table.

## Bayes Theorem
$$P(A|B) = \frac{P(B|A) P(A)}{P(B)}$$ flips the conditional. Denominator by law of total probability: $P(B) = P(B|A)P(A) + P(B|A^c)P(A^c)$. Classic: medical test w/ 99% sensitivity but rare disease (1%) -> positive test still means only around 50% chance of disease b/c of false positives. base rate matters!

## Counting
permutations (order matters) $nPr = \frac{n!}{(n-r)!}$, combinations (order doesnt) $nCr = \frac{n!}{r!(n-r)!}$
