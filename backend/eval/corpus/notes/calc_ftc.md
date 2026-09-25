---
title: Fundamental Theorem of Calculus
subject: Math
topic: Calculus
tags: FTC, definite integrals, riemann sums, area
---
## Riemann Sums
Approximate area under a curve w/ rectangles. Left, right, midpoint sums. $\int_a^b f(x) dx = \lim_{n \to \infty} \sum f(x_i) \Delta x$ where $\Delta x = \frac{b-a}{n}$. Trapezoid rule averages left and right.

## FTC Part 1
If $F(x) = \int_a^x f(t) dt$ then $F'(x) = f(x)$. Differentiating an integral w/ variable upper limit gives back the integrand. If upper limit is g(x) use chain rule: $\frac{d}{dx}\int_a^{g(x)} f(t) dt = f(g(x)) g'(x)$

## FTC Part 2
$\int_a^b f(x) dx = F(b) - F(a)$ where F is any antiderivative. This is how you actually compute definite integrals. No + C needed for definite.

## Properties of Definite Integrals
- $\int_a^a f = 0$
- $\int_a^b f = -\int_b^a f$
- $\int_a^b f = \int_a^c f + \int_c^b f$
- area below the x axis counts as negative, for total area split it up and take absolute values
- average value of f on [a,b] $= \frac{1}{b-a}\int_a^b f(x) dx$
