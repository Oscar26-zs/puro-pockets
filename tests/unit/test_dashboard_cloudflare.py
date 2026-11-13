"""Dashboard publicado por Cloudflare con Cloudflare Access (Hito 10; decisión del 2026-11-12).

Los tokens se firman aquí con claves RSA de prueba, como los de Cloudflare Access. Se comprueba que
todo lo que llega por el túnel exige un token válido, que el acceso local sigue igual, que sin modo
público cualquier petición de Cloudflare se rechaza, y que el límite de intentos usa la IP real.
"""

import secrets
import time
from functools import partial

import anyio
import jwt
import pytest
from argon2 import PasswordHasher
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

from puro_pockets.api.access import AccessVerifier
from puro_pockets.api.app import build_app
from puro_pockets.api.config import load_dashboard_settings
from puro_pockets.api.session import SessionManager
from puro_pockets.config import ConfigError
from puro_pockets.domain.auth import LoginRateLimiter
from puro_pockets.domain.money import RateRange
from puro_pockets.services.dashboard import DashboardService
from puro_pockets.services.ledger import LedgerService
from puro_pockets.services.passwords import PasswordVerifier
from tests.dashboard_world import TODAY, build_world
from tests.fakes import InMemoryLedgerStore

HOST = "dash.puropockets.space"
PUBLIC = f"https://{HOST}"
LOCAL = "https://127.0.0.1:8080"
TEAM = "puropockets.cloudflareaccess.com"
AUD = "a" * 64
PASSWORD = secrets.token_urlsafe(16)
PASSWORD_HASH = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token(key=KEY, aud=AUD, iss=f"https://{TEAM}", exp_in=600, **extra) -> str:
    now = int(time.time())
    claims = {"aud": [aud], "iss": iss, "iat": now, "exp": now + exp_in, "email": "x@y.z", **extra}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


@pytest.fixture(scope="module")
def ledger_and_store():
    store = InMemoryLedgerStore()
    ledger = LedgerService(store, today=lambda: TODAY, rate_range=RateRange(300, 1000))
    anyio.run(partial(build_world, store, ledger))
    return ledger, store


def make_app(ledger_and_store, *, public=True, per_key=5, provider=None):
    ledger, store = ledger_and_store
    access = (
        AccessVerifier(TEAM, AUD, key_provider=provider or (lambda _t: KEY.public_key()))
        if public
        else None
    )
    return build_app(
        DashboardService(ledger, store, lambda: TODAY),
        SessionManager(secrets.token_bytes(48), 12 * 3600),
        PasswordVerifier(PASSWORD_HASH),
        LoginRateLimiter(per_key_max=per_key, window_seconds=900, global_max=50),
        public_hostname=HOST if public else None,
        access=access,
    )


@pytest.fixture
def public(ledger_and_store):
    with TestClient(make_app(ledger_and_store), base_url=PUBLIC) as client:
        yield client


def _jwt_headers(value=None):
    return {"Cf-Access-Jwt-Assertion": value or token(), "CF-Connecting-IP": "203.0.113.7"}


# --- Por Cloudflare: sin token válido no se pasa ---


@pytest.mark.parametrize("path", ["/", "/healthz", "/api/summary", "/api/session", "/assets/x.js"])
def test_sin_token_de_access_403_en_todo(public, path):
    response = public.get(path)
    assert response.status_code == 403
    assert response.json() == {"detail": "Acceso no autorizado."}


def test_login_sin_token_403_aunque_la_contraseña_sea_correcta(public):
    response = public.post("/api/session/login", json={"password": PASSWORD})
    assert response.status_code == 403
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize(
    "bad",
    [
        token(exp_in=-10),  # vencido
        token(aud="otra-aplicacion"),  # otra aplicación de Access
        token(iss="https://otro.cloudflareaccess.com"),  # otro equipo
        token(key=OTHER_KEY),  # firmado con otra clave
        "no-es-un-jwt",
        jwt.encode({"aud": [AUD], "iss": f"https://{TEAM}"}, "s" * 32, algorithm="HS256"),
    ],
)
def test_token_invalido_403(public, bad):
    assert public.get("/api/session", headers=_jwt_headers(bad)).status_code == 403


def test_token_sin_vencimiento_403(public):
    claims = {"aud": [AUD], "iss": f"https://{TEAM}", "iat": int(time.time())}
    unsigned_exp = jwt.encode(claims, KEY, algorithm="RS256")
    assert public.get("/api/session", headers=_jwt_headers(unsigned_exp)).status_code == 403


def test_si_no_hay_claves_se_rechaza(ledger_and_store):
    def unreachable(_token):
        raise OSError("sin red")

    app = make_app(ledger_and_store, provider=unreachable)
    with TestClient(app, base_url=PUBLIC) as client:
        assert client.get("/healthz", headers=_jwt_headers()).status_code == 403


def test_con_token_valido_sigue_pidiendo_la_contraseña_y_entra(public):
    headers = _jwt_headers()
    assert public.get("/api/summary", headers=headers).status_code == 401  # Access no basta
    login = public.post(
        "/api/session/login", json={"password": PASSWORD}, headers={**headers, "Origin": PUBLIC}
    )
    assert login.status_code == 204  # el origen https del nombre público se acepta
    assert "secure" in login.headers["set-cookie"].lower()
    summary = public.get("/api/summary", headers=headers)
    assert summary.status_code == 200 and summary.json()["income"] == 500_000
    assert summary.headers["strict-transport-security"] == "max-age=31536000"


