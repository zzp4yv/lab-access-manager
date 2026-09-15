#!/usr/bin/env python3
"""
Agente de validação de código (gate determinístico).

Executa, contra o diretório `backend/` do projeto:
  1. Lint estático com ruff.
  2. Suíte de testes automatizados (pytest) com cobertura de código.
  3. Análise de complexidade ciclomática média com radon.

E combina os resultados em uma nota única de 1 a 10. Conforme a
política definida para este projeto, apenas versões com nota
SUPERIOR A 9 são consideradas aptas para produção — o script sai com
código de saída 0 quando a nota final > --min-score (padrão 9.0) e
código de saída 1 caso contrário, para ser usado como "gate"
bloqueante em CI/CD (ver .github/workflows/ci.yml e cd.yml).

Uso:
    python validation_agent/validate.py \
        [--backend-dir PATH] [--min-score 9.0] [--json-out FILE]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKEND_DIR = REPO_ROOT / "backend"


@dataclass
class CheckResult:
    name: str
    score: float  # 0-10
    weight: float
    details: dict = field(default_factory=dict)
    passed_hard_gate: bool = True
    error: str | None = None


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)  # noqa: S603


def check_lint(backend_dir: Path) -> CheckResult:
    proc = run(["ruff", "check", "app", "--output-format=json"], backend_dir)
    try:
        issues = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return CheckResult("lint", 0.0, weight=0.20, error=(proc.stderr or proc.stdout)[-1000:])

    n = len(issues)
    # 0 problemas => nota 10; cada problema custa 1.5 ponto, piso em 0.
    score = max(0.0, round(10.0 - n * 1.5, 2))
    return CheckResult("lint", score, weight=0.20, details={"issues": n})


def check_tests_and_coverage(backend_dir: Path) -> tuple[CheckResult, CheckResult]:
    junit_path = backend_dir / "validation_report_junit.xml"
    cov_json_path = backend_dir / "validation_report_coverage.json"

    proc = run(
        [
            "pytest",
            "-q",
            f"--junitxml={junit_path.name}",
            "--cov=app",
            f"--cov-report=json:{cov_json_path.name}",
        ],
        backend_dir,
    )

    tests_result = CheckResult("tests", 0.0, weight=0.35, passed_hard_gate=False)
    if junit_path.exists():
        root = ET.parse(junit_path).getroot()
        suite = root if root.tag == "testsuite" else root.find("testsuite")
        total = int(suite.get("tests", 0))
        failures = int(suite.get("failures", 0))
        errors = int(suite.get("errors", 0))
        passed = total - failures - errors
        pass_rate = (passed / total) if total else 0.0
        tests_result.score = round(pass_rate * 10, 2)
        tests_result.details = {
            "total": total,
            "passed": passed,
            "failures": failures,
            "errors": errors,
        }
        tests_result.passed_hard_gate = total > 0 and failures == 0 and errors == 0
    else:
        tests_result.error = (proc.stdout[-1500:] + proc.stderr[-1500:]).strip()

    cov_result = CheckResult("coverage", 0.0, weight=0.30)
    if cov_json_path.exists():
        data = json.loads(cov_json_path.read_text())
        percent = data.get("totals", {}).get("percent_covered", 0.0)
        cov_result.score = round(percent / 10, 2)
        cov_result.details = {"percent_covered": round(percent, 2)}
    else:
        cov_result.error = "coverage.json não foi gerado (a suíte de testes pode ter falhado ao iniciar)"

    return tests_result, cov_result


def check_complexity(backend_dir: Path) -> CheckResult:
    proc = run(["radon", "cc", "app", "-a", "-j"], backend_dir)
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return CheckResult("complexity", 5.0, weight=0.15, error=(proc.stderr or "")[-1000:])

    complexities = [block["complexity"] for blocks in data.values() for block in blocks]
    if not complexities:
        return CheckResult("complexity", 10.0, weight=0.15, details={"average": 0, "blocks": 0})

    avg = sum(complexities) / len(complexities)
    # Complexidade média <=5 => nota 10; degrada linearmente até 0 em média >=20.
    score = max(0.0, min(10.0, 10.0 - max(0.0, avg - 5) * (10 / 15)))
    return CheckResult(
        "complexity",
        round(score, 2),
        weight=0.15,
        details={"average": round(avg, 2), "blocks": len(complexities)},
    )


def compute_final_score(checks: list[CheckResult]) -> float:
    total_weight = sum(c.weight for c in checks)
    if not total_weight:
        return 0.0
    weighted = sum(c.score * c.weight for c in checks)
    return round(weighted / total_weight, 2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backend-dir", default=str(DEFAULT_BACKEND_DIR))
    parser.add_argument("--min-score", type=float, default=9.0)
    parser.add_argument("--json-out", default=str(REPO_ROOT / "validation_report.json"))
    args = parser.parse_args()

    backend_dir = Path(args.backend_dir).resolve()

    lint = check_lint(backend_dir)
    tests, coverage = check_tests_and_coverage(backend_dir)
    complexity = check_complexity(backend_dir)
    checks = [lint, tests, coverage, complexity]

    final_score = compute_final_score(checks)
    hard_gate_ok = all(c.passed_hard_gate for c in checks)
    approved = hard_gate_ok and final_score > args.min_score

    report = {
        "final_score": final_score,
        "min_score_required": args.min_score,
        "approved_for_production": approved,
        "checks": [
            {
                "name": c.name,
                "score": c.score,
                "weight": c.weight,
                "details": c.details,
                "passed_hard_gate": c.passed_hard_gate,
                "error": c.error,
            }
            for c in checks
        ],
    }

    Path(args.json_out).write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print("=" * 64)
    print("AGENTE DE VALIDAÇÃO DE CÓDIGO — Relatório")
    print("=" * 64)
    for c in checks:
        status_icon = "OK   " if c.passed_hard_gate else "FALHA"
        print(f"[{status_icon}] {c.name:12s} nota={c.score:5.2f}/10  peso={c.weight:.2f}  {c.details}")
        if c.error:
            print(f"          erro: {c.error}")
    print("-" * 64)
    print(f"NOTA FINAL: {final_score}/10   (mínimo exigido: nota > {args.min_score})")
    print(f"APROVADO PARA PRODUÇÃO: {'SIM' if approved else 'NÃO'}")
    print("=" * 64)

    return 0 if approved else 1


if __name__ == "__main__":
    sys.exit(main())
