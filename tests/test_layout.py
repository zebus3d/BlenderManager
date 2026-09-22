"""Que ningún módulo se vuelva a convertir en un fichero inabarcable.

``main_window.py`` llegó a 3314 líneas y ``migrate.py`` a 2492: a partir de ahí
nadie lee el fichero entero, y lo que no se lee es donde se esconde el código
repetido. El tope es blando (se puede subir con un motivo), pero tiene que ser
una decisión, no un descuido.
"""

import unittest
from pathlib import Path

# Un módulo de más de mil líneas ya no se lee de una sentada. Los que están
# cerca se parten por responsabilidad, no por número de líneas.
MAX_LINES = 1000

# Excepciones, con su porqué. Vacío: si hace falta añadir una, que se vea en
# la revisión.
ALLOWED = {}


class ModuleSizeTest(unittest.TestCase):
    def test_ningun_modulo_pasa_de_mil_lineas(self):
        root = Path(__file__).resolve().parents[1] / "src"
        grandes = []
        for path in sorted(root.rglob("*.py")):
            lines = len(path.read_text(encoding="utf-8").splitlines())
            name = str(path.relative_to(root))
            if lines > ALLOWED.get(name, MAX_LINES):
                grandes.append(f"{name}: {lines}")
        self.assertEqual(grandes, [], "módulos que hay que partir")


if __name__ == "__main__":
    unittest.main()
