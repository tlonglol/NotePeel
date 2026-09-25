---
title: Limits and Continuity
subject: Math
topic: Calculus
tags: limits, continuity, squeeze theorem, asymptotes
---
## Limits
$\lim_{x \to a} f(x) = L$ means f(x) gets arbitrarily close to L as x approaches a (from both sides). The limit can exist even if f(a) is undefined. One sided limits: $\lim_{x \to a^-}$ and $\lim_{x \to a^+}$ must agree for the limit to exist.

## Evaluating Limits
- plug in first, if you get a number youre done
- $\frac{0}{0}$ is indeterminate: factor and cancel, multiply by conjugate, or use LHopital
- LHopitals rule: if $\frac{0}{0}$ or $\frac{\infty}{\infty}$, $\lim \frac{f}{g} = \lim \frac{f'}{g'}$
- squeeze theorem: if $g \leq f \leq h$ and g and h have the same limit L then f -> L too. used for $\lim_{x \to 0} \frac{\sin x}{x} = 1$
- limits at infinity: compare degrees of top and bottom for rational functions

## Continuity
f is continuous at a if: f(a) exists, the limit exists, and they are equal. Types of discontinuity: removable (hole), jump, infinite (vertical asymptote). Polynomials continuous everywhere. Intermediate Value Theorem: continuous on [a,b] means f takes every value between f(a) and f(b).
