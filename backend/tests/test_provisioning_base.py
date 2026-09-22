"""Testes unitários dos helpers puros de `app.provisioning.base`."""
from __future__ import annotations

from app.provisioning.base import nextterm_username, slugify_username


def test_slugify_username_returns_matricula_lowercase():
    assert slugify_username("Grace Hopper", "0135019") == "0135019"
    assert slugify_username("Joao Silva", "F0135019") == "f0135019"
    assert slugify_username("Maria", "F001") == "f001"


def test_nextterm_username_returns_matricula_lowercase():
    assert nextterm_username("Rogério Silva", "0135019") == "0135019"
    assert nextterm_username("Ana", "F001") == "f001"
    assert nextterm_username("Teste Final", "F0LIVECHK05") == "f0livechk05"
