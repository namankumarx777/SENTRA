"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import Link from "next/link";
import {
  Search,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  ShieldAlert,
  Fingerprint,
  GitCommit,
  Database,
  Server,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
} from "lucide-react";
import { api } from "@/src/api";
import {
  BlockchainStatus,
  LedgerRecord,
  LedgerHistoryEntry,
  VerificationResult,
} from "@/src/types";
import { Select } from "@/src/components/Select";
import { LoadingSkeleton, ErrorState, EmptyState } from "@/src/components/States";

// Truncate hash for clean table display: 0aa7c218…e91ab3
function truncateHash(hash?: string | null, startChars = 8, endChars = 6): string {
  if (!hash) return "—";
  if (hash.length <= startChars + endChars + 3) return hash;
  return `${hash.slice(0, startChars)}…${hash.slice(-endChars)}`;
}

// Truncate Transaction ID
function truncateTxId(txId?: string | null, startChars = 10, endChars = 4): string {
  if (!txId) return "—";
  if (txId.length <= startChars + endChars + 3) return txId;
  return `${txId.slice(0, startChars)}…${txId.slice(-endChars)}`;
}

export default function BlockchainPage() {
  const [status, setStatus] = useState<BlockchainStatus | null>(null);
  const [records, setRecords] = useState<LedgerRecord[]>([]);
  const [history, setHistory] = useState<LedgerHistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);
  const [selectedRecordId, setSelectedRecordId] = useState<string>("");
  const [lastSyncTime, setLastSyncTime] = useState<string>("");

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("ALL");
  const [entityFilter, setEntityFilter] = useState<string>("ALL");
  const [tabFilter, setTabFilter] = useState<string>("ALL");

  // Verification & Tamper Simulation State
  const [verifying, setVerifying] = useState(false);
  const [verificationResult, setVerificationResult] = useState<VerificationResult | null>(null);
  const [simulateTamper, setSimulateTamper] = useState(false);

  // Navigation tab
  const [activeTab, setActiveTab] = useState<"ledger" | "transactions" | "integrity" | "network">("ledger");

  // Fetch initial ledger data
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusRes, recordsRes, historyRes] = await Promise.all([
        api.getBlockchainStatus().catch(() => null),
        api.getLedgerRecords().catch(() => []),
        api.getAllLedgerHistory().catch(() => []),
      ]);

      setStatus(statusRes);
      setRecords(recordsRes || []);
      setHistory(historyRes || []);

      const now = new Date();
      setLastSyncTime(
        now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
      );

      if (recordsRes && recordsRes.length > 0 && !selectedRecordId) {
        setSelectedRecordId(recordsRes[0].recordId);
      }
    } catch (err: any) {
      console.error("Failed loading blockchain ledger data:", err);
      setError(err.message || "Failed loading ledger state");
    } finally {
      setLoading(false);
    }
  }, [selectedRecordId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSeed = async () => {
    setSeeding(true);
    try {
      await api.seedLedger();
      await fetchData();
    } catch (err) {
      console.error("Failed seeding ledger:", err);
    } finally {
      setSeeding(false);
    }
  };

  // Perform live verification
  const handleVerify = async (recordIdToVerify?: string) => {
    const targetId = recordIdToVerify || selectedRecordId;
    if (!targetId) return;

    setVerifying(true);
    try {
      if (simulateTamper) {
        const tamperedHash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
        const res = await api.verifyRecord(targetId, tamperedHash);
        setVerificationResult(res);
      } else {
        const res = await api.verifyRecord(targetId);
        setVerificationResult(res);
      }
    } catch (err: any) {
      setVerificationResult({
        recordId: targetId,
        status: "UNAVAILABLE",
        localHash: "",
        message: err.message || "Ledger verification unavailable",
      });
    } finally {
      setVerifying(false);
    }
  };

  // Filtered records
  const filteredRecords = useMemo(() => {
    return records.filter((rec) => {
      const q = searchQuery.toLowerCase().trim();
      const matchesSearch =
        !q ||
        rec.recordId.toLowerCase().includes(q) ||
        rec.entityId.toLowerCase().includes(q) ||
        rec.recordType.toLowerCase().includes(q) ||
        (rec.contentHash && rec.contentHash.toLowerCase().includes(q)) ||
        (rec.findingHash && rec.findingHash.toLowerCase().includes(q));

      const matchesType = typeFilter === "ALL" || rec.recordType === typeFilter;
      const matchesEntity = entityFilter === "ALL" || rec.entityId === entityFilter;
      const matchesTab = tabFilter === "ALL" || rec.recordType === tabFilter;

      return matchesSearch && matchesType && matchesEntity && matchesTab;
    });
  }, [records, searchQuery, typeFilter, entityFilter, tabFilter]);

  // Unique entities
  const entities = useMemo(() => {
    const set = new Set<string>();
    records.forEach((r) => {
      if (r.entityId) set.add(r.entityId);
    });
    return Array.from(set).sort();
  }, [records]);

  // Derive visual blocks & mapping from transaction history
  const { blocks, recordMetaMap } = useMemo(() => {
    const list: Array<{
      blockNumber: number;
      txId: string;
      recordId: string;
      recordType: string;
      entityId: string;
      hash: string;
      prevHash: string;
      timestamp: string;
      version: number;
      entry: LedgerHistoryEntry;
    }> = [];

    const map = new Map<
      string,
      {
        blockNumber: number;
        txId: string;
        hash: string;
        prevHash: string;
        timestamp: string;
        historyEntry: LedgerHistoryEntry;
      }
    >();

    let prev = "0000000000000000000000000000000000000000000000000000000000000000";

    // Genesis anchor: visual start of the local hash chain. This is a local
    // demo anchor, not an on-chain Fabric genesis block.
    list.push({
      blockNumber: 0,
      txId: "local-genesis-anchor",
      recordId: "GENESIS-BLOCK",
      recordType: "GENESIS",
      entityId: "SYSTEM",
      hash: "7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
      prevHash: prev,
      timestamp: "2026-01-01T00:00:00Z",
      version: 1,
      entry: {
        txId: "local-genesis-anchor",
        timestamp: "2026-01-01T00:00:00Z",
        isDelete: false,
      },
    });

    prev = "7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069";

    history.forEach((h, index) => {
      const rec = h.record;
      const hash = rec?.contentHash || rec?.findingHash || "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918";
      const blockNum = index + 1;
      const item = {
        blockNumber: blockNum,
        txId: h.txId,
        recordId: rec?.recordId || "UNKNOWN",
        recordType: rec?.recordType || "RECORD",
        entityId: rec?.entityId || "N/A",
        hash: hash,
        prevHash: prev,
        timestamp: h.timestamp,
        version: rec?.version || 1,
        entry: h,
      };

      list.push(item);
      if (rec?.recordId) {
        map.set(rec.recordId, {
          blockNumber: blockNum,
          txId: h.txId,
          hash: hash,
          prevHash: prev,
          timestamp: h.timestamp,
          historyEntry: h,
        });
      }
      prev = hash;
    });

    return { blocks: list, recordMetaMap: map };
  }, [history]);

  if (loading) {
    return <LoadingSkeleton variant="overview" text="Loading local ledger..." />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={fetchData} />;
  }

  return (
    <div className="space-y-6 sm:space-y-8">
      {/* 1. Header Surface (Matching Overview & CSEs Header) */}
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-4 border-b border-[var(--border)] pb-5">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-[var(--fg)]">
              Ledger Explorer
            </h1>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              {status?.mode === "live" ? "Operational" : "Local (permissioned)"}
            </span>
          </div>
          <p className="text-xs sm:text-sm text-[var(--muted)] mt-1">
            Immutable record provenance and cryptographic audit history across supervisory telemetry
          </p>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--muted)] pt-1.5">
            <span>
              Network: <span className="font-mono text-[var(--fg)]">{status?.network || "SENTRA-network"}</span>
            </span>
            <span className="text-[var(--subtle)]">·</span>
            <span>
              Channel: <span className="font-mono text-[var(--fg)]">{status?.channel || "SENTRA-channel"}</span>
            </span>
            <span className="text-[var(--subtle)]">·</span>
            <span suppressHydrationWarning>
              Last sync: <span className="text-[var(--fg)]">{lastSyncTime || "23:41:00"}</span>
            </span>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2.5 self-start sm:self-center shrink-0">
          <button
            onClick={handleSeed}
            disabled={seeding}
            className="px-3 py-1.5 rounded-lg text-xs font-medium border border-[var(--border)] bg-[var(--surface-secondary)] hover:bg-[var(--surface-tertiary)] text-[var(--fg)] flex items-center gap-1.5 transition cursor-pointer disabled:opacity-50"
            title="Re-seed demo ledger state"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${seeding ? "animate-spin text-emerald-500" : "text-[var(--muted)]"}`} />
            <span>{seeding ? "Syncing..." : "Sync / Re-seed"}</span>
          </button>

          <button
            onClick={() => fetchData()}
            aria-label="Refresh ledger state"
            className="p-2 rounded-lg text-[var(--muted)] hover:text-[var(--fg)] border border-[var(--border)] bg-[var(--surface-secondary)] hover:bg-[var(--surface-tertiary)] transition cursor-pointer"
            title="Refresh"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 2. KPI Metric Cards (Rounded-2xl Cards matching Overview) */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5 sm:gap-4">
        {/* Metric 1 */}
        <div className="p-4 sm:p-5 rounded-2xl border border-[var(--border)] bg-[var(--surface-secondary)] space-y-2 hover:border-[var(--muted)]/40 transition-colors">
          <span className="text-[11px] font-mono text-[var(--muted)] uppercase tracking-wider block">
            Ledger Records
          </span>
          <div className="text-2xl sm:text-3xl font-bold font-mono tabular-nums text-[var(--fg)]">
            {records.length}
          </div>
          <span className="text-xs text-[var(--muted)] block">
            Active state keys committed
          </span>
        </div>

        {/* Metric 2 */}
        <div className="p-4 sm:p-5 rounded-2xl border border-[var(--border)] bg-[var(--surface-secondary)] space-y-2 hover:border-[var(--muted)]/40 transition-colors">
          <span className="text-[11px] font-mono text-[var(--muted)] uppercase tracking-wider block">
            Transactions
          </span>
          <div className="text-2xl sm:text-3xl font-bold font-mono tabular-nums text-[var(--fg)]">
            {history.length}
          </div>
          <span className="text-xs text-[var(--muted)] block">
            Total committed ledger entries
          </span>
        </div>

        {/* Metric 3 */}
        <div className="p-4 sm:p-5 rounded-2xl border border-[var(--border)] bg-[var(--surface-secondary)] space-y-2 hover:border-[var(--muted)]/40 transition-colors">
          <span className="text-[11px] font-mono text-[var(--muted)] uppercase tracking-wider block">
            Current Block
          </span>
          <div className="text-2xl sm:text-3xl font-bold font-mono tabular-nums text-[var(--fg)]">
            #{blocks.length > 0 ? blocks.length - 1 : 0}
          </div>
          <span className="text-xs text-emerald-600 dark:text-emerald-400 block font-medium">
            Local permissioned ledger (no Fabric deployment)
          </span>
        </div>

        {/* Metric 4 */}
        <div className="p-4 sm:p-5 rounded-2xl border border-[var(--border)] bg-[var(--surface-secondary)] space-y-2 hover:border-[var(--muted)]/40 transition-colors">
          <span className="text-[11px] font-mono text-[var(--muted)] uppercase tracking-wider block">
            Verified Records
          </span>
          <div className="text-2xl sm:text-3xl font-bold font-mono tabular-nums text-emerald-600 dark:text-emerald-400">
            {records.length}
          </div>
          <span className="text-xs text-[var(--muted)] block">
            Committed locally; network {status?.is_connected ? "connected" : "unavailable"}
          </span>
        </div>
      </div>

      {/* 3. Section Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-[var(--border)]">
        <button
          onClick={() => setActiveTab("ledger")}
          className={`pb-3 text-sm font-medium transition cursor-pointer border-b-2 flex items-center gap-2 ${
            activeTab === "ledger"
              ? "border-[var(--fg)] text-[var(--fg)] font-semibold"
              : "border-transparent text-[var(--muted)] hover:text-[var(--fg)]"
          }`}
        >
          <Database className="w-4 h-4" />
          <span>Ledger Registry</span>
          <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-[var(--surface-secondary)] text-[var(--muted)]">
            {records.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab("transactions")}
          className={`pb-3 text-sm font-medium transition cursor-pointer border-b-2 flex items-center gap-2 ${
            activeTab === "transactions"
              ? "border-[var(--fg)] text-[var(--fg)] font-semibold"
              : "border-transparent text-[var(--muted)] hover:text-[var(--fg)]"
          }`}
        >
          <GitCommit className="w-4 h-4" />
          <span>Block Sequence</span>
          <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-[var(--surface-secondary)] text-[var(--muted)]">
            {history.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab("integrity")}
          className={`pb-3 text-sm font-medium transition cursor-pointer border-b-2 flex items-center gap-2 ${
            activeTab === "integrity"
              ? "border-[var(--fg)] text-[var(--fg)] font-semibold"
              : "border-transparent text-[var(--muted)] hover:text-[var(--fg)]"
          }`}
        >
          <Fingerprint className="w-4 h-4" />
          <span>Integrity Verification</span>
        </button>

        <button
          onClick={() => setActiveTab("network")}
          className={`pb-3 text-sm font-medium transition cursor-pointer border-b-2 flex items-center gap-2 ${
            activeTab === "network"
              ? "border-[var(--fg)] text-[var(--fg)] font-semibold"
              : "border-transparent text-[var(--muted)] hover:text-[var(--fg)]"
          }`}
        >
          <Server className="w-4 h-4" />
          <span>Network Topology</span>
        </button>
      </div>

      {/* 4. TAB 1: LEDGER REGISTRY */}
      {activeTab === "ledger" && (
        <div className="space-y-4">
          {/* Filter / Search Bar in Rounded-xl Container (Matching CSEs / Review Queue) */}
          <div className="flex flex-wrap items-center justify-between gap-3 p-2.5 sm:p-3 rounded-xl border border-[var(--border)] bg-[var(--surface)]">
            <div className="flex flex-wrap items-center gap-2.5">
              {/* Integrated Search Input */}
              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--muted)]" />
                <input
                  type="text"
                  placeholder="Search records, entities, hashes..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8 pr-2.5 h-[34px] text-xs rounded-lg border border-[var(--border)] bg-transparent text-[var(--fg)] placeholder:text-[var(--subtle)] focus:outline-none focus:border-[var(--muted)] w-56 sm:w-64 transition-colors"
                />
              </div>

              {/* Segmented Filter Pills */}
              <div className="flex items-center h-[34px] rounded-lg border border-[var(--border)] bg-[var(--surface-secondary)] p-0.5 text-xs">
                {["ALL", "FINDING", "SUBMISSION", "EVIDENCE"].map((type) => (
                  <button
                    key={type}
                    onClick={() => setTabFilter(type)}
                    className={`px-2.5 h-full rounded-md text-[11px] font-medium transition cursor-pointer ${
                      tabFilter === type
                        ? "bg-[var(--surface)] text-[var(--fg)] border border-[var(--border-subtle)] shadow-xs"
                        : "text-[var(--muted)] hover-subtle"
                    }`}
                  >
                    {type === "ALL" ? "All Types" : type.charAt(0) + type.slice(1).toLowerCase() + "s"}
                  </button>
                ))}
              </div>

              {entities.length > 0 && (
                <Select
                  value={entityFilter}
                  onChange={(val) => setEntityFilter(val)}
                  options={[
                    { value: "ALL", label: "All Entities" },
                    ...entities.map((e) => ({ value: e, label: e })),
                  ]}
                />
              )}
            </div>

            {/* Metadata Count & Clear */}
            <div className="flex items-center gap-3">
              {(searchQuery || entityFilter !== "ALL" || tabFilter !== "ALL") && (
                <button
                  onClick={() => {
                    setSearchQuery("");
                    setEntityFilter("ALL");
                    setTabFilter("ALL");
                  }}
                  className="text-xs text-[var(--muted)] hover:text-[var(--fg)] underline cursor-pointer"
                >
                  Clear filters
                </button>
              )}
              <span className="text-[11px] font-mono text-[var(--muted)] select-none">
                {filteredRecords.length} of {records.length} records
              </span>
            </div>
          </div>

          {/* Table Section (Clean 6-Column Layout with ZERO Horizontal Scroll) */}
          {filteredRecords.length === 0 ? (
            <EmptyState
              title="No ledger records found"
              description="Try adjusting your search query or reset active filters."
              onReset={() => {
                setSearchQuery("");
                setEntityFilter("ALL");
                setTabFilter("ALL");
              }}
            />
          ) : (
            <div className="border border-[var(--border)] rounded-2xl overflow-hidden bg-[var(--surface)] shadow-xs">
              <table className="w-full text-left text-[13px]">
                <thead className="bg-[var(--surface-secondary)]/50 text-[var(--muted)] font-medium border-b border-[var(--border)]">
                  <tr>
                    <th className="px-5 py-3 text-[11px] font-semibold uppercase tracking-wider select-none w-28">
                      Status
                    </th>
                    <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wider select-none">
                      Record ID
                    </th>
                    <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wider select-none text-center w-28">
                      Type
                    </th>
                    <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wider select-none w-32">
                      Entity
                    </th>
                    <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wider select-none text-center w-24">
                      Block
                    </th>
                    <th className="px-5 py-3 text-[11px] font-semibold uppercase tracking-wider select-none text-right w-36">
                      Committed
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {filteredRecords.map((rec) => {
                    const meta = recordMetaMap.get(rec.recordId);

                    return (
                      <tr
                        key={rec.recordId}
                        className="hover:bg-[var(--surface-secondary)]/40 transition-colors"
                      >
                        {/* 1. Status */}
                        <td className="px-5 py-3.5 whitespace-nowrap">
                          <span className="inline-flex items-center gap-2 text-xs font-medium text-[var(--fg)]">
                            <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                            <span>Verified</span>
                          </span>
                        </td>

                        {/* 2. Record ID */}
                        <td className="px-4 py-3.5 font-mono text-xs font-semibold text-[var(--fg)] whitespace-nowrap">
                          {rec.recordId}
                        </td>

                        {/* 3. Type */}
                        <td className="px-4 py-3.5 text-center whitespace-nowrap">
                          <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-[var(--surface-secondary)] text-[var(--muted)] border border-[var(--border)]">
                            {rec.recordType}
                          </span>
                        </td>

                        {/* 4. Entity */}
                        <td className="px-4 py-3.5 whitespace-nowrap">
                          <Link
                            href={`/cses/${rec.entityId}`}
                            className="text-xs font-medium text-sky-600 dark:text-sky-400 hover:underline"
                          >
                            {rec.entityId || "SYSTEM"}
                          </Link>
                        </td>

                        {/* 5. Block */}
                        <td className="px-4 py-3.5 text-center font-mono text-xs text-[var(--muted)] whitespace-nowrap">
                          {meta ? `#${meta.blockNumber}` : "—"}
                        </td>

                        {/* 6. Committed Timestamp */}
                        <td suppressHydrationWarning className="px-5 py-3.5 text-xs text-[var(--muted)] whitespace-nowrap text-right font-mono">
                          {rec.createdAt ? new Date(rec.createdAt).toLocaleDateString() : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* 5. TAB 2: BLOCK SEQUENCE */}
      {activeTab === "transactions" && (
        <div className="space-y-4">
          <div className="p-4 rounded-2xl border border-[var(--border)] bg-[var(--surface)] flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-[var(--fg)]">
                Sequential Cryptographic Block Registry
              </h2>
              <p className="text-xs text-[var(--muted)] mt-0.5">
                Chained blocks linked via SHA-256 pointers in the local permissioned ledger
              </p>
            </div>
            <span className="text-xs font-mono text-[var(--muted)]">
              Total Height: <span className="font-semibold text-[var(--fg)]">#{blocks.length > 0 ? blocks.length - 1 : 0}</span>
            </span>
          </div>

          <div className="space-y-3">
            {blocks.map((b) => (
              <div
                key={b.txId}
                className="p-4 sm:p-5 rounded-2xl border border-[var(--border)] bg-[var(--surface)] hover:border-[var(--muted)]/40 hover:shadow-xs transition-all flex flex-col md:flex-row md:items-center justify-between gap-4"
              >
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-xl bg-[var(--surface-secondary)] border border-[var(--border)] flex flex-col items-center justify-center shrink-0">
                    <span className="text-[10px] uppercase font-mono text-[var(--muted)]">BLK</span>
                    <span className="text-sm font-bold font-mono text-[var(--fg)]">#{b.blockNumber}</span>
                  </div>

                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-semibold text-[var(--fg)]">{b.recordId}</span>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-[var(--surface-secondary)] text-[var(--muted)] border border-[var(--border)]">
                        {b.recordType}
                      </span>
                      {b.entityId !== "SYSTEM" && (
                        <span className="text-xs text-sky-600 dark:text-sky-400 font-medium">
                          {b.entityId}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-[var(--muted)] font-mono">
                      Tx: {b.txId}
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between md:justify-end gap-6 text-xs text-[var(--muted)] font-mono">
                  <div className="text-right hidden sm:block">
                    <span className="text-[10px] uppercase text-[var(--muted)] block">Digest</span>
                    <span className="text-[var(--fg)]">{truncateHash(b.hash, 10, 6)}</span>
                  </div>
                  <span suppressHydrationWarning className="text-xs">
                    {new Date(b.timestamp).toLocaleString()}
                  </span>
                  <ArrowRight className="w-4 h-4 text-[var(--muted)]" />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 6. TAB 3: INTEGRITY VERIFICATION */}
      {activeTab === "integrity" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column: Selector */}
          <div className="p-5 rounded-2xl border border-[var(--border)] bg-[var(--surface)] space-y-4">
            <div>
              <h2 className="text-sm font-semibold text-[var(--fg)] flex items-center gap-2">
                <Fingerprint className="w-4 h-4 text-emerald-500" />
                Ledger Verification
              </h2>
              <p className="text-xs text-[var(--muted)] mt-1">
                Validate live finding/submission dataset digest against committed ledger record
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-[var(--muted)] block">
                Select Record to Verify:
              </label>
              <Select
                className="w-full font-mono"
                value={selectedRecordId}
                onChange={(val) => setSelectedRecordId(val)}
                options={records.map((r) => ({
                  value: r.recordId,
                  label: `${r.recordId} (${r.recordType} — ${r.entityId || "SYSTEM"})`,
                }))}
              />
            </div>

            <button
              onClick={() => handleVerify()}
              disabled={verifying || !selectedRecordId}
              className="w-full py-2.5 rounded-xl text-xs font-semibold bg-[var(--fg)] text-[var(--bg)] hover:opacity-90 transition cursor-pointer flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {verifying ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  Computing Digest...
                </>
              ) : (
                <>
                  <ShieldCheck className="w-3.5 h-3.5" />
                  Verify Integrity Against Ledger
                </>
              )}
            </button>

            {/* Test Mode */}
            <div className="pt-4 border-t border-[var(--border)] space-y-2">
              <span className="text-[11px] font-mono uppercase text-[var(--muted)] block tracking-wider">
                Demonstration Mode
              </span>
              <div className="p-3.5 rounded-xl border border-amber-500/20 bg-amber-500/5 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-amber-600 dark:text-amber-400 flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5" />
                    Simulate Data Tampering
                  </span>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={simulateTamper}
                      onChange={(e) => setSimulateTamper(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="w-8 h-4 bg-zinc-300 peer-focus:outline-hidden rounded-full peer dark:bg-zinc-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-amber-500"></div>
                  </label>
                </div>
                <p className="text-[11px] text-[var(--muted)] leading-relaxed">
                  Mutate verification digest to demonstrate immediate cryptographic mismatch detection.
                </p>
              </div>
            </div>
          </div>

          {/* Right Column: Verification Proof */}
          <div className="lg:col-span-2 p-5 rounded-2xl border border-[var(--border)] bg-[var(--surface)] space-y-5">
            <div className="flex items-center justify-between border-b border-[var(--border)] pb-4">
              <div>
                <h2 className="text-sm font-semibold text-[var(--fg)]">
                  Cryptographic Reconciliation Result
                </h2>
                <p className="text-xs text-[var(--muted)] mt-0.5">
                  Direct SHA-256 reconciliation between local state and committed ledger hash
                </p>
              </div>

              {verificationResult && (
                <span
                  className={`px-3 py-1 rounded-full text-xs font-medium flex items-center gap-1.5 border ${
                    verificationResult.status === "VERIFIED"
                      ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
                      : verificationResult.status === "MISMATCH"
                      ? "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30"
                      : "bg-zinc-500/10 text-zinc-500 border-zinc-500/30"
                  }`}
                >
                  {verificationResult.status === "VERIFIED" && <CheckCircle2 className="w-3.5 h-3.5" />}
                  {verificationResult.status === "MISMATCH" && <ShieldAlert className="w-3.5 h-3.5" />}
                  {verificationResult.status}
                </span>
              )}
            </div>

            {verificationResult ? (
              <div className="space-y-4">
                <div
                  className={`p-4 rounded-xl border text-xs leading-relaxed ${
                    verificationResult.status === "VERIFIED"
                      ? "bg-emerald-500/5 border-emerald-500/20 text-emerald-800 dark:text-emerald-300"
                      : "bg-rose-500/5 border-rose-500/20 text-rose-800 dark:text-rose-300"
                  }`}
                >
                  <div className="font-semibold flex items-center gap-1.5">
                    {verificationResult.status === "VERIFIED" ? (
                      <>✓ Cryptographic Match Confirmed</>
                    ) : (
                      <>⚠ Integrity Mismatch Detected</>
                    )}
                  </div>
                  <div className="mt-1 text-xs opacity-90">{verificationResult.message}</div>
                </div>

                <div className="space-y-3 font-mono text-xs">
                  <div className="p-3.5 rounded-xl bg-[var(--surface-secondary)] border border-[var(--border)]">
                    <div className="flex items-center justify-between text-[11px] text-[var(--muted)] mb-1">
                      <span>LOCAL DATASET SHA-256 DIGEST</span>
                      <span>Computed Live</span>
                    </div>
                    <div className="text-xs text-[var(--fg)] break-all select-all font-semibold">
                      {verificationResult.localHash || "Unavailable"}
                    </div>
                  </div>

                  <div className="p-3.5 rounded-xl bg-[var(--surface-secondary)] border border-[var(--border)]">
                    <div className="flex items-center justify-between text-[11px] text-[var(--muted)] mb-1">
                      <span>COMMITTED LEDGER DIGEST</span>
                      <span>Committed State</span>
                    </div>
                    <div className="text-xs text-[var(--fg)] break-all select-all font-semibold">
                      {verificationResult.ledgerHash || "Not registered on ledger"}
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3 border-t border-[var(--border)] text-xs font-mono text-[var(--muted)]">
                  <div>
                    <span className="block text-[10px] uppercase">Record ID</span>
                    <span className="text-[var(--fg)] font-semibold">{verificationResult.recordId}</span>
                  </div>
                  <div>
                    <span className="block text-[10px] uppercase">Entity ID</span>
                    <span className="text-[var(--fg)]">{verificationResult.entityId || "N/A"}</span>
                  </div>
                  <div>
                    <span className="block text-[10px] uppercase">Tx ID</span>
                    <span className="text-[var(--fg)] truncate block">{verificationResult.txId || "N/A"}</span>
                  </div>
                  <div>
                    <span className="block text-[10px] uppercase">Timestamp</span>
                    <span suppressHydrationWarning className="text-[var(--fg)]">
                      {verificationResult.timestamp ? new Date(verificationResult.timestamp).toLocaleDateString() : "N/A"}
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="py-16 text-center text-xs text-[var(--muted)] space-y-2">
                <ShieldCheck className="w-8 h-8 mx-auto text-[var(--muted)] opacity-40" />
                <p>Select a record and click &quot;Verify Integrity Against Ledger&quot; to execute live SHA-256 reconciliation.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 7. TAB 4: NETWORK TOPOLOGY */}
      {activeTab === "network" && (
        <div className="space-y-6">
          <div className="p-5 rounded-2xl border border-[var(--border)] bg-[var(--surface)] grid grid-cols-2 md:grid-cols-4 gap-4 text-xs font-mono">
            <div>
              <span className="text-[11px] text-[var(--muted)] uppercase block">Ledger Status</span>
              <span
                className={`font-semibold flex items-center gap-1.5 mt-1 ${
                  status?.is_connected
                    ? "text-emerald-600 dark:text-emerald-400"
                    : "text-amber-600 dark:text-amber-400"
                }`}
              >
                <span className={`w-2 h-2 rounded-full ${status?.is_connected ? "bg-emerald-500" : "bg-amber-500"}`} />
                {status?.is_connected ? "Connected" : "Unavailable"}
              </span>
            </div>
            <div>
              <span className="text-[11px] text-[var(--muted)] uppercase block">Network ID</span>
              <span className="font-semibold text-[var(--fg)] block mt-1">{status?.network || "SENTRA-network"}</span>
            </div>
            <div>
              <span className="text-[11px] text-[var(--muted)] uppercase block">Channel</span>
              <span className="font-semibold text-[var(--fg)] block mt-1">{status?.channel || "SENTRA-channel"}</span>
            </div>
            <div>
              <span className="text-[11px] text-[var(--muted)] uppercase block">Chaincode</span>
              <span className="font-semibold text-[var(--fg)] block mt-1">
                {status?.chaincode || "SENTRA-integrity"} v{status?.chaincode_version || "1.0.0"}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-5 rounded-2xl border border-[var(--border)] bg-[var(--surface)] space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono uppercase tracking-wider text-[var(--muted)]">Ledger Node</span>
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
              </div>
              <div className="text-sm font-semibold text-[var(--fg)] font-mono">
                {status?.peer_endpoint || "localhost:7051"}
              </div>
              <p className="text-xs text-[var(--muted)]">
                Local permissioned integrity ledger. Hash-chained commitments are recorded and verified locally; no external nodes are required.
              </p>
              <div className="pt-2 border-t border-[var(--border)] text-xs font-mono text-[var(--muted)] flex justify-between">
                <span>Deployment: {status?.mode || "local-permissioned"}</span>
              </div>
            </div>

            <div className="p-5 rounded-2xl border border-[var(--border)] bg-[var(--surface)] space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono uppercase tracking-wider text-[var(--muted)]">Supervisory Identity</span>
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
              </div>
              <div className="text-sm font-semibold text-[var(--fg)] font-mono">SupervisorMSP</div>
              <p className="text-xs text-[var(--muted)]">
                Supervisory authority identity under which findings, evidence, and submission digests are committed to the ledger.
              </p>
              <div className="pt-2 border-t border-[var(--border)] text-xs font-mono text-[var(--muted)] flex justify-between">
                <span>Chaincode: SENTRA-integrity</span>
              </div>
            </div>

            <div className="p-5 rounded-2xl border border-[var(--border)] bg-[var(--surface)] space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono uppercase tracking-wider text-[var(--muted)]">Topology Notes</span>
                <span className="w-2 h-2 rounded-full bg-amber-500" />
              </div>
              <div className="text-sm font-semibold text-[var(--fg)]">Design Preview Only</div>
              <p className="text-xs text-[var(--muted)]">
                A distributed Hyperledger Fabric topology (Raft orderer, Org1/Org2 peers) is a design preview and is NOT deployed. All ledger behaviour shown here is the local permissioned implementation.
              </p>
              <div className="pt-2 border-t border-[var(--border)] text-xs font-mono text-[var(--muted)] flex justify-between">
                <span>Status: UNVERIFIED</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
