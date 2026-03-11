from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence
from urllib.parse import urlparse

from .search import (
    evaluate_scraped_content,
    scrape_archived_domain,
    scrape_web_content,
    search_brave_web,
    search_multi_engine_web,
)


def _domain_of(url: str) -> str:
    parsed = urlparse(url or "")
    return parsed.netloc or ""


def _dedupe_by_url(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for item in items:
        url = str(item.get("url") or "").strip()
        key = url or f"{item.get('title', '')}|{item.get('source_type', '')}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


@dataclass
class ScraperTactic:
    name: str
    mode: str
    query_template: Optional[str] = None
    max_results: int = 5
    freshness: Optional[str] = None
    scrape_top_results: bool = False
    weight: float = 1.0


@dataclass
class ScraperDaemonConfig:
    iterations: int = 3
    sleep_seconds: float = 0.0
    max_results_per_tactic: int = 5
    max_scrapes_per_tactic: int = 3
    min_quality_score: float = 40.0
    quality_domain: str = "caselaw"
    stall_iterations: int = 2


@dataclass
class ScraperCritique:
    quality_score: float
    coverage_score: float
    novelty_score: float
    diversity_score: float
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quality_score": self.quality_score,
            "coverage_score": self.coverage_score,
            "novelty_score": self.novelty_score,
            "diversity_score": self.diversity_score,
            "issues": self.issues,
            "recommendations": self.recommendations,
        }


@dataclass
class ScraperIterationReport:
    iteration: int
    tactics: List[Dict[str, Any]]
    discovered_count: int
    accepted_count: int
    scraped_count: int
    coverage: Dict[str, Any]
    quality: Dict[str, Any]
    critique: ScraperCritique

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "tactics": self.tactics,
            "discovered_count": self.discovered_count,
            "accepted_count": self.accepted_count,
            "scraped_count": self.scraped_count,
            "coverage": self.coverage,
            "quality": self.quality,
            "critique": self.critique.to_dict(),
        }


