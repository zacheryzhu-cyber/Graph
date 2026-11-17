# RESULTS (latest ./run_all.sh, 2026-11-17)

| model | SCALE | size | load ms | Q1 impact | Q2 edge filter | Q3 provenance | Q4 path | Q5 aggregate | correct |
|---|---|---|---|---|---|---|---|---|---|
| rdf_plain | 1 | 2,595 triples | 12 | 1.7 | 0.6 | 0.3 | 0.9 | 0.3 | ✓ |
| rdf_plain | 10 | 25,096 triples | 131 | 36.4 | 4.3 | 2.9 | 0.9 | 2.1 | ✓ |
| rdf_plain | 50 | 125,340 triples | 682 | 189.0 | 25.6 | 16.3 | 1.1 | 15.4 | ✓ |
| rdf_star | 1 | 2,457 triples | 16 | 0.3 | 0.3 | 0.3 | 0.6 | 0.4 | ✓ |
| rdf_star | 10 | 23,751 triples | 129 | 0.3 | 2.6 | 3.5 | 0.6 | 3.4 | ✓ |
| rdf_star | 50 | 118,641 triples | 731 | 0.3 | 16.1 | 17.5 | 0.5 | 13.7 | ✓ |
| lpg_neo4j | 1 | 261 n / 398 r | 456 | 4.6 (srv 1) | 3.7 (srv 0) | 3.9 (srv 0) | 3.2 (srv 1) | 3.9 (srv 2) | ✓ |
| lpg_neo4j | 10 | 2,544 n / 3,888 r | 604 | 3.6 (srv 1) | 6.6 (srv 3) | 11.0 (srv 3) | 2.9 (srv 1) | 5.5 (srv 3) | ✓ |
| lpg_neo4j | 50 | 12,748 n / 19,446 r | 1753 | 6.9 (srv 4) | 23.9 (srv 7) | 45.0 (srv 12) | 3.4 (srv 0) | 17.0 (srv 10) | ✓ |

```
[1] Redundancy path explosion — 2N mesh with k layers (2^k distinct paths SRC → SINK)
     k     paths |  SPARQL feeds+ (reach) |  Cypher DISTINCT reach |    Cypher count(paths) |  Cypher shortestPath
     8       256 |           17 in 0.3 ms |             17 in 2 ms |            256 in 3 ms |            9 in 2 ms
    12      4096 |           25 in 0.2 ms |             25 in 2 ms |           4096 in 9 ms |           13 in 2 ms
    16     65536 |           33 in 0.3 ms |             33 in 2 ms |        65536 in 145 ms |           17 in 3 ms
    18    262144 |           37 in 0.3 ms |             37 in 2 ms |       262144 in 456 ms |           19 in 5 ms
    20   1048576 |           41 in 0.2 ms |             41 in 5 ms |     1048576 in 1912 ms |          21 in 12 ms
    22   4194304 |           45 in 0.2 ms |             45 in 2 ms |                skipped |           23 in 3 ms

[2] SCADA live-value writes: update 5000 datapoint values per 'tick'
   Oxigraph SPARQL UPDATE (batched)      :    261,780 values/s
   Neo4j UNWIND batch SET                 :     57,611 values/s
   Neo4j one transaction per value change :        337 values/s
   (a mid-size fab WinCC OA system: ~100k–1M tags; at 1 Hz on 10 % of them = 10k–100k changes/s)
```
