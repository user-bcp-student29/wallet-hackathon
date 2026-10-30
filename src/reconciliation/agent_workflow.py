from __future__ import annotations

import os
from typing import Any, TypedDict

from .agent_tools import W6ReadOnlyTools
from .guardrails import ALLOWED_RECOMMENDATIONS, validate_recommendation
from .w6_group import W6PaymentGroup


class AgentRuntimeUnavailable(RuntimeError):
    pass


class AgentWorkflowError(RuntimeError):
    pass


class AgentWorkflowState(TypedDict, total=False):
    sources: dict[str, list[dict[str, Any]]]
    analysis: dict[str, Any]
    result: dict[str, Any]


class W6AnalysisWorkflow:
    def __init__(self, group: W6PaymentGroup) -> None:
        self._tools = W6ReadOnlyTools(group)
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as error:
            raise AgentRuntimeUnavailable(
                "LangGraph is not installed. Use the Python 3.13 AI environment."
            ) from error

        graph = StateGraph(AgentWorkflowState)
        graph.add_node("collect_read_only_sources", self._collect_sources)
        graph.add_node("analyze_snapshot", self._analyze_snapshot)
        graph.add_node("enforce_guardrails", self._enforce_guardrails)
        graph.add_edge(START, "collect_read_only_sources")
        graph.add_edge("collect_read_only_sources", "analyze_snapshot")
        graph.add_edge("analyze_snapshot", "enforce_guardrails")
        graph.add_edge("enforce_guardrails", END)
        self._graph = graph.compile()

    def run(self) -> dict[str, Any]:
        state = self._graph.invoke({})
        return state["result"]

    def _collect_sources(self, _state: AgentWorkflowState) -> AgentWorkflowState:
        return {
            "sources": {
                name: self._tools.invoke(name)
                for name in self._tools.names
            }
        }

    def _analyze_snapshot(self, state: AgentWorkflowState) -> AgentWorkflowState:
        sources = state["sources"]
        open_incidents = [
            incident
            for incident in sources["get_reconciliation_incidents"]
            if incident["status"] == "OPEN"
        ]
        reasons = sorted({incident["reason"] for incident in open_incidents})
        summary = {
            "wallet_payments": len(sources["get_wallet_payments"]),
            "settlement_rows": len(sources["get_settlements"]),
            "ledger_entries": len(sources["get_ledger"]),
            "open_incidents": len(open_incidents),
            "open_incident_reasons": reasons,
        }

        crew_enabled = os.environ.get("ENABLE_CREWAI", "").casefold() == "true"
        model = os.environ.get("CREWAI_MODEL", "").strip()
        if crew_enabled and not model:
            raise AgentRuntimeUnavailable(
                "ENABLE_CREWAI=true requires CREWAI_MODEL to be configured."
            )
        if crew_enabled:
            recommendation = self._run_crewai(summary, model)
            crew_status = "ENABLED"
        elif open_incidents:
            recommendation = "Compare source records and request an operational review."
            crew_status = "DISABLED"
        else:
            recommendation = "Run POST /reconciliations to refresh the incident state."
            crew_status = "DISABLED"

        return {
            "analysis": {
                "summary": summary,
                "crew_status": crew_status,
                "recommendation": recommendation,
            }
        }

    def _enforce_guardrails(self, state: AgentWorkflowState) -> AgentWorkflowState:
        analysis = state["analysis"]
        result = validate_recommendation(analysis["recommendation"])
        if not result.passed:
            raise AgentWorkflowError(
                f"CrewAI recommendation blocked: {result.reason}"
            )
        return {
            "result": {
                "workflow": "LangGraph",
                "execution_mode": (
                    "deterministic_local"
                    if analysis["crew_status"] == "DISABLED"
                    else "crewai_opt_in"
                ),
                "crewai_status": analysis["crew_status"],
                "tools": self._tools.names,
                "snapshot": analysis["summary"],
                "recommendation": analysis["recommendation"],
                "guardrail": result.as_dict(),
                "reconciliation_note": (
                    "This read-only analysis does not recalculate incidents. "
                    "Use POST /reconciliations to refresh their state."
                ),
            }
        }

    @staticmethod
    def _run_crewai(summary: dict[str, Any], model: str) -> str:
        try:
            from crewai import Agent, Crew, Process, Task
        except ImportError as error:
            raise AgentRuntimeUnavailable(
                "CrewAI is not installed in the selected Python environment."
            ) from error

        recommendations = "\n".join(
            f"- {recommendation}" for recommendation in sorted(ALLOWED_RECOMMENDATIONS)
        )
        analyst = Agent(
            role="Wallet reconciliation analyst",
            goal="Choose one safe, read-only recommendation for the current snapshot.",
            backstory=(
                "You analyze synthetic reconciliation summaries. You cannot call "
                "tools, approve payments, change balances, or modify ledger entries."
            ),
            llm=model,
            allow_delegation=False,
            max_iter=1,
            verbose=False,
        )
        task = Task(
            description=(
                "Based only on this aggregate synthetic snapshot, return exactly "
                "one of the allowed recommendations, with no extra text.\n"
                f"Snapshot: {summary}\n"
                f"Allowed recommendations:\n{recommendations}"
            ),
            expected_output="Exactly one allowed recommendation, without explanation.",
            agent=analyst,
        )
        crew = Crew(
            agents=[analyst],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
        )
        try:
            output = crew.kickoff()
        except RuntimeError as error:
            raise AgentWorkflowError(f"CrewAI execution failed: {error}") from error
        return str(output).strip()
