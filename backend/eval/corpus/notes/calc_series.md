---
title: Sequences and Series Convergence Tests
subject: Math
topic: Calculus
tags: series, convergence, taylor, geometric
---
## Sequences vs Series
Sequence = list of terms $a_n$. Series = sum $\sum a_n$. Partial sums $S_n$. Series converges if partial sums approach a limit.

## Special Series
- geometric $\sum ar^n$ converges to $\frac{a}{1-r}$ if $|r| < 1$, diverges otherwise
- p-series $\sum \frac{1}{n^p}$ converges if p > 1 (harmonic series p=1 diverges!)
- telescoping - terms cancel, find partial sum directly

## Convergence Tests
- nth term test: if $a_n$ does not go to 0, diverges. (going to 0 proves NOTHING)
- integral test: $\sum a_n$ and $\int f(x) dx$ do the same thing, f positive decreasing
- comparison / limit comparison: compare to a known p-series or geometric
- ratio test: $L = \lim \left|\frac{a_{n+1}}{a_n}\right|$, L < 1 converges, L > 1 diverges, L = 1 inconclusive. best for factorials and exponentials
- alternating series test: terms alternate, decrease, and go to 0 -> converges
- absolute vs conditional convergence

## Taylor Series
$f(x) = \sum \frac{f^{(n)}(a)}{n!}(x - a)^n$, Maclaurin when a = 0. Know: $e^x = \sum \frac{x^n}{n!}$, $\sin x = x - \frac{x^3}{3!} + \frac{x^5}{5!} - ...$, $\frac{1}{1-x} = \sum x^n$. radius of convergence from ratio test.
