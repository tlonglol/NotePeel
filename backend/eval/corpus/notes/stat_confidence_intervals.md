---
title: Confidence Intervals
subject: Statistics
topic: Inference
tags: confidence interval, margin of error, sample size
---
## What a CI Is
A range of plausible values for a population parameter. estimate $\pm$ margin of error. 95% confidence means: if we repeated the sampling many times, 95% of the intervals would capture the true parameter. It does NOT mean 95% probability the parameter is in THIS interval (its either in or its not).

## Formulas
- mean (sigma known): $\bar{x} \pm z^* \frac{\sigma}{\sqrt{n}}$
- mean (sigma unknown, usual case): $\bar{x} \pm t^* \frac{s}{\sqrt{n}}$, df = n - 1
- proportion: $\hat{p} \pm z^* \sqrt{\frac{\hat{p}(1 - \hat{p})}{n}}$, need $n\hat{p} \geq 10$ and $n(1-\hat{p}) \geq 10$
- $z^*$ = 1.96 for 95%, 1.645 for 90%, 2.576 for 99%

## Margin of Error
$ME = z^* \times SE$. Gets smaller w/ bigger n (by $\sqrt{n}$, so 4x the sample halves the ME). Gets bigger w/ higher confidence level. Tradeoff: more confident = wider interval = less precise.

## Sample Size
solve $n = \left(\frac{z^* \sigma}{ME}\right)^2$, for proportions use $\hat{p} = 0.5$ if unknown (most conservative). always round UP.

## Connection to Tests
a 95% CI that does not contain the null value is the same as rejecting $H_0$ at $\alpha = 0.05$ (two sided)
