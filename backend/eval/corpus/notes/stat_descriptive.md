---
title: Descriptive Statistics
subject: Statistics
topic: Descriptive Stats
tags: mean, median, standard deviation, outliers
---
## Measures of Center
- mean = sum / n, $\bar{x} = \frac{\sum x_i}{n}$, pulled by outliers
- median = middle value when sorted (avg of the 2 middle if even n), resistant to outliers
- mode = most frequent value, can have more than one
- skewed right (long right tail) -> mean > median. skewed left -> mean < median. symmetric -> about equal

## Measures of Spread
- range = max - min
- variance $s^2 = \frac{\sum (x_i - \bar{x})^2}{n - 1}$ for a sample (n-1 = degrees of freedom, Bessels correction). population uses N
- standard deviation = sqrt of variance, same units as the data
- IQR = Q3 - Q1, middle 50%
- outlier rule: below Q1 - 1.5 IQR or above Q3 + 1.5 IQR

## Five Number Summary and Boxplots
min, Q1, median, Q3, max. boxplot shows the box from Q1 to Q3 w/ a line at the median, whiskers to the last non outlier, dots for outliers. compare distributions side by side.

## Empirical Rule (68 95 99.7)
for roughly normal data: 68% within 1 SD of the mean, 95% within 2, 99.7% within 3
