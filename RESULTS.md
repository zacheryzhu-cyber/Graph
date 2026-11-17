# RESULTS (latest ./run_all.sh, 2026-11-17)

Cells: p50/p95 ms over 15 runs after 1 warm-up. Neo4j cells are client-side incl. Bolt; srv = server-reported.
Q1b = traversal-first rewrite of Q1 (RDF only). Q6 prep = one-off materialisation of fab:feedsPower that RDF needs for Q6.

| model | SCALE | size | load ms | Q1 | Q1b | Q2 | Q3 | Q4 | Q5 | Q6 | Q6 prep | correct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rdf_plain | 1 | 2,595 triples | 17 | 1.7/1.8 | 0.2/0.2 | 0.5/0.5 | 0.3/0.3 | 0.8/0.8 | 0.2/0.3 | 0.2/0.3 | 0 | ✓ |
| rdf_plain | 10 | 25,096 triples | 121 | 40.3/46.4 | 0.4/0.5 | 4.6/5.3 | 2.7/3.0 | 1.4/1.6 | 2.2/3.2 | 2.6/3.0 | 4 | ✓ |
| rdf_plain | 50 | 125,340 triples | 750 | 195.2/237.1 | 1.5/1.6 | 22.3/23.2 | 16.4/21.7 | 1.0/1.1 | 17.1/18.6 | 14.6/22.4 | 29 | ✓ |
| rdf_plain | 200 | 501,894 triples | 2571 | 802.2/867.9 | 7.3/9.1 | 105.4/107.2 | 87.6/94.5 | 1.4/1.5 | 65.1/68.5 | 98.1/163.6 | 114 | ✓ |
| rdf_star | 1 | 2,457 triples | 16 | 0.3/0.3 | 0.3/0.3 | 0.4/0.4 | 0.3/0.4 | 0.5/0.5 | 0.3/0.3 | 0.3/0.4 | 0 | ✓ |
| rdf_star | 10 | 23,751 triples | 130 | 0.2/0.3 | 0.3/0.3 | 2.8/3.2 | 2.6/2.8 | 0.4/0.5 | 2.4/3.0 | 2.8/2.9 | 4 | ✓ |
| rdf_star | 50 | 118,641 triples | 823 | 0.3/0.3 | 0.3/0.4 | 18.0/19.7 | 15.7/18.0 | 0.5/0.5 | 13.6/14.5 | 17.2/18.5 | 27 | ✓ |
| rdf_star | 200 | 475,089 triples | 3794 | 0.3/0.3 | 0.3/0.3 | 99.8/102.7 | 76.3/91.1 | 0.5/0.5 | 69.0/80.7 | 140.2/175.6 | 118 | ✓ |
| lpg_neo4j | 1 | 261 n / 398 r | 419 | 3.1/6.9 (srv 0) | — | 3.5/7.5 (srv 1) | 4.2/7.3 (srv 1) | 3.5/4.8 (srv 1) | 3.3/7.6 (srv 1) | 3.7/5.1 (srv 1) | not needed | ✓ |
| lpg_neo4j | 10 | 2,544 n / 3,888 r | 643 | 3.3/3.6 (srv 1) | — | 7.3/8.7 (srv 2) | 12.9/13.9 (srv 2) | 2.9/3.1 (srv 1) | 5.8/8.6 (srv 2) | 9.2/11.2 (srv 1) | not needed | ✓ |
| lpg_neo4j | 50 | 12,748 n / 19,446 r | 1721 | 4.1/6.4 (srv 1) | — | 26.2/32.2 (srv 10) | 43.7/51.6 (srv 7) | 2.9/3.5 (srv 0) | 14.8/16.0 (srv 10) | 44.0/51.9 (srv 6) | not needed | ✓ |
| lpg_neo4j | 200 | 51,072 n / 77,876 r | 6091 | 3.7/5.4 (srv 1) | — | 102.5/129.0 (srv 57) | 201.7/232.7 (srv 29) | 2.9/3.3 (srv 2) | 45.5/57.4 (srv 24) | 134.7/165.6 (srv 26) | not needed | ✓ |

```
[1] Redundancy path explosion — 2N mesh with k layers (2^k distinct paths SRC → SINK)
     k     paths |  SPARQL feeds+ (reach) |  Cypher DISTINCT reach |    Cypher count(paths) |  Cypher shortestPath
     8       256 |           17 in 0.4 ms |            17 in 46 ms |           256 in 90 ms |           9 in 47 ms
    12      4096 |           25 in 0.3 ms |             25 in 3 ms |          4096 in 55 ms |          13 in 12 ms
    16     65536 |           33 in 0.2 ms |             33 in 2 ms |        65536 in 270 ms |           17 in 3 ms
    18    262144 |           37 in 0.2 ms |             37 in 2 ms |       262144 in 718 ms |           19 in 5 ms
    20   1048576 |           41 in 0.2 ms |             41 in 2 ms |     1048576 in 2676 ms |           21 in 6 ms
    22   4194304 |           45 in 0.2 ms |             45 in 3 ms |                skipped |           23 in 3 ms

[2] SCADA live-value writes: update 5000 datapoint values per 'tick'
   Oxigraph SPARQL UPDATE (batched, in-memory) :    215,386 values/s
   Oxigraph SPARQL UPDATE (batched, on-disk)   :     91,071 values/s
   Oxigraph one UPDATE per value (on-disk)     :     13,071 values/s
   Neo4j UNWIND batch SET                      :     45,773 values/s
   Neo4j one transaction per value change      :        326 values/s
   (a mid-size fab WinCC OA system: ~100k–1M tags; at 1 Hz on 10 % of them = 10k–100k changes/s)

[4] Relationship-property index (Neo4j 5) on FEEDS.source — Q3 at SCALE=200
   no index  : client p50  168.5 ms | server p50  35 ms | plan leaf: DirectedRelationshipTypeScan
   with index: client p50  149.5 ms | server p50  20 ms | plan leaf: DirectedRelationshipIndexSeek
```

```
n10s 5.26 parser (rdf4j 4.3.12) — ./n10s_parser_check/run.sh
== RDF-star 2021 (Turtle-star)
   <<http://example.org/fab#UPS-1 http://example.org/fab#feeds http://example.org/fab#PDU-1>> installed "2012"^^<http://www.w3.org/2001/XMLSchema#integer>   → n10s: RELATIONSHIP PROPERTY
   <<http://example.org/fab#UPS-1 http://example.org/fab#feeds http://example.org/fab#PDU-1>> sourceSystem "BIM"   → n10s: RELATIONSHIP PROPERTY
== RDF 1.2 triple term + reifier
   PARSE FAILED: Expected an RDF value here, found '(' [line 2]
== RDF 1.2 annotation syntax
   PARSE FAILED: Expected '.', found '~' [line 2]
```
