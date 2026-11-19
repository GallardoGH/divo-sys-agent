"""divo-sys command line. Run `python divo.py` for the list of commands (the code lives in divosys/cli.py)."""
import sys

from divosys.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
