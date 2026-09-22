"use client";

import React, { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Layers,
  FileText,
  ExternalLink,
  Printer,
  Download,
} from "lucide-react";
import { api } from "../../../src/api";
import {
  EntityRisk,
  ManifestData,
  RiskContribution,
  parseFindingIds,
  dimensionConfigFromManifest,
  riskBandThresholdsFromManifest,
} from "../../../src/types";
import {
  RiskBandBadge,
  CorroborationBadge,
  DetectorTypeBadge,
  EvidenceStrengthBadge,
} from "../../../src/components/Badges";
import { DimensionCard } from "../../../src/components/DimensionCard";
import { RiskDimensionBarChart } from "../../../src/components/RiskProfileCharts";
import { FindingDetailDrawer } from "../../../src/components/FindingDetailDrawer";
import { LoadingSkeleton, ErrorState } from "../../../src/components/States";

export default function CSEDetailPage() {
  const params = useParams();
  const router = useRouter();
  const entityId = (params?.entityId as string) || "CSE-011";

  const [entity, setEntity] = useState<EntityRisk | null>(null);
  const [contributions, setContributions] = useState<RiskContribution[]>([]);
  const [manifest, setManifest] = useState<ManifestData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Finding inspector drawer state
  const [inspectedFindingId, setInspectedFindingId] = useState<string | null>(null);

  // Progressive disclosure state for contributions
  const [expandedRowId, setExpandedRowId] = useState<string | null>(null);

  // Cross-highlighting state
  const [selectedDimension, setSelectedDimension] = useState<string | null>(null);

  const [downloadingJson, setDownloadingJson] = useState(false);

  const handleDownloadJson = async () => {
    try {
      setDownloadingJson(true);
      const dossier = await api.getEntityDossier(entityId);
      const blob = new Blob([JSON.stringify(dossier, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `supervisory_dossier_${entityId}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Failed to download dossier JSON:", err);
      alert("Failed to download supervisory dossier JSON.");
    } finally {
      setDownloadingJson(false);
    }
  };

  const handlePrintPdf = () => {
    window.open(api.getDossierHtmlUrl(entityId), "_blank");
  };

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [entityRes, contribRes, manifestRes] = await Promise.all([
        api.getEntity(entityId),
        api.getContributions(entityId),
        api.getManifest().catch(() => null),
      ]);
      setEntity(entityRes);
      setContributions(contribRes);
      setManifest(manifestRes);
    } catch (err: any) {
      setError(err.message || `Failed loading assessment for ${entityId}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [entityId]);

  if (loading) {
    return <LoadingSkeleton variant="detail" text={`Loading supervisory assessment for ${entityId}...`} />;
  }

  if (error || !entity) {
    return <ErrorState message={error || "Entity assessment not found."} onRetry={fetchData} />;
  }

  const dimensionConfig = dimensionConfigFromManifest(manifest);
  const thresholds = riskBandThresholdsFromManifest(manifest);

  // Format dimension chart data
  const dimensionChartData = dimensionConfig.map((dim) => ({
    dimension: dim.key,
    score: (entity as any)[dim.field] as number | null,
    weight: dim.weight,
  }));

  // Identify elevated dimensions for "Why Flagged"
  const elevatedDimensions = dimensionConfig
    .filter((d) => {
      const score = (entity as any)[d.field];
      return score !== null && score >= thresholds.moderate;
    })
    .sort((a, b) => ((entity as any)[b.field] || 0) - ((entity as any)[a.field] || 0));

  // Derive the primary correlation group from the manifest for the top risk dimension
  const topGroup = Object.entries(manifest?.correlation_groups ?? {}).find(
    ([, g]) => g.dimension.toLowerCase() === entity.top_risk_dimension.toLowerCase(),
  );
  const groupKey = topGroup?.[0] ?? null;
  const groupDetectors = topGroup?.[1].detectors ?? [];

  // Find primary finding for the top elevated dimension (e.g. EG002 for Investigation)
  const topContribution =
    (groupKey
      ? contributions.find(
        (c) =>
          c.corroboration_group === groupKey &&
          c.dimension.toLowerCase().includes(entity.top_risk_dimension.toLowerCase()),
      )
      : undefined) ||
    contributions.find((c) =>
      c.dimension.toLowerCase().includes(entity.top_risk_dimension.toLowerCase()),
    );
  const topFindingIds = parseFindingIds(topContribution?.supporting_finding_ids);
  const fallbackFindingIds = parseFindingIds(contributions[0]?.supporting_finding_ids);
  const primaryFindingId = topFindingIds[0] ?? fallbackFindingIds[0] ?? null;

  // Corroboration callout, derived from the manifest group + actual contributions
  const corroborationContribs = groupDetectors.length
    ? contributions.filter((c) => groupDetectors.includes(c.detector_id))
    : [];
  const corroborationPhases = Array.from(
    new Set(corroborationContribs.map((c) => c.source_phase)),
  ).sort();
  const corroborationDetectors = Array.from(
    new Set(corroborationContribs.map((c) => c.detector_id)),
  );
  const corroborationGroupId = groupKey ?? "INVESTIGATION_EFFORT";
  const corroborationDescription =
    topGroup?.[1].description ??
    "Multiple analytical detectors observe the same underlying operational deficiency.";

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link
          href="/cses"
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-secondary)] text-xs font-medium text-[var(--fg)] hover:bg-[var(--border)] transition shadow-sm cursor-pointer"
        >
          <ArrowLeft className="w-3.5 h-3.5 text-[var(--muted)]" />
          <span>Back</span>
        </Link>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handlePrintPdf}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-secondary)] text-xs font-medium text-[var(--fg)] hover:bg-[var(--border)] transition shadow-sm cursor-pointer"
            title="Open printable examination dossier (Save as PDF)"
          >
            <Printer className="w-3.5 h-3.5 text-sky-500" />
            <span>Print / PDF Dossier</span>
          </button>
          <button
            onClick={handleDownloadJson}
            disabled={downloadingJson}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-secondary)] text-xs font-medium text-[var(--fg)] hover:bg-[var(--border)] transition shadow-sm disabled:opacity-50 cursor-pointer"
            title="Download full JSON audit dossier"
          >
            <Download className="w-3.5 h-3.5 text-[var(--muted)]" />
            <span>{downloadingJson ? "Exporting..." : "Audit JSON"}</span>
          </button>
        </div>
      </div>

      {/* Editorial Identity & Risk Hero */}
      <div className="p-6 sm:p-8 rounded-2xl border border-[var(--border)] bg-[var(--surface)] space-y-6">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-6">
          {/* Identity */}
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-xs font-mono text-[var(--muted)]">
              <span>{entity.sector || "Energy & Utilities"}</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-[var(--fg)]">
              {entity.name || entity.entity_id}
            </h1>
            <p className="text-xs text-[var(--muted)] pt-1">
              Assessment Coverage: {(entity.assessment_coverage * 100).toFixed(0)}% ({entity.assessable_dimensions}/{entity.total_dimensions} Dimensions Assessable) • Cryptographic Commitment: SHA-256 Provenance
            </p>
          </div>

          {/* Calm, Dominant Risk Metric */}
          <div className="p-4 sm:p-5 rounded-xl border border-[var(--border)] bg-[var(--surface-secondary)] min-w-[200px] text-right space-y-1 self-start sm:self-auto">
            <span className="text-[10px] font-mono uppercase tracking-wider text-[var(--muted)] block">
              Supervisory Risk
            </span>
            <div className="font-mono text-3xl sm:text-4xl font-bold tabular-nums text-[var(--fg)]">
              {entity.overall_score.toFixed(2)}
              <span className="text-xs font-normal text-[var(--muted)] ml-1">/100</span>
            </div>
            <div className="pt-1 flex justify-end">
              <RiskBandBadge band={entity.risk_band} />
            </div>
          </div>
        </div>
      </div>

      {/* SIGNATURE UX: "Why This Entity Is Flagged" */}
      <div className="p-6 sm:p-8 rounded-2xl border border-[var(--border)] bg-[var(--surface)] space-y-5">
        <div className="flex items-baseline justify-between border-b border-[var(--border)] pb-3">
          <h2 className="text-sm font-semibold tracking-tight text-[var(--fg)] uppercase font-mono">
            Why This Entity Is Flagged
          </h2>
          <span className="text-[11px] font-mono text-[var(--muted)]">
            Corroborated Supervisory Evidence
          </span>
        </div>

        {/* Top Flagged Dimension Block */}
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-2">
            <div>
              <span className="text-lg font-semibold text-[var(--fg)]">
                {entity.top_risk_dimension}
              </span>
              <p className="text-xs text-[var(--muted)] mt-0.5">
                {entity.top_reason || "Critical investigation effort is materially below configured supervisory expectation."}
              </p>
            </div>
            <div className="text-right">
              <span className="font-mono text-2xl font-bold tabular-nums text-[var(--fg)]">
                {(entity as any)[`${entity.top_risk_dimension.toLowerCase().replace(/ /g, "_")}_score`]?.toFixed(1) || "100.0"}
              </span>
              <span className="text-xs text-[var(--muted)] font-mono ml-0.5">/100</span>
            </div>
          </div>

          {/* Multi-Phase Corroboration Callout */}
          <div className="p-4 rounded-xl border border-[var(--border)] bg-[var(--surface-secondary)] space-y-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-mono font-semibold text-[var(--fg)] uppercase tracking-wider">
                  Corroboration
                </span>
                <span className="text-xs font-mono text-[var(--muted)]">
                  {corroborationPhases.length > 0
                    ? corroborationPhases.map((p) => `Phase ${p.replace("phase", "")}`).join(" · ")
                    : "Single Phase"}
                </span>
              </div>
              <div className="flex items-center gap-1.5 font-mono text-[10px] text-[var(--muted)]">
                <span>{corroborationDetectors.length > 0 ? corroborationDetectors.join(" · ") : "—"}</span>
              </div>
            </div>

            <p className="text-xs text-[var(--muted)] leading-relaxed">
              Multiple analytical detectors observe the same underlying operational deficiency. SENTRA consolidates them within the <strong>{corroborationGroupId}</strong> correlation group instead of penalizing the entity with additive double-counting.
              {corroborationDescription && (
                <span className="block mt-1 text-[var(--subtle)]">{corroborationDescription}</span>
              )}
            </p>

            <div className="pt-1">
              {primaryFindingId ? (
                <button
                  onClick={() => setInspectedFindingId(primaryFindingId)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium border border-[var(--border)] bg-[var(--surface)] hover:bg-[var(--surface-tertiary)] text-[var(--fg)] transition"
                >
                  <FileText className="w-3.5 h-3.5" />
                  <span>Inspect Primary Evidence ({primaryFindingId})</span>
                </button>
              ) : (
                <span className="text-xs font-mono text-[var(--subtle)]">
                  No primary evidence finding available.
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Secondary elevated dimensions if any */}
        {elevatedDimensions.length > 1 && (
          <div className="pt-2 space-y-2 border-t border-[var(--border-subtle)]">
            <span className="text-[11px] font-mono uppercase text-[var(--muted)] tracking-wider block">
              Secondary Operational Drivers
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {elevatedDimensions.slice(1).map((d) => {
                const score = (entity as any)[d.field];
                return (
                  <div
                    key={d.key}
                    className="p-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-secondary)] flex items-center justify-between"
                  >
                    <div>
                      <span className="font-medium text-xs text-[var(--fg)]">{d.key}</span>
                      <span className="text-[11px] text-[var(--muted)] block">{d.description}</span>
                    </div>
                    <span className="font-mono text-sm font-bold tabular-nums text-[var(--fg)]">
                      {score?.toFixed(1)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Six Operational Dimensions Grid */}
      <div className="space-y-4">
        <div>
          <h2 className="text-sm font-semibold tracking-tight text-[var(--fg)]">
            Operational Dimension Profile
          </h2>
          <p className="text-xs text-[var(--muted)]">
            Normalized 0–100 scale across all 6 core supervisory dimensions
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {dimensionConfig.map((dim) => (
            <DimensionCard
              key={dim.key}
              dimension={dim.key}
              score={(entity as any)[dim.field] as number | null}
              weight={dim.weight}
              description={dim.description}
              thresholds={thresholds}
              isSelected={selectedDimension === dim.key}
              onClick={() => setSelectedDimension(selectedDimension === dim.key ? null : dim.key)}
            />
          ))}
        </div>

        {/* Minimal Horizontal Comparison Chart */}
        <div className="p-5 rounded-xl border border-[var(--border)] bg-[var(--surface)] space-y-2">
          <span className="text-[11px] font-mono uppercase text-[var(--muted)] tracking-wider block">
            Dimension Profile Comparison
          </span>
          <RiskDimensionBarChart data={dimensionChartData} thresholds={thresholds} />
        </div>
      </div>

      {/* Risk Contributions (Progressive Disclosure Table) */}
      <div className="space-y-3">
        <div>
          <h2 className="text-sm font-semibold tracking-tight text-[var(--fg)]">
            Risk Contributions & Traceability
          </h2>
          <p className="text-xs text-[var(--muted)]">
            Underlying analytical signals mapped into supervisory dimensions
          </p>
        </div>

        <div className="border border-[var(--border)] rounded-xl overflow-hidden bg-[var(--surface)]">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[var(--surface-secondary)] text-[var(--muted)] font-medium border-b border-[var(--border)]">
                <tr>
                  <th className="px-4 py-2.5 font-mono text-[10px] uppercase">Dimension</th>
                  <th className="px-4 py-2.5 font-mono text-[10px] uppercase">Signal / Detector</th>
                  <th className="px-4 py-2.5 font-mono text-[10px] uppercase">Phase</th>
                  <th className="px-4 py-2.5 font-mono text-[10px] uppercase text-right">Raw</th>
                  <th className="px-4 py-2.5 font-mono text-[10px] uppercase text-right">Normalized</th>
                  <th className="px-4 py-2.5 font-mono text-[10px] uppercase text-right">Contribution</th>
                  <th className="px-4 py-2.5 font-mono text-[10px] uppercase">Evidence</th>
                  <th className="px-4 py-2.5 font-mono text-[10px] uppercase text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-subtle)]">
                {contributions.map((c) => {
                  const isExpanded = expandedRowId === c.id;
                  const findingIds = parseFindingIds(c.supporting_finding_ids);
                  const firstFindingId = findingIds[0];

                  return (
                    <React.Fragment key={c.id}>
                      <tr
                        onClick={() => setExpandedRowId(isExpanded ? null : c.id)}
                        className={`transition-all cursor-pointer ${selectedDimension && selectedDimension !== c.dimension
                          ? "opacity-30 hover:opacity-100 bg-[var(--bg)]"
                          : "hover-subtle"
                          } ${selectedDimension === c.dimension
                            ? "bg-[var(--surface-secondary)] border-l-2 border-l-[var(--fg)]"
                            : ""
                          }`}
                      >
                        <td className="px-4 py-3 font-medium text-[var(--fg)]">
                          {c.dimension}
                        </td>
                        <td className="px-4 py-3">
                          <div className="font-mono text-[11px] text-[var(--fg)] font-medium">
                            {c.signal_name}
                          </div>
                          <div className="text-[10px] text-[var(--muted)] mt-0.5">
                            <DetectorTypeBadge detectorId={c.detector_id} />
                          </div>
                        </td>
                        <td className="px-4 py-3 font-mono text-[11px] text-[var(--muted)] uppercase">
                          {c.source_phase}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-[11px] text-[var(--muted)] tabular-nums">
                          {typeof c.raw_value === "number" ? c.raw_value.toFixed(2) : c.raw_value || "—"}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-xs text-[var(--fg)] tabular-nums">
                          {c.normalized_value.toFixed(1)}
                        </td>
                        <td className="px-4 py-3 text-right font-mono font-bold text-xs text-[var(--fg)] tabular-nums">
                          {c.contribution.toFixed(2)}
                        </td>
                        <td className="px-4 py-3">
                          <EvidenceStrengthBadge strength={c.evidence_strength} />
                        </td>
                        <td className="px-4 py-3 text-right">
                          {firstFindingId ? (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setInspectedFindingId(firstFindingId);
                              }}
                              className="text-[11px] font-mono text-[var(--fg)] hover:underline"
                            >
                              Inspect &rarr;
                            </button>
                          ) : (
                            <span className="text-[var(--subtle)] text-[11px]">—</span>
                          )}
                        </td>
                      </tr>

                      {/* Progressive Disclosure Drawer */}
                      {isExpanded && (
                        <tr className="bg-[var(--surface-secondary)]">
                          <td colSpan={8} className="px-6 py-4 space-y-2 border-b border-[var(--border)]">
                            <div className="text-xs space-y-1">
                              <span className="font-semibold text-[var(--fg)]">Rationale:</span>
                              <p className="text-[var(--muted)] leading-relaxed">{c.rationale}</p>
                            </div>
                            <div className="flex flex-wrap gap-4 pt-1 text-[11px] font-mono text-[var(--muted)]">
                              <span>Weight: {c.weight.toFixed(2)}</span>
                              <span>Corroboration: {c.corroboration_group}</span>
                              {findingIds.length > 0 && (
                                <span>
                                  Findings: {findingIds.join(", ")}
                                </span>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Slide-Over Finding Inspector Drawer */}
      <FindingDetailDrawer
        findingId={inspectedFindingId}
        onClose={() => setInspectedFindingId(null)}
      />
    </div>
  );
}
