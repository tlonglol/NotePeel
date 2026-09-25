---
title: Sorting Algorithms
subject: Computer Science
topic: Algorithms
tags: sorting, merge sort, quicksort, stability
---
## Simple O(n^2) Sorts
- Bubble: swap adjacent out of order pairs, repeat. O(n^2), O(1) space, stable
- Selection: find min, swap to front. always O(n^2) even if sorted, not stable
- Insertion: build sorted prefix, insert each element into place. O(n^2) worst but O(n) on nearly sorted data, stable, good for small arrays

## Merge Sort
Divide and conquer: split in half, sort each half recursively, merge. Always O(n log n), needs O(n) extra space for the merge. Stable. Good for linked lists and external sorting. Recurrence $T(n) = 2T(n/2) + O(n)$

## Quicksort
Pick a pivot, partition into less than and greater than, recurse. Average O(n log n), worst O(n^2) when pivot is always min/max (already sorted input w/ first element pivot). In place, O(log n) stack space. NOT stable. Usually fastest in practice b/c of cache. Randomized pivot or median of 3 avoids the worst case.

## Others
- Heap sort: build max heap, extract max n times. O(n log n), in place, not stable
- Counting / radix sort: O(n + k), not comparison based, only for integers in a known range
- comparison sorts cant beat O(n log n) - proven lower bound
- stable = equal elements keep their original order. matters when sorting by multiple keys
