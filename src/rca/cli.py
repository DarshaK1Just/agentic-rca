"""Command-line interface for the RCA engine.

Examples
--------
    # Investigate an incident with a natural-language question
    rca investigate data/production_incident_01.log \
        --query "What caused the 503 errors for TENANT-X around 16:10?"

    # Quick corpus profile (deterministic, no LLM)
    rca profile data/auth_rate_limit_noise.log
"""
from __future__ import annotations

import warnings

import typer

warnings.filterwarnings("ignore")  # silence vendor FutureWarnings in the CLI

app = typer.Typer(add_completion=False, help="Agentic RCA over multi-tenant logs.")


@app.command()
def investigate(
    logs: list[str] = typer.Argument(..., help="One or more log file paths."),
    query: str = typer.Option(..., "--query", "-q", help="Natural-language question."),
    vectors: bool = typer.Option(False, "--vectors", help="Build the semantic index."),
):
    """Run the full plan→retrieve→reflect→synthesize loop and print a cited RCA."""
    from rca.agent.llm_provider import llm_available
    from rca.config import settings
    from rca.pipeline import build_engine

    engine, stats = build_engine(list(logs), with_vectors=vectors)
    typer.secho(
        f"Ingested {stats.events} events ({stats.distinct_templates} templates) "
        f"from {', '.join(stats.files)} in {stats.ingest_seconds}s.",
        fg=typer.colors.CYAN,
    )
    mode = f"LLM={settings.provider}" if llm_available() else "deterministic (no LLM key)"
    typer.secho(f"Synthesis mode: {mode}\n", fg=typer.colors.CYAN)

    res = engine.investigate(query)

    typer.secho("=" * 80, fg=typer.colors.BRIGHT_BLACK)
    typer.secho(f"QUERY: {res.query}", fg=typer.colors.WHITE, bold=True)
    typer.secho("=" * 80, fg=typer.colors.BRIGHT_BLACK)
    typer.echo(res.narrative)
    typer.echo("")
    badge = "VERIFIED" if res.chain.chronology_verified else "UNVERIFIED"
    typer.secho(f"[causal chronology: {badge}] "
                f"[citations verified: {res.citations_verified}] "
                f"[LLM used: {res.llm_used}]", fg=typer.colors.GREEN)
    for w in res.warnings:
        typer.secho(f"! {w}", fg=typer.colors.YELLOW)

    typer.secho("\nEvidence (verbatim, line-addressable):", fg=typer.colors.BRIGHT_BLACK)
    for e in res.evidence:
        typer.echo(f"  {e.citation()} | {e.level:<5} {e.message[:70]}")


@app.command()
def profile(logs: list[str] = typer.Argument(..., help="Log file path(s).")):
    """Deterministic corpus profile: tenants, template frequencies, rare anomalies."""
    from rca.pipeline import build_engine

    engine, stats = build_engine(list(logs))
    store = engine.tools.store
    typer.secho(f"{stats.events} events | {stats.distinct_templates} templates | "
                f"{stats.ingest_seconds}s\n", fg=typer.colors.CYAN)
    for t in store.tenants():
        freqs = store.template_frequencies(tenant_id=t)
        n = sum(f["count"] for f in freqs)
        rare = store.rare_anomalies(t, min_level="WARN", k=3)
        typer.secho(f"{t}: {n} events, {len(freqs)} templates", bold=True)
        for r in rare:
            typer.echo(f"    rare WARN+  x{r.occurrences:<4} {r.component} | {r.message[:55]}")


if __name__ == "__main__":
    app()
