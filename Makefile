.PHONY: all neo4j env data rdf star lpg interop n10s bench scada export demo demo-build demo-test clean
all: ; ./run_all.sh
neo4j: ; ./neo4j_embedded/run.sh
env: ; python step0_env_check.py
data: ; python step1_generate_data.py
rdf: ; python step2_rdf_plain.py
star: ; python step3_rdf_star.py
lpg: ; python step4_lpg_neo4j.py
interop: ; python step5_interop.py
n10s: ; ./n10s_parser_check/run.sh && python step5b_n10s_compat.py
bench: ; python step6_bottlenecks.py
scada: ; python step7_scada_bridge.py
export: ; python export_rdf.py
clean: ; rm -rf out neo4j_data oxi_db data/facility_s*.json
demo: ; python demo/server.py
demo-build: ; python demo/build_published.py
demo-test: ; node demo/tests/ui_smoke.js
