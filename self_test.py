"""Run the regression suite from an IDE, regardless of its working directory."""
from pathlib import Path
import unittest

if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    suite = unittest.defaultTestLoader.discover(str(root / 'tests'), top_level_dir=str(root))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
