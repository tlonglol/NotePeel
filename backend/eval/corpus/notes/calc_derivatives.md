---
title: Derivatives & The Chain Rule
subject: Math
topic: Calculus
tags: derivatives, chain rule, product rule
---
## Derivatives
The derivative measures the instantaneous rate of change of a function (the slope of the tangent line). Limit definition: $$f'(x) = \lim_{h \to 0} \frac{f(x+h) - f(x)}{h}$$

## Common Rules
- Power rule: $\frac{d}{dx} x^n = n x^{n-1}$
- Constant multiple: $(cf)' = cf'$
- Sum rule: $(f + g)' = f' + g'$
- Product rule: $(fg)' = f'g + fg'$
- Quotient rule: $\left(\frac{f}{g}\right)' = \frac{f'g - fg'}{g^2}$ (low d high minus high d low over low squared)
- Chain rule: $\frac{d}{dx} f(g(x)) = f'(g(x)) \cdot g'(x)$, derivative of outside times derivative of inside

## Special Derivatives
- $\frac{d}{dx} e^x = e^x$, $\frac{d}{dx} \ln x = \frac{1}{x}$
- $\frac{d}{dx} \sin x = \cos x$, $\frac{d}{dx} \cos x = -\sin x$, $\frac{d}{dx} \tan x = \sec^2 x$
- $\frac{d}{dx} a^x = a^x \ln a$

## Implicit Differentiation
when y isnt isolated, differentiate both sides treating y as a function of x, every y term gets a $\frac{dy}{dx}$ from the chain rule. ex $x^2 + y^2 = 25 \Rightarrow 2x + 2y y' = 0 \Rightarrow y' = -\frac{x}{y}$
