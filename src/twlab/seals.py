"""Registro de verificadores de sello temporal de **producción**.

Modelo de confianza (precisado en la ronda 6, R06-01): la garantía del
protocolo se enuncia para *consumidores por defecto dentro de un proceso de
confianza*, es decir, con este módulo importado sin alterar, el registro de
producción tal como está en el código versionado y
``allow_test_authorities=False`` en el validador y en la evaluación. En esas
condiciones ningún sello de autoridad de prueba se acepta y, mientras el
registro esté vacío, ningún registro puede estar sellado para el protocolo.
La garantía **no** cubre la mutación del entorno de importación
(monkeypatch, sustitución del módulo): eso queda fuera del modelo, como en
cualquier programa Python, y se mitiga con el registro como mapa de sólo
lectura y con la comprobación de integridad del árbol en cada ronda.

Estado: **vacío**. Los adaptadores OpenTimestamps (verificación de una
prueba .ots contra la cadena de Bitcoin) y RFC 3161 (verificación de un
token TSA con su certificado) aún no existen.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Callable, Mapping

PRODUCTION_AUTHORITIES = frozenset({"opentimestamps", "rfc3161"})

# authority -> verifier(record, receipt) -> bool. Sólo lectura; vacío a propósito: ver docstring.
PRODUCTION_VERIFIERS: Mapping[str, Callable] = MappingProxyType({})


def is_production_authority(authority: str) -> bool:
    return authority in PRODUCTION_AUTHORITIES


def production_verifier(authority: str):
    return PRODUCTION_VERIFIERS.get(authority)
