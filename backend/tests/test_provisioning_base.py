"""Testes unitários dos helpers puros de `app.provisioning.base`."""
from __future__ import annotations

from app.provisioning.base import nextterm_username, slugify_username


def test_nextterm_username_matricula_without_f_prefix():
    assert nextterm_username("Rogério Silva", "0135019") == "rogerioF0135019"


def test_nextterm_username_matricula_already_with_f_prefix_is_not_doubled():
    assert nextterm_username("Rogério Silva", "F0135019") == "rogerioF0135019"


def test_nextterm_username_matricula_with_lowercase_f_prefix_is_not_doubled():
    assert nextterm_username("Rogério Silva", "f0135019") == "rogerioF0135019"


def test_slugify_username_prefixes_lab_and_truncates_matricula():
    assert slugify_username("Grace Hopper", "F0135019") == "lab-grace-135019"
