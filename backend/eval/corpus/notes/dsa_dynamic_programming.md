---
title: Dynamic Programming
subject: Computer Science
topic: Algorithms
tags: dynamic programming, memoization, recursion, DP
---
## When DP Applies
Two properties: 1. optimal substructure - optimal solution built from optimal solutions of subproblems. 2. overlapping subproblems - the same subproblems get solved over and over (thats what makes naive recursion exponential).

## Two Approaches
- Top down (memoization): write the recursion, cache results in a dict/array, return cached if seen. easy to write, recursion overhead
- Bottom up (tabulation): fill a table from the smallest subproblems up, iterative, no stack overflow, often can optimize space

## Fibonacci Example
naive recursive is $O(2^n)$. memoized is O(n). bottom up: dp[i] = dp[i-1] + dp[i-2], and you only need the last two so O(1) space.

## Classic Problems
- 0/1 knapsack: dp[i][w] = max value using first i items w/ capacity w
- longest common subsequence: dp[i][j], if chars match 1 + diag else max(up, left)
- coin change (min coins): dp[amount] = min(dp[amount - coin] + 1)
- climbing stairs / unique paths
- edit distance
- steps: define state, write recurrence, figure out base cases, decide order, extract answer
