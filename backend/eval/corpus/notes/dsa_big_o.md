---
title: Big O Notation
subject: Computer Science
topic: Algorithms
tags: big o, complexity, runtime analysis
---
## What Big O Means
Describes how runtime (or memory) grows w/ input size n. Upper bound, worst case. Drop constants and lower order terms: $3n^2 + 5n + 2 \rightarrow O(n^2)$. Big Omega = lower bound, Big Theta = tight bound.

## Common Complexities (fast -> slow)
- O(1) constant - array index, hash lookup, push/pop
- O(log n) logarithmic - binary search, balanced BST ops, halving each step
- O(n) linear - single loop, linear search
- O(n log n) - good sorts (merge, heap, quick avg)
- O(n^2) quadratic - nested loops, bubble sort, insertion sort
- O(2^n) exponential - naive recursive fibonacci, subsets
- O(n!) factorial - permutations, traveling salesman brute force

## Rules of Thumb
- sequential steps add: O(n) + O(n^2) = O(n^2)
- nested loops multiply
- recursion: count the calls x work per call, or use master theorem
- amortized: dynamic array append is O(1) amortized even though resize is O(n)
- space complexity counts extra memory, recursion uses stack space O(depth)