def test_token_tambien_en_la_cookie_de_access(public):
    public.cookies.set("CF_Authorization", token())
    assert public.get("/healthz").status_code == 200


def test_otro_origen_sigue_rechazado(public):
    response = public.post(
        "/api/session/login",
        json={"password": PASSWORD},
        headers={**_jwt_headers(), "Origin": "https://mcp.puropockets.space"},
    )
    assert response.status_code == 403


def test_limite_de_intentos_por_ip_real_del_cliente(public):
    for _ in range(5):
        headers = {**_jwt_headers(), "CF-Connecting-IP": "198.51.100.1"}
        assert (
            public.post(
                "/api/session/login", json={"password": "mala"}, headers=headers
            ).status_code
            == 401
        )
    blocked = {**_jwt_headers(), "CF-Connecting-IP": "198.51.100.1"}
    assert (
        public.post("/api/session/login", json={"password": PASSWORD}, headers=blocked).status_code
        == 429
    )
    other = {**_jwt_headers(), "CF-Connecting-IP": "198.51.100.2"}
    assert (
        public.post("/api/session/login", json={"password": PASSWORD}, headers=other).status_code
        == 204
    )


# --- Acceso local (túnel SSH) sin cambios ---


def test_acceso_local_no_necesita_access(ledger_and_store):
    with TestClient(make_app(ledger_and_store), base_url=LOCAL) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/api/summary").status_code == 401
        assert client.post("/api/session/login", json={"password": PASSWORD}).status_code == 204
        assert client.get("/api/summary").status_code == 200
        assert "strict-transport-security" not in client.get("/healthz").headers


def test_cabecera_de_cloudflare_en_otro_nombre_tambien_exige_access(ledger_and_store):
    with TestClient(make_app(ledger_and_store), base_url=LOCAL) as client:
        assert client.get("/healthz", headers={"CF-Ray": "abc"}).status_code == 403
        assert (
            client.get("/healthz", headers={"CF-Ray": "abc", **_jwt_headers()}).status_code == 200
        )


# --- Sin modo público: Cloudflare nunca llega ---


@pytest.mark.parametrize(
    "headers",
    [{"CF-Ray": "abc"}, {"CF-Connecting-IP": "203.0.113.7"}, {"Cf-Access-Jwt-Assertion": "x"}],
)
def test_sin_modo_publico_cualquier_peticion_de_cloudflare_403(ledger_and_store, headers):
    with TestClient(make_app(ledger_and_store, public=False), base_url=LOCAL) as client:
        assert client.get("/healthz", headers=headers).status_code == 403
        assert client.get("/healthz").status_code == 200  # lo local sigue igual


def test_nombre_y_access_van_juntos(ledger_and_store):
    ledger, store = ledger_and_store
    with pytest.raises(ValueError):
        build_app(
            DashboardService(ledger, store, lambda: TODAY),
            SessionManager(secrets.token_bytes(48), 60),
            PasswordVerifier(PASSWORD_HASH),
            LoginRateLimiter(),
            public_hostname=HOST,
        )


# --- Configuración ---

BASE_ENV = {
    "DASHBOARD_DATABASE_URL": "postgresql+psycopg://puro_dashboard:x@db:5432/puro_pockets",
    "DASHBOARD_SESSION_SECRET": "s" * 32,
    "OWNER_PASSWORD_HASH": PASSWORD_HASH,
}


def test_configuracion_publica_completa():
    settings = load_dashboard_settings(
        {
            **BASE_ENV,
            "DASHBOARD_PUBLIC_HOSTNAME": "Dash.PuroPockets.space",
            "CF_ACCESS_TEAM_DOMAIN": TEAM,
            "CF_ACCESS_AUD": AUD,
        }
    )
    assert settings.public_hostname == HOST
    assert (settings.access_team_domain, settings.access_audience) == (TEAM, AUD)


def test_sin_nombre_publico_no_hay_modo_publico():
    assert load_dashboard_settings(BASE_ENV).public_hostname is None


@pytest.mark.parametrize(
    "extra",
    [
        {"DASHBOARD_PUBLIC_HOSTNAME": HOST},  # sin Access
        {"DASHBOARD_PUBLIC_HOSTNAME": HOST, "CF_ACCESS_TEAM_DOMAIN": TEAM},  # sin AUD
        {"DASHBOARD_PUBLIC_HOSTNAME": HOST, "CF_ACCESS_AUD": AUD},  # sin equipo
        {
            "DASHBOARD_PUBLIC_HOSTNAME": HOST,
            "CF_ACCESS_TEAM_DOMAIN": f"https://{TEAM}",
            "CF_ACCESS_AUD": AUD,
        },
        {
            "DASHBOARD_PUBLIC_HOSTNAME": HOST,
            "CF_ACCESS_TEAM_DOMAIN": "puropockets.example.com",
            "CF_ACCESS_AUD": AUD,
        },
        {
            "DASHBOARD_PUBLIC_HOSTNAME": "https://dash.puropockets.space",
            "CF_ACCESS_TEAM_DOMAIN": TEAM,
            "CF_ACCESS_AUD": AUD,
        },
    ],
)
def test_configuracion_publica_incompleta_o_invalida(extra):
    with pytest.raises(ConfigError):
        load_dashboard_settings({**BASE_ENV, **extra})
