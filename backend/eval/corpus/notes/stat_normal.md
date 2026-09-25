---
title: Normal Distribution and Z Scores
subject: Statistics
topic: Distributions
tags: normal distribution, z score, central limit theorem
---
## Normal Distribution
Bell shaped, symmetric, defined by mean $\mu$ and SD $\sigma$, written $N(\mu, \sigma)$. Total area = 1. Mean = median = mode. Standard normal is N(0, 1).

## Z Scores
$$z = \frac{x - \mu}{\sigma}$$ how many SDs above or below the mean. Lets you compare across different scales (SAT vs ACT). Use the z table or calculator (normalcdf) for the area to the left. To go backwards: invNorm gives the z for a given percentile, then $x = \mu + z\sigma$.

## Common Z Values
- z = 1.645 -> 90% (5% in each tail)
- z = 1.96 -> 95%
- z = 2.576 -> 99%
- P(z < 0) = 0.5

## Central Limit Theorem
The sampling distribution of the sample mean $\bar{x}$ is approximately normal for large n (n >= 30 rule of thumb) REGARDLESS of the population shape. Mean of $\bar{x}$ = $\mu$, SD of $\bar{x}$ = $\frac{\sigma}{\sqrt{n}}$ (standard error). Bigger samples -> tighter distribution. This is why we can do inference on means.
