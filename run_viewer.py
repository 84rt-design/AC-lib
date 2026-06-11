"""Point d'entrée portable pour PyInstaller — lance A.C.Lib Viewer."""
import sys

from aclib.viewer.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
