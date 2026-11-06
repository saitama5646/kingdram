import sys
import unittest


def main():
    suite = unittest.defaultTestLoader.discover(
        start_dir="tests",
        pattern="test_*.py",
        top_level_dir=".",
    )

    total = suite.countTestCases()

    print("\\nPruebas descubiertas:", total)

    if total == 0:
        print("ERROR: no se descubrió ninguna prueba.")
        return 2

    result = unittest.TextTestRunner(
        verbosity=2
    ).run(suite)

    print("\\nResumen:")
    print("Ejecutadas:", result.testsRun)
    print("Fallidas:", len(result.failures))
    print("Errores:", len(result.errors))
    print("Omitidas:", len(result.skipped))

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
