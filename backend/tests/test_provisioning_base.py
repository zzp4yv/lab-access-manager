"""Testes unitários dos helpers puros de `app.provisioning.base`."""
from __future__ import annotations

from app.provisioning.base import nextterm_username, slugify_username


def test_slugify_username_returns_matricula():
    assert slugify_username("Grace Hopper", "0135019") == "0135019"
    assert slugify_username("Joao Silva", "F0135019") == "F0135019"


def test_nextterm_username_returns_matricula():
    assert nextterm_username("Rogério Silva", "0135019") == "0135019"
    assert nextterm_username("Ana", "F001") == "F001"
    assert nextterm_username("Teste Final", "F0LIVECHK05") == "F0LIVECHK05"
