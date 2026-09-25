---
title: Binomial and Poisson Distributions
subject: Statistics
topic: Probability
tags: binomial, poisson, discrete distributions
---
## Random Variables
Discrete = countable outcomes (number of heads). Continuous = any value in a range (height). Expected value $E(X) = \sum x P(x)$, variance $\sum (x - \mu)^2 P(x)$.

## Binomial
Conditions (BINS): Binary outcomes, Independent trials, fixed Number of trials n, Same probability p each trial. $$P(X = k) = \binom{n}{k} p^k (1-p)^{n-k}$$ mean $\mu = np$, variance $np(1-p)$, SD $\sqrt{np(1-p)}$. ex: 10 coin flips, P(exactly 3 heads). normal approx ok when $np \geq 10$ and $n(1-p) \geq 10$.

## Geometric
number of trials until the FIRST success. $P(X = k) = (1-p)^{k-1} p$, mean $1/p$

## Poisson
Counts of events in a fixed interval of time or space when events happen at a constant average rate $\lambda$ and independently. $$P(X = k) = \frac{\lambda^k e^{-\lambda}}{k!}$$ mean = variance = $\lambda$. ex: calls to a help desk per hour, typos per page. approximates binomial when n large and p small ($\lambda = np$).
