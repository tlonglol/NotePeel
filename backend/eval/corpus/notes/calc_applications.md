---
title: Related Rates and Optimization
subject: Math
topic: Calculus
tags: related rates, optimization, applications of derivatives
---
## Related Rates
Two quantities changing w/ time, related by an equation. Steps: 1. draw a picture and label. 2. write the equation relating the variables. 3. differentiate both sides w/ respect to t (implicit, chain rule). 4. plug in known values LAST. Ex: ladder sliding down a wall, $x^2 + y^2 = L^2 \Rightarrow 2x\frac{dx}{dt} + 2y\frac{dy}{dt} = 0$

## Optimization
Find max or min of some quantity. Steps: 1. write the objective function. 2. use the constraint to get it in one variable. 3. find critical points where f' = 0 or undefined. 4. check endpoints and use 2nd derivative test. classic problem: max area of rectangle w/ fixed perimeter -> its a square

## First and Second Derivative Tests
- f' > 0 increasing, f' < 0 decreasing
- f' changes + to - at a critical point -> local max, - to + -> local min
- f'' > 0 concave up (cup), f'' < 0 concave down (frown)
- f'' = 0 and changes sign -> inflection point
- 2nd derivative test: f'(c) = 0 and f''(c) > 0 -> min, f''(c) < 0 -> max

## Mean Value Theorem
if f continuous on [a,b] and differentiable on (a,b), there is some c where $f'(c) = \frac{f(b) - f(a)}{b - a}$. somewhere the instantaneous rate equals the average rate
