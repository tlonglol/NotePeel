---
title: Hash Tables
subject: Computer Science
topic: Data Structures
tags: hash table, hashing, collisions, dictionary
---
## Hash Table Basics
Key -> hash function -> index into an array of buckets. Average O(1) insert, lookup, delete. Worst case O(n) if everything collides. Python dict and set, Java HashMap, JS objects/Map.

## Hash Functions
Should be deterministic, fast, uniform (spread keys evenly). ex for strings: polynomial rolling hash, sum of chars x prime^i mod table size. Keys must be immutable / hashable (cant use a list as a dict key in python).

## Collision Handling
- Chaining: each bucket is a linked list, collisions just append. simple, table can exceed 100% load
- Open addressing: find another slot in the same array. linear probing (next slot), quadratic probing, double hashing. deletion is tricky - need tombstones
- load factor $\alpha = \frac{n}{table size}$, resize (rehash) when it gets too high, usually around 0.7

## Uses
- counting frequencies, two sum in O(n), memoization cache, deduplication w/ a set, LRU cache = hash map + doubly linked list
- not ordered! (python 3.7+ dicts keep insertion order but dont rely on it for sorting)
