#!/usr/bin/env bash
# Parse with rdf4j 4.3.12 (the parser bundled in n10s 5.26). No args: syntax demo. With a file: n10s mapping counts.
set -e; cd "$(dirname "$0")"
[ -d target/lib ] || mvn -q -B package dependency:copy-dependencies -DoutputDirectory=target/lib
exec java -Dstdout.encoding=UTF-8 -cp "target/classes:target/lib/*" lab.ParserCheck "$@" 2> >(grep -v JAVA_TOOL >&2)
