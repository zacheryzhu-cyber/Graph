.PHONY: all neo4j env data rdf star lpg interop bench clean
all: ; ./run_all.sh
neo4j: ; ./neo4j_embedded/run.sh
env: ; python step0_env_check.py
data: ; python step1_generate_data.py
rdf: ; python step2_rdf_plain.py
star: ; python step3_rdf_star.py
lpg: ; python step4_lpg_neo4j.py
interop: ; python step5_interop.py
bench: ; python step6_bottlenecks.py
clean: ; rm -rf out neo4j_data data/facility_s*.json