class ScraperDaemon:
    def __init__(self, config: Optional[ScraperDaemonConfig] = None):
        self.config = config or ScraperDaemonConfig()
        self.coverage_ledger: Dict[str, Dict[str, Any]] = {}
        self.tactic_history: Dict[str, List[float]] = {}

    def _default_tactics(self) -> List[ScraperTactic]:
        return [
            ScraperTactic(
                name="multi_engine_search",
                mode="multi_engine_search",
                query_template="{keywords}",
                max_results=self.config.max_results_per_tactic,
                scrape_top_results=True,
                weight=1.2,
            ),
            ScraperTactic(
                name="brave_search_fresh",
                mode="brave_search",
                query_template="{keywords}",
                max_results=self.config.max_results_per_tactic,
                freshness="pw",
                scrape_top_results=True,
                weight=1.0,
            ),
            ScraperTactic(
                name="domain_archive_sweep",
                mode="archived_domain_scrape",
                max_results=self.config.max_results_per_tactic,
                weight=0.9,
            ),
        ]

    def _render_query(self, tactic: ScraperTactic, keywords: Sequence[str], domains: Optional[Sequence[str]]) -> str:
        keyword_text = " ".join(keyword.strip() for keyword in keywords if keyword and keyword.strip())
        domain_text = " site:" + " OR site:".join(domains) if domains else ""
        template = tactic.query_template or "{keywords}"
        return template.format(keywords=keyword_text, domains=domain_text).strip()

    def _evaluate_tactic(self,
                         tactic: ScraperTactic,
                         keywords: Sequence[str],
                         domains: Optional[Sequence[str]]) -> Dict[str, Any]:
        query = self._render_query(tactic, keywords, domains)
        discovered: List[Dict[str, Any]] = []
        scraped: List[Dict[str, Any]] = []

        if tactic.mode == "multi_engine_search":
            discovered = search_multi_engine_web(query, max_results=tactic.max_results)
        elif tactic.mode == "brave_search":
            discovered = search_brave_web(
                query,
                max_results=tactic.max_results,
                freshness=tactic.freshness,
            )
        elif tactic.mode == "archived_domain_scrape" and domains:
            for domain in domains:
                discovered.extend(
                    scrape_archived_domain(
                        domain,
                        max_pages=tactic.max_results,
                    )
                )

        discovered = _dedupe_by_url(discovered)
        if tactic.scrape_top_results:
            for item in discovered[: self.config.max_scrapes_per_tactic]:
                url = str(item.get("url") or "").strip()
                if not url:
                    continue
                scraped_item = scrape_web_content(url)
                if scraped_item.get("success"):
                    merged = {
                        **item,
                        "content": scraped_item.get("content") or item.get("content", ""),
                        "description": item.get("description") or scraped_item.get("description", ""),
                        "metadata": {
                            **(item.get("metadata") if isinstance(item.get("metadata"), dict) else {}),
                            "original_source_type": item.get("source_type", tactic.mode),
                            "scrape": scraped_item.get("metadata", {}),
                            "scrape_errors": scraped_item.get("errors", []),
                        },
                        "source_type": item.get("source_type", tactic.mode),
                    }
                    scraped.append(merged)

        accepted = []
        for item in scraped or discovered:
            content = str(item.get("content") or item.get("description") or "").strip()
            if not content:
                continue
            accepted.append(item)

        quality = evaluate_scraped_content(
            accepted or discovered,
            scraper_name=tactic.name,
            domain=self.config.quality_domain,
        )
        quality_score = float(quality.get("data_quality_score", 0.0) or 0.0)
        novelty_count = 0
        for item in accepted:
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            if url not in self.coverage_ledger:
                novelty_count += 1

        report = {
            "name": tactic.name,
            "mode": tactic.mode,
            "query": query,
            "weight": tactic.weight,
            "discovered_count": len(discovered),
            "scraped_count": len(scraped),
            "accepted_count": len(accepted),
            "quality_score": quality_score,
            "novelty_count": novelty_count,
            "quality": quality,
            "results": accepted or discovered,
        }
        self.tactic_history.setdefault(tactic.name, []).append(quality_score)
        return report

    def _compute_coverage(self, items: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        urls = [str(item.get("url") or "").strip() for item in items if str(item.get("url") or "").strip()]
        domains = {_domain_of(url) for url in urls if _domain_of(url)}
        source_types = {str(item.get("source_type") or "") for item in items if str(item.get("source_type") or "")}
        content_lengths = [len(str(item.get("content") or item.get("description") or "")) for item in items]
        return {
            "unique_urls": len(set(urls)),
            "unique_domains": len(domains),
            "source_diversity": len(source_types),
            "average_content_length": round(sum(content_lengths) / max(1, len(content_lengths)), 2),
        }

    def _critique_iteration(self,
                            coverage: Dict[str, Any],
                            quality: Dict[str, Any],
                            tactic_reports: Sequence[Dict[str, Any]],
                            accepted_count: int) -> ScraperCritique:
        quality_score = float(quality.get("data_quality_score", 0.0) or 0.0)
        coverage_score = min(100.0, coverage.get("unique_urls", 0) * 10.0 + coverage.get("unique_domains", 0) * 8.0)
        diversity_score = min(100.0, coverage.get("source_diversity", 0) * 25.0)
        novelty_score = min(
            100.0,
            _safe_ratio(
                sum(report.get("novelty_count", 0) for report in tactic_reports),
                max(1, accepted_count),
            ) * 100.0,
        )

        issues: List[str] = []
        recommendations: List[str] = []
        if quality_score < self.config.min_quality_score:
            issues.append("Scraped content quality is below threshold")
            recommendations.append("Shift weight toward archived-domain sweeps and reduce shallow search-only tactics")
        if coverage.get("unique_domains", 0) < 2:
            issues.append("Coverage is concentrated in too few domains")
            recommendations.append("Add more target domains or broaden search queries")
        if diversity_score < 50.0:
            issues.append("Strategy diversity is low")
            recommendations.append("Keep both multi-engine search and archive sweeps active")
        if novelty_score < 35.0:
            issues.append("Recent iterations are recycling already-seen URLs")
            recommendations.append("Lower weight for repeated tactics and expand query variants")

        return ScraperCritique(
            quality_score=round(quality_score, 2),
            coverage_score=round(coverage_score, 2),
            novelty_score=round(novelty_score, 2),
            diversity_score=round(diversity_score, 2),
            issues=issues,
            recommendations=recommendations,
        )

    def _optimize_tactics(self,
                          tactics: Sequence[ScraperTactic],
                          reports: Sequence[Dict[str, Any]]) -> List[ScraperTactic]:
        report_by_name = {report["name"]: report for report in reports}
        optimized: List[ScraperTactic] = []
        for tactic in tactics:
            report = report_by_name.get(tactic.name, {})
            quality_score = float(report.get("quality_score", 0.0) or 0.0)
            novelty_count = int(report.get("novelty_count", 0) or 0)

            weight = tactic.weight
            if quality_score >= self.config.min_quality_score:
                weight += 0.15
            else:
                weight -= 0.2
            if novelty_count > 0:
                weight += 0.1
            else:
                weight -= 0.1

            optimized.append(
                ScraperTactic(
                    name=tactic.name,
                    mode=tactic.mode,
                    query_template=tactic.query_template,
                    max_results=tactic.max_results,
                    freshness=tactic.freshness,
                    scrape_top_results=tactic.scrape_top_results,
                    weight=max(0.1, round(weight, 2)),
                )
            )
        return sorted(optimized, key=lambda tactic: tactic.weight, reverse=True)

    def run(self,
            *,
            keywords: Sequence[str],
            domains: Optional[Sequence[str]] = None,
            tactics: Optional[Sequence[ScraperTactic]] = None) -> Dict[str, Any]:
        active_tactics = list(tactics or self._default_tactics())
        iterations: List[Dict[str, Any]] = []
        all_accepted: List[Dict[str, Any]] = []
        stall_count = 0

        for iteration in range(1, self.config.iterations + 1):
            tactic_reports = [self._evaluate_tactic(tactic, keywords, domains) for tactic in active_tactics]
            accepted = _dedupe_by_url(
                item
                for report in tactic_reports
                for item in report.get("results", [])
            )
            coverage = self._compute_coverage(accepted)
            quality = evaluate_scraped_content(
                accepted,
                scraper_name="agentic_scraper_daemon",
                domain=self.config.quality_domain,
            )
            critique = self._critique_iteration(coverage, quality, tactic_reports, len(accepted))

            for item in accepted:
                url = str(item.get("url") or "").strip()
                if not url:
                    continue
                self.coverage_ledger[url] = {
                    "domain": _domain_of(url),
                    "source_type": item.get("source_type", ""),
                    "last_seen_iteration": iteration,
                }

            if tactic_reports and sum(report.get("novelty_count", 0) for report in tactic_reports) == 0:
                stall_count += 1
            else:
                stall_count = 0

            report = ScraperIterationReport(
                iteration=iteration,
                tactics=[
                    {
                        key: value
                        for key, value in tactic_report.items()
                        if key != "results"
                    }
                    for tactic_report in tactic_reports
                ],
                discovered_count=sum(report.get("discovered_count", 0) for report in tactic_reports),
                accepted_count=len(accepted),
                scraped_count=sum(report.get("scraped_count", 0) for report in tactic_reports),
                coverage=coverage,
                quality=quality,
                critique=critique,
            )
            iterations.append(report.to_dict())
            all_accepted.extend(accepted)

            if stall_count >= self.config.stall_iterations:
                break

            active_tactics = self._optimize_tactics(active_tactics, tactic_reports)
            if self.config.sleep_seconds > 0 and iteration < self.config.iterations:
                time.sleep(self.config.sleep_seconds)

        final_results = _dedupe_by_url(all_accepted)
        return {
            "iterations": iterations,
            "final_results": final_results,
            "coverage_ledger": self.coverage_ledger,
            "tactic_history": self.tactic_history,
            "final_quality": evaluate_scraped_content(
                final_results,
                scraper_name="agentic_scraper_daemon",
                domain=self.config.quality_domain,
            ),
        }


__all__ = [
    "ScraperCritique",
    "ScraperDaemon",
    "ScraperDaemonConfig",
    "ScraperIterationReport",
    "ScraperTactic",
]