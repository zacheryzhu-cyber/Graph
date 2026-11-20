#!/usr/bin/env bash
# Runs the whole lab. Starts embedded Neo4j if nothing listens on :7687.
set -euo pipefail
cd "$(dirname "$0")"
pip install -q -r requirements.txt >/dev/null 2>&1 || true
rm -f out/metrics.json
if ! (exec 3<>/dev/tcp/127.0.0.1/7687) 2>/dev/null; then
  echo ">> starting Neo4j 5.26 embedded (log: neo4j.log)"
  setsid nohup ./neo4j_embedded/run.sh < /dev/null > neo4j.log 2>&1 &
  for i in $(seq 1 60); do grep -q NEO4J_READY neo4j.log 2>/dev/null && break; sleep 2; done
fi
python step0_env_check.py
for s in 1 10 50 200; do SCALE=$s python step1_generate_data.py; done
for s in 1 10 50 200; do
  echo; echo "================ SCALE=$s ================"
  SCALE=$s python step2_rdf_plain.py
  SCALE=$s python step3_rdf_star.py
  SCALE=$s python step4_lpg_neo4j.py
done
echo; python step5_interop.py
echo; ./n10s_parser_check/run.sh || echo "(n10s parser check skipped: needs Java + Maven)"
echo; python step5b_n10s_compat.py
echo; python step6_bottlenecks.py | tee out/step6_output.txt
echo; python step7_scada_bridge.py
python export_rdf.py
