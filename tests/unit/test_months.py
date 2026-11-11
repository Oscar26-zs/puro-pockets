"""Mes presupuestario 'YYYY-MM' (Hito 4)."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from puro_pockets.domain.errors import DomainError
from puro_pockets.domain.months import Month


@pytest.mark.parametrize("text", ["2026-11", " 2026-01 ", "1999-12"])
def test_formato_valido(text):
    assert str(Month.parse(text)) == text.strip()


@pytest.mark.parametrize(
    "text", ["2026-13", "26-01", "2026-1", "2026/11", "0000-05", "", None, 202611]
)
def test_formato_invalido_mensaje_claro(text):
    with pytest.raises(DomainError, match="AAAA-MM"):
        Month.parse(text)


def test_anterior_siguiente_y_orden():
    assert Month(2026, 1).previous() == Month(2025, 12)
    assert Month(2026, 12).next() == Month(2027, 1)
    assert Month(2026, 11) < Month(2026, 12) < Month(2027, 1)
    assert max([Month(2026, 3), Month(2025, 12)]) == Month(2026, 3)


def test_mes_actual_en_costa_rica_cerca_de_medianoche_utc():
    # 2026-12-01 03:00 UTC es todavía 30 de noviembre en Costa Rica (UTC-6)
    instant = datetime(2026, 12, 1, 3, 0, tzinfo=UTC)
    local = instant.astimezone(ZoneInfo("America/Costa_Rica")).date()
    assert Month.of(local) == Month(2026, 11)
    assert Month.of(date(2026, 12, 1)) == Month(2026, 12)
