---
title: Hypothesis Testing and Error Types
subject: Statistics
topic: Inference
tags: hypothesis test, p-value, type I error, type II error, power
---
## Setup
- null hypothesis $H_0$: no effect / no difference / status quo (always has =)
- alternative $H_a$: what you want evidence for (<, >, or $\neq$ for two sided)
- significance level $\alpha$, usually 0.05, chosen BEFORE looking at data
- test statistic (z or t) measures how far the sample is from $H_0$ in SEs

## P-value
Probability of getting a result at least as extreme as ours IF $H_0$ is true. Small p (< $\alpha$) -> reject $H_0$, result is statistically significant. Large p -> fail to reject (never "accept" $H_0$). p-value is NOT the probability $H_0$ is true.

## Type I and Type II Errors
- Type I error: reject $H_0$ when its actually true. false positive. probability = $\alpha$. "convicting an innocent person"
- Type II error: fail to reject $H_0$ when its actually false. false negative. probability = $\beta$. "letting a guilty person go"
- Power = $1 - \beta$ = probability of correctly rejecting a false $H_0$
- increase power by: bigger sample size, bigger effect size, larger $\alpha$ (tradeoff w/ type I)
- lowering $\alpha$ reduces type I but increases type II

## t vs z
use z when population SD known (rare), t when using sample SD s. t has heavier tails, df = n - 1, approaches z as n grows
