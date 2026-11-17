#!/usr/bin/env bash
# Start Neo4j 5.26 Community embedded with Bolt on 127.0.0.1:7687 (no auth). Ctrl-C to stop.
set -e
cd "$(dirname "$0")"
[ -d target/lib ] || mvn -q -B package dependency:copy-dependencies -DoutputDirectory=target/lib
exec java -Xmx2g -cp "target/classes:target/lib/*" lab.Server "${1:-../neo4j_data}" "${2:-7687}"
