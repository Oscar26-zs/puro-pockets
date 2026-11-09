"""Genera el hash argon2 de la contraseña del propietario para OWNER_PASSWORD_HASH.

La contraseña se pide con getpass (no se ve al escribir) y NUNCA se guarda ni se imprime: solo se
imprime el hash. Los parámetros de argon2 quedan dentro del hash.

Uso:
    python scripts/hash_password.py                    # pide la contraseña e imprime el hash
    python scripts/hash_password.py --benchmark        # mide cuánto tarda una verificación
    python scripts/hash_password.py --memory-kib 32768 --time-cost 2 --benchmark

En el homelab (sin uv): docker compose exec mcp python scripts/hash_password.py --benchmark
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import statistics
import sys
import time

from argon2 import PasswordHasher

MIN_LENGTH = 12


def _hasher(args: argparse.Namespace) -> PasswordHasher:
    return PasswordHasher(
        memory_cost=args.memory_kib, time_cost=args.time_cost, parallelism=args.parallelism
    )


def benchmark(args: argparse.Namespace, rounds: int = 5) -> int:
    hasher = _hasher(args)
    sample = secrets.token_urlsafe(16)  # valor aleatorio de prueba, no es tu contraseña
    encoded = hasher.hash(sample)
    timings = []
    for _ in range(rounds):
        start = time.perf_counter()
        hasher.verify(encoded, sample)
        timings.append(time.perf_counter() - start)
    median = statistics.median(timings)
    print(
        f"argon2id m={args.memory_kib} KiB, t={args.time_cost}, p={args.parallelism}: "
        f"verificación mediana {median:.3f} s (en {rounds} rondas)"
    )
    if median >= 1:
        print("Más de 1 s: baja --time-cost o --memory-kib.", file=sys.stderr)
    return 0


def generate(args: argparse.Namespace) -> int:
    password = getpass.getpass("Contraseña del propietario: ")
    if len(password) < MIN_LENGTH:
        print(f"Usa al menos {MIN_LENGTH} caracteres.", file=sys.stderr)
        return 1
    if getpass.getpass("Repítela: ") != password:
        print("No coinciden.", file=sys.stderr)
        return 1
    encoded = _hasher(args).hash(password)
    del password
    print(
        "Copia esta línea en el .env del homelab (entre comillas simples, por los '$'):",
        file=sys.stderr,
    )
    print(f"OWNER_PASSWORD_HASH='{encoded}'")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Hash argon2 de la contraseña del propietario.")
    parser.add_argument("--memory-kib", type=int, default=65536, help="memoria en KiB (64 MiB)")
    parser.add_argument("--time-cost", type=int, default=3, help="iteraciones")
    parser.add_argument("--parallelism", type=int, default=4, help="hilos")
    parser.add_argument("--benchmark", action="store_true", help="solo medir, sin pedir contraseña")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    return benchmark(args) if args.benchmark else generate(args)


if __name__ == "__main__":
    sys.exit(main())
