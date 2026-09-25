---
title: Graph Traversal BFS and DFS
subject: Computer Science
topic: Algorithms
tags: graphs, BFS, DFS, traversal, shortest path
---
## Graph Representation
- adjacency list: dict of node -> list of neighbors, O(V + E) space, best for sparse graphs
- adjacency matrix: V x V grid, O(V^2) space, O(1) edge lookup, good for dense
- directed vs undirected, weighted vs unweighted

## Breadth First Search
Uses a QUEUE. Visit all neighbors at distance 1, then distance 2, etc (level by level). Mark visited when you enqueue, not when you dequeue. Finds the SHORTEST path in an unweighted graph. O(V + E). Applications: shortest path, level order traversal of a tree, web crawler, social network degrees of separation.

## Depth First Search
Uses a STACK (or recursion). Go as deep as possible then backtrack. O(V + E). Applications: cycle detection, topological sort, connected components, maze solving, path existence. Does NOT find shortest path in general. Recursion depth can overflow on big graphs -> use explicit stack.

## Comparison
- BFS: queue, shortest path, more memory (whole frontier)
- DFS: stack, less memory, good for exhaustive search
- both need a visited set to avoid infinite loops on cycles
- Dijkstra = BFS w/ a priority queue for weighted graphs (no negative edges)
