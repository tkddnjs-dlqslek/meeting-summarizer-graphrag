import sys, traceback
sys.path.insert(0, '.')

print("Testing imports...")

try:
    from graph.neo4j_client import verify_connectivity, init_constraints
    print("[OK] neo4j_client")
except Exception as e:
    print(f"[ERR] neo4j_client: {e}")
    traceback.print_exc()

try:
    from api.extractor import extract_graph_data
    print("[OK] extractor")
except Exception as e:
    print(f"[ERR] extractor: {e}")

try:
    from api.graph_builder import build_graph
    print("[OK] graph_builder")
except Exception as e:
    print(f"[ERR] graph_builder: {e}")

try:
    from api.agents import run_expert_panel
    print("[OK] agents")
except Exception as e:
    print(f"[ERR] agents: {e}")
    traceback.print_exc()

try:
    from api.obsidian_writer import write_meeting_note
    print("[OK] obsidian_writer")
except Exception as e:
    print(f"[ERR] obsidian_writer: {e}")

try:
    from api.stt import job_store
    print("[OK] stt")
except Exception as e:
    print(f"[ERR] stt: {e}")

try:
    from api.main import app
    print("[OK] main")
except Exception as e:
    print(f"[ERR] main: {e}")
    traceback.print_exc()

print("Done.")
