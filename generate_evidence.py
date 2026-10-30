from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from reconciliation.service import ReconciliationService  # noqa: E402
from reconciliation.w6_group import W6PaymentGroup  # noqa: E402


def main() -> None:
    test_command = [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests",
        "-v",
    ]
    test_run = subprocess.run(
        test_command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    test_output = test_run.stdout + test_run.stderr
    test_count = re.search(r"Ran (\d+) tests?", test_output)
    if test_run.returncode != 0:
        raise RuntimeError(
            "automated tests failed; evidence was not generated:\n" + test_output
        )
    test_summary = (
        f"PASS — {test_count.group(1)} pruebas"
        if test_count
        else "PASS — unittest devolvió código de salida 0"
    )

    service = ReconciliationService(ROOT / "fixtures", ROOT / "artifacts")
    run = service.create_run()
    w6_group = W6PaymentGroup()
    initial_w6 = w6_group.reconcile()
    w6_group.control_settlement(
        {"paymentId": "PAY-1500", "mode": "AMOUNT", "amountCents": 1600}
    )
    amount_difference = w6_group.reconcile()
    w6_incident_id = amount_difference["differences"][0]["id"]
    repeated_difference = w6_group.reconcile()
    stable_incident = repeated_difference["differences"][0]["id"] == w6_incident_id
    w6_group.control_settlement({"paymentId": "PAY-1500", "mode": "CLEAR"})
    resolved_w6 = w6_group.reconcile()
    resolved_incident = next(
        incident
        for incident in w6_group.get_incidents()
        if incident["id"] == w6_incident_id
    )
    w6_evidence = {
        "initial_status": initial_w6["status"],
        "amount_difference_status": amount_difference["status"],
        "amount_difference_reason": amount_difference["differences"][0]["reason"],
        "incident_id_stable_on_repeat": stable_incident,
        "resolved_status": resolved_w6["status"],
        "incident_final_status": resolved_incident["status"],
        "wallet_amount_cents_after_control": w6_group.payments["PAY-1500"].amount_cents,
    }
    (ROOT / "artifacts" / "w6-contract-flow.json").write_text(
        json.dumps(w6_evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    counts = run["summary"]
    lines = [
        "# Evidencia de conciliación W6",
        "",
        f"- Ejecución: `{run['run_id']}`",
        f"- Generado el (UTC): `{run['created_at']}`",
        "- Fuentes: fixtures JSON sintéticos de wallet, proveedor y ledger.",
        "- Ejecución: servicio local determinista en Python; sin integraciones externas.",
        "- Movimiento de dinero: ninguno.",
        f"- Pruebas automatizadas: `{test_summary}`",
        f"- Flujo de API W6: `{w6_evidence['initial_status']} → "
        f"{w6_evidence['amount_difference_reason']} → "
        f"{w6_evidence['incident_final_status']}`.",
        "",
        "## Evidencia de aceptación",
        "",
        "| Verificación | Resultado |",
        "|---|---:|",
        f"| Transacciones procesadas | {counts['processed']} |",
        f"| Coincidentes | {counts['matched']} |",
        f"| Diferencias | {counts['differences']} |",
        f"| Pendientes de revisión | {counts['pending']} |",
        f"| Requieren revisión humana | {counts['human_review']} |",
        "",
        "SHA-256 de los fixtures:",
        "",
    ]
    for source, digest in sorted(run["fixture_hashes"].items()):
        lines.append(f"- `{source}`: `{digest}`")

    lines.extend(["",     "## Resultados por transacción", ""])
    lines.extend(
        [
                "| Transacción | Conciliación | Tipos de diferencia | Severidad | Revisión humana |",
            "|---|---|---|---|---|",
        ]
    )
    for result in run["results"]:
        difference_types = ", ".join(result["difference_types"]) or "—"
        lines.append(
            f"| `{result['transaction_id']}` | `{result['reconciliation_status']}` "
            f"| {difference_types} | `{result['severity']}` "
            f"| {'Sí' if result['requires_human_review'] else 'No'} |"
        )
    lines.extend(
        [
            "",
            "## Validación",
            "",
            f"Comando: `python -m unittest discover -s tests -v` — {test_summary}.",
            "",
            "## Notas de guardrails y HITL",
            "",
            "- El esquema de origen, los tipos de monto, la moneda, los identificadores,",
            "  el tamaño de los fixtures y los valores con apariencia de secreto se",
            "  validan antes de conciliar.",
            "- Se bloquean los nombres de herramientas financieras y las",
            "  recomendaciones financieras inseguras.",
            "- Los resultados marcados para revisión humana son orientativos; este corte",
            "  no ejecuta acciones financieras ni aprueba pagos.",
            f"- Ejecución con control de monto: `{w6_evidence['initial_status']}` a "
            f"`{w6_evidence['amount_difference_status']}` "
            f"(`{w6_evidence['amount_difference_reason']}`), incidencia "
            f"`{w6_incident_id}` conservada al repetir, luego "
            f"`{w6_evidence['incident_final_status']}` tras limpiar.",
            "- Evidencia del flujo W6: `artifacts/w6-contract-flow.json`.",
        ]
    )
    (ROOT / "evidence.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Generated evidence.md and artifacts/{run['run_id']}.json")


if __name__ == "__main__":
    main()
