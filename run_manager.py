"""Point d'entrée portable pour PyInstaller — lance A.C.Lib Manager."""
import sys

from aclib.manager.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
