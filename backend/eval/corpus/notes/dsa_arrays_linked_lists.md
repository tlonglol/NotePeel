---
title: Arrays vs Linked Lists
subject: Computer Science
topic: Data Structures
tags: arrays, linked lists, stacks, queues
---
## Arrays
Contiguous memory, fixed size (static) or resizable (dynamic / ArrayList / vector). Index access O(1) b/c address = base + i * size. Insert/delete in the middle O(n) - have to shift elements. Cache friendly.

## Linked Lists
Nodes w/ data + pointer to next. Singly linked: next only. Doubly linked: prev and next. Access by index O(n) - must walk from head. Insert/delete at a known node O(1), no shifting. Extra memory for pointers, not cache friendly.

## When to Use Which
- lots of random access -> array
- lots of inserts/deletes at front or middle -> linked list
- unknown size and frequent growth -> linked list or dynamic array
- interview classics: reverse a linked list (3 pointers prev cur next), detect a cycle (Floyd's tortoise & hare, slow/fast pointers), find middle (fast moves 2x)

## Stacks and Queues
- Stack: LIFO, push/pop/peek O(1), used for undo, call stack, matching parentheses, DFS
- Queue: FIFO, enqueue/dequeue O(1), used for BFS, task scheduling, printers
- implement queue w/ 2 stacks, or stack w/ array
- deque: insert/remove both ends
