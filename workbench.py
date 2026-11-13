"""Start the local rules browser. Python 3.11+, no dependencies."""
import argparse
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"scripts"))
from codexbp.server import serve
if __name__=="__main__":
    parser=argparse.ArgumentParser(description="浏览默认规范，另建整套副本后编辑")
    parser.add_argument("--port",type=int,default=0)
    parser.add_argument("--open",action="store_true")
    args=parser.parse_args()
    serve(ROOT,args.port,args.open)
