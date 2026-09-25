---
title: Integration Techniques
subject: Math
topic: Calculus
tags: integrals, u-substitution, integration by parts
---
## Antiderivatives
Integration reverses differentiation. $\int x^n dx = \frac{x^{n+1}}{n+1} + C$ for $n \neq -1$, $\int \frac{1}{x} dx = \ln|x| + C$, $\int e^x dx = e^x + C$. Dont forget + C on indefinite integrals!!

## u-Substitution
Reverse of the chain rule. Pick u = inside function, du = u' dx, rewrite everything in u. ex $\int 2x \cos(x^2) dx$, let $u = x^2$, $du = 2x dx$ -> $\int \cos u \, du = \sin(x^2) + C$. Change the limits too if definite.

## Integration by Parts
Reverse of the product rule. $\int u \, dv = uv - \int v \, du$. Choose u by LIATE (Log, Inverse trig, Algebraic, Trig, Exponential) - pick u as whatever comes first. ex $\int x e^x dx$: u = x, dv = e^x dx -> $xe^x - e^x + C$

## Other Techniques
- partial fractions for rational functions, factor the denominator
- trig substitution for $\sqrt{a^2 - x^2}$ use $x = a\sin\theta$
- tabular method for repeated by parts (like $\int x^3 e^x dx$)
