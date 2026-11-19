"""`python -m divosys <command>`: the same command line as `divo.py` and `divo-sys.exe`."""
import sys

from .cli import main

sys.exit(main(sys.argv[1:]))
