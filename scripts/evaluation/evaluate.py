#!/usr/bin/env python3
"""Compare authenticated retrieval modes against labeled source documents."""

import argparse
import json
import math
import statistics
import time
from pathlib import Path

import httpx
from azure.identity import DefaultAzureCredential


def scores(results, relevant, k):
    # Score documents, not repeated chunks of the same document.
    ranked = list(dict.fromkeys(item["sourcefile"] for item in results))[:k]
    hits = [1 if source in relevant else 0 for source in ranked]
    recall = sum(hits) / len(relevant) if relevant else 1.0
    reciprocal = next((1 / (i + 1) for i, hit in enumerate(hits) if hit), 0.0)
    dcg = sum(hit / math.log2(i + 2) for i, hit in enumerate(hits))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return {"recall_at_k": recall, "mrr": reciprocal, "ndcg_at_k": dcg / ideal if ideal else 1.0}


def evaluate(client, url, cases, modes, k, headers):
    rows = []
    for mode in modes:
        for case in cases:
            start = time.perf_counter()
            response = client.get(
                f"{url.rstrip('/')}/api/search",
                headers=headers(),
                params={
                    "q": case["query"],
                    "index_name": case["index_name"],
                    "top": k,
                    "mode": "hybrid" if mode == "hybrid-semantic" else mode,
                    "semantic": "true" if mode == "hybrid-semantic" else "false",
                },
            )
            latency = (time.perf_counter() - start) * 1000
            response.raise_for_status()
            results = response.json()
            forbidden = set(case.get("forbidden_sourcefiles", []))
            leaked = any(item["sourcefile"] in forbidden for item in results)
            if leaked:
                raise AssertionError(f"Permission regression in case {case['id']}")
            expected_pages = case.get("expected_pages", {})
            checked = [item for item in results if item["sourcefile"] in expected_pages]
            citation_hits = sum(
                bool(set(item.get("pages", [])) & set(expected_pages[item["sourcefile"]])) for item in checked
            )
            rows.append(
                {
                    "case": case["id"],
                    "mode": mode,
                    "latency_ms": latency,
                    **scores(results, set(case["relevant_sourcefiles"]), k),
                    "citation_hits": citation_hits,
                    "citation_checks": len(checked),
                }
            )
    summary = {}
    for mode in modes:
        values = [row for row in rows if row["mode"] == mode]
        latency = sorted(row["latency_ms"] for row in values)
        summary[mode] = {
            metric: statistics.mean(row[metric] for row in values)
            for metric in ("recall_at_k", "mrr", "ndcg_at_k")
        }
        summary[mode].update(
            p50_ms=statistics.median(latency), p95_ms=latency[math.ceil(0.95 * len(latency)) - 1]
        )
        count = sum(row["citation_checks"] for row in values)
        summary[mode]["citation_accuracy"] = (
            sum(row["citation_hits"] for row in values) / count if count else None
        )
    return {"summary": summary, "cases": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument(
        "--audience", required=True, help="Entra API application ID URI, e.g. api://client-id"
    )
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--min-recall", type=float, default=0.8)
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=["keyword", "vector", "hybrid", "hybrid-semantic"],
        default=["keyword", "vector", "hybrid", "hybrid-semantic"],
    )
    args = parser.parse_args()
    cases = [json.loads(line) for line in Path(args.cases).read_text().splitlines() if line.strip()]
    if not cases or not 1 <= args.k <= 50:
        parser.error("Supply nonempty labeled cases and k between 1 and 50")
    with DefaultAzureCredential() as credential, httpx.Client(timeout=60) as client:

        def headers():
            return {
                "Authorization": f"Bearer {credential.get_token(args.audience.rstrip('/') + '/.default').token}"
            }

        result = evaluate(client, args.url, cases, args.modes, args.k, headers)
    Path(args.output).write_text(json.dumps(result, indent=2))
    if (
        result["summary"].get("hybrid-semantic", result["summary"][args.modes[-1]])["recall_at_k"]
        < args.min_recall
    ):
        raise SystemExit("Recall gate failed; inspect the evaluation artifact")


if __name__ == "__main__":
    main()
