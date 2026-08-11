# ADR 005: Incremental graph component index

- Status: Accepted
- Date: 2026-08-11

## Context

Profiling showed repeated NetworkX connected-component traversals dominated feature replay.
Entity reuse caused components to grow, making the same breadth-first search recur for each
candidate node on every authorization.

## Alternatives considered

1. Keep NetworkX traversal: simplest semantics, but measured 7.981 seconds for the reference
   feature replay and scales with component size per query.
2. Cache component membership with invalidation: reads are cheap, but every component merge
   requires updating or invalidating many nodes.
3. Maintain disjoint-set roots and component aggregates: near-constant amortized union/find,
   but adds a second representation that must stay consistent.
4. External graph database: potentially appropriate at larger scale, but would introduce an
   unmeasured network/storage dependency and still require a temporal consistency design.

## Decision

Keep NetworkX as the visualization graph and add union-by-size/path-compressed disjoint-set
state for component size, observation count, and confirmed-fraud count.

## Advantages

- Same-seed feature replay measured 7.981 to 0.139 seconds (57.5× faster).
- Candidate features remain read-before-write.
- Investigator ring export is unchanged.

## Disadvantages

- NetworkX and the index can diverge if a future mutation bypasses `update`.
- Disjoint-set does not support edge deletion or component splitting.
- Both structures remain process-local and non-durable.

## Consequences

Tests compare indexed component results to NetworkX traversal. Any future edge expiry or graph
deletion requires a different dynamic-connectivity design. A distributed implementation must
define component ownership and recovery before reusing this approach.
