"""Local CLI/import shim; canonical helper is deployed inside the LLM package."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'xiaozhi_adapter'))
from utility_tunnel.viewer_session import *

if __name__=='__main__':
    raise SystemExit(main())
