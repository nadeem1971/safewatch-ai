import { useState, useEffect, useCallback } from "react";

// SafeWatch AI - Governance Dashboard
// The HSE manager's oversight screen: the pending review queue, the decision
// workflow (approve / reject / escalate) that closes the human gate, an audit
// trail, and a Model Ops tab. Calls the SafeWatch governance API.
//
// Where the Operations Console is a loud field-intake tool, this is a calm
// desk instrument for oversight: denser, quieter, built for reading a queue and
// making accountable decisions. Same hazard accent, more restraint.

const API_BASE = "http://localhost:8010";

const BAND_COLOR = { low: "#3ba55d", medium: "#e6a817", high: "#e2622b", critical: "#d3324a" };
const ROUTE_LABEL = {
  auto_log: "Auto-logged",
  safety_officer: "Safety Officer",
  hse_manager: "HSE Manager",
  escalation_committee: "Escalation Committee",
};

export default function GovernanceDashboard() {
  const [tab, setTab] = useState("queue");
  const [queue, setQueue] = useState([]);
  const [stats, setStats] = useState(null);
  const [selected, setSelected] = useState(null);
  const [audit, setAudit] = useState([]);
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [q, s] = await Promise.all([
        fetch(`${API_BASE}/incidents`).then((r) => r.json()),
        fetch(`${API_BASE}/stats`).then((r) => r.json()),
      ]);
      setQueue(q);
      setStats(s);
    } catch {
      setError("Cannot reach the SafeWatch API on :8010. Is it running?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 4000); // keep the queue live
    return () => clearInterval(t);
  }, [load]);

  async function openIncident(inc) {
    setSelected(inc);
    setNote("");
    try {
      const a = await fetch(`${API_BASE}/incidents/${inc.id}/audit`).then((r) => r.json());
      setAudit(a);
    } catch {
      setAudit([]);
    }
  }

  async function decide(decision) {
    if (!selected) return;
    try {
      await fetch(`${API_BASE}/incidents/${selected.id}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, reviewer: "hse_manager", note }),
      });
      setSelected(null);
      setNote("");
      await load();
    } catch {
      setError("Failed to record the decision.");
    }
  }

  return (
    <div style={S.page}>
      <style>{CSS}</style>

      <header style={S.header}>
        <div style={S.brandRow}>
          <span style={S.mark} aria-hidden />
          <div>
            <div style={S.brand}>SAFEWATCH<span style={{ color: HAZARD }}>·</span>AI</div>
            <div style={S.sub}>Governance Dashboard — HSE Oversight</div>
          </div>
        </div>
        <nav style={S.tabs}>
          {["queue", "overview", "modelops"].map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              style={{ ...S.tab, ...(tab === t ? S.tabActive : {}) }}
            >
              {t === "queue" ? "Review queue" : t === "overview" ? "Overview" : "Model Ops"}
              {t === "queue" && queue.length > 0 && <span style={S.badge}>{queue.length}</span>}
            </button>
          ))}
        </nav>
      </header>

      {error && <div style={S.errorBar}>{error}</div>}

      <main style={S.main}>
        {tab === "queue" && (
          <div style={S.queueWrap}>
            <div style={S.queueList}>
              <div style={S.sectionHead}>
                Pending human review
                <span style={S.count}>{queue.length}</span>
              </div>

              {loading && <div style={S.muted}>Loading queue…</div>}
              {!loading && queue.length === 0 && (
                <div style={S.emptyQueue}>
                  <div style={S.emptyMark}>✓</div>
                  <div style={S.emptyTitle}>Queue clear</div>
                  <div style={S.emptySub}>No incidents awaiting review.</div>
                </div>
              )}

              {queue.map((inc) => (
                <button
                  key={inc.id}
                  onClick={() => openIncident(inc)}
                  style={{
                    ...S.queueItem,
                    ...(selected?.id === inc.id ? S.queueItemActive : {}),
                    borderLeftColor: BAND_COLOR[inc.risk_band] ?? "#666",
                  }}
                >
                  <div style={S.qiTop}>
                    <span style={{ ...S.qiScore, color: BAND_COLOR[inc.risk_band] }}>
                      {inc.risk_score}
                    </span>
                    <span style={S.qiRoute}>{ROUTE_LABEL[inc.route] ?? inc.route}</span>
                  </div>
                  <div style={S.qiViolation}>
                    {inc.reviewer_packet?.detections?.[0]?.violation_type?.replace(/_/g, " ") ??
                      "no violation"}
                  </div>
                  {inc.hard_overrides?.length > 0 && (
                    <div style={S.qiOverride}>⚠ {inc.hard_overrides.join(", ").replace(/_/g, " ")}</div>
                  )}
                </button>
              ))}
            </div>

            <div style={S.detail}>
              {!selected && (
                <div style={S.detailEmpty}>
                  <div style={S.emptyMark}>◧</div>
                  <div style={S.emptyTitle}>Select an incident</div>
                  <div style={S.emptySub}>Review the packet, then decide.</div>
                </div>
              )}

              {selected && (
                <IncidentDetail
                  inc={selected}
                  audit={audit}
                  note={note}
                  setNote={setNote}
                  onDecide={decide}
                />
              )}
            </div>
          </div>
        )}

        {tab === "overview" && <Overview stats={stats} />}
        {tab === "modelops" && <ModelOps />}
      </main>

      <footer style={S.footer}>
        The LLM proposes · deterministic policy disposes · <b style={{ color: HAZARD }}>a human approves</b>
      </footer>
    </div>
  );
}

function IncidentDetail({ inc, audit, note, setNote, onDecide }) {
  const p = inc.reviewer_packet;
  return (
    <div style={S.detailInner}>
      <div style={S.detailHead}>
        <div>
          <div style={S.detailScore} data-band={inc.risk_band}>
            {inc.risk_score}<span style={S.detailOf}>/100</span>
          </div>
          <div style={{ ...S.bandTag, background: BAND_COLOR[inc.risk_band] }}>{inc.risk_band}</div>
        </div>
        <div style={S.detailRoute}>
          <div style={S.detailRouteLabel}>Routed to</div>
          <div style={S.detailRouteVal}>{ROUTE_LABEL[inc.route] ?? inc.route}</div>
        </div>
      </div>

      <div style={S.block}>
        <div style={S.blockLabel}>Rationale</div>
        <div style={S.blockText}>{p?.risk_rationale}</div>
      </div>

      {inc.hard_overrides?.length > 0 && (
        <div style={S.block}>
          <div style={S.blockLabel}>Hard overrides</div>
          <div style={S.overrideRow}>
            {inc.hard_overrides.map((o) => (
              <span key={o} style={S.overrideChip}>{o.replace(/_/g, " ")}</span>
            ))}
          </div>
        </div>
      )}

      {p?.citations?.length > 0 && (
        <div style={S.block}>
          <div style={S.blockLabel}>Cited regulation</div>
          {p.citations.map((c, i) => (
            <div key={i} style={S.cite}>
              <div style={S.citeReg}>{c.regulation} · {c.clause}</div>
              <div style={S.citeText}>{c.text}</div>
            </div>
          ))}
        </div>
      )}

      {audit.length > 0 && (
        <div style={S.block}>
          <div style={S.blockLabel}>Audit trail</div>
          {audit.map((a) => (
            <div key={a.id} style={S.auditRow}>
              <span style={S.auditDecision}>{a.decision}</span>
              <span style={S.auditMeta}>{a.reviewer} · {a.note || "no note"}</span>
            </div>
          ))}
        </div>
      )}

      <div style={S.decisionZone}>
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Decision note (recorded to audit trail)…"
          style={S.noteInput}
        />
        <div style={S.decisionBtns}>
          <button style={{ ...S.decBtn, ...S.approve }} onClick={() => onDecide("approved")}>
            Approve
          </button>
          <button style={{ ...S.decBtn, ...S.escalate }} onClick={() => onDecide("escalated")}>
            Escalate
          </button>
          <button style={{ ...S.decBtn, ...S.reject }} onClick={() => onDecide("rejected")}>
            Reject
          </button>
        </div>
        <div style={S.policyNote}>Decision recorded against policy {inc.policy_version}</div>
      </div>
    </div>
  );
}

function Overview({ stats }) {
  if (!stats) return <div style={S.muted}>Loading…</div>;
  const bands = ["low", "medium", "high", "critical"];
  return (
    <div style={S.overview}>
      <div style={S.statRow}>
        <Stat label="Total incidents" value={stats.total} />
        <Stat label="Pending review" value={stats.pending_review} accent={HAZARD} />
      </div>
      <div style={S.block}>
        <div style={S.blockLabel}>Risk distribution</div>
        {bands.map((b) => (
          <div key={b} style={S.distRow}>
            <span style={S.distLabel}>{b}</span>
            <div style={S.distTrack}>
              <div
                style={{
                  ...S.distFill,
                  width: `${stats.total ? ((stats.by_band[b] ?? 0) / stats.total) * 100 : 0}%`,
                  background: BAND_COLOR[b],
                }}
              />
            </div>
            <span style={S.distCount}>{stats.by_band[b] ?? 0}</span>
          </div>
        ))}
      </div>
      <div style={S.block}>
        <div style={S.blockLabel}>By status</div>
        <div style={S.statusRow}>
          {Object.entries(stats.by_status).map(([k, v]) => (
            <div key={k} style={S.statusChip}>
              <span style={S.statusVal}>{v}</span>
              <span style={S.statusKey}>{k.replace(/_/g, " ")}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ModelOps() {
  // Honest placeholder: the model registry / eval-gate / drift monitoring are a
  // designed Phase-2 capability (see the MLOps issue). This tab states what the
  // production system tracks, rather than faking live metrics.
  const rows = [
    ["Vision PPE model", "stub-vision-v0", "placeholder", "Issues #5/#6"],
    ["Document extraction", "stub-document-v0", "placeholder", "Issue #7"],
    ["Compliance embeddings", "text-embedding-3-large", "live", "In-region"],
    ["Governance policy", "2.0.0", "live", "Deterministic"],
  ];
  return (
    <div style={S.overview}>
      <div style={S.modelNote}>
        Model Ops surfaces the version and status of every model and policy in the pipeline.
        In v1 the vision and document models are labelled placeholders; the registry, evaluation
        gates, and drift monitoring are a designed Phase-2 capability.
      </div>
      <div style={S.block}>
        <div style={S.blockLabel}>Pipeline components</div>
        <table style={S.table}>
          <thead>
            <tr>
              <th style={S.th}>Component</th>
              <th style={S.th}>Version</th>
              <th style={S.th}>Status</th>
              <th style={S.th}>Note</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([c, v, s, n]) => (
              <tr key={c}>
                <td style={S.td}>{c}</td>
                <td style={{ ...S.td, fontFamily: "monospace", fontSize: 12 }}>{v}</td>
                <td style={S.td}>
                  <span style={{ ...S.statusDot, background: s === "live" ? BAND_COLOR.low : "#8b8f88" }} />
                  {s}
                </td>
                <td style={{ ...S.td, color: "#8b8f88" }}>{n}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Stat({ label, value, accent }) {
  return (
    <div style={S.statCard}>
      <div style={{ ...S.statNum, color: accent ?? INK }}>{value}</div>
      <div style={S.statLabel}>{label}</div>
    </div>
  );
}

const HAZARD = "#d4e34a";
const INK = "#e9ebe4";

const CSS = `
  * { box-sizing: border-box; }
  @media (max-width: 860px) {
    .qwrap { grid-template-columns: 1fr !important; }
  }
`;

const S = {
  page: { minHeight: "100vh", background: "#141517", color: INK, fontFamily: "'Inter', system-ui, sans-serif" },
  header: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "18px 28px", borderBottom: "1px solid #26282c", background: "#0f1012", flexWrap: "wrap", gap: 12,
  },
  brandRow: { display: "flex", alignItems: "center", gap: 14 },
  mark: { width: 24, height: 24, background: `repeating-linear-gradient(45deg, ${HAZARD} 0 5px, #141517 5px 10px)`, borderRadius: 4 },
  brand: { fontWeight: 800, fontSize: 19, letterSpacing: "0.06em" },
  sub: { fontSize: 12, color: "#8b8f88", marginTop: 2 },
  tabs: { display: "flex", gap: 4 },
  tab: {
    position: "relative", padding: "9px 16px", background: "none", border: "1px solid transparent",
    borderRadius: 6, color: "#8b8f88", fontSize: 13.5, fontWeight: 600, cursor: "pointer",
  },
  tabActive: { background: "#1a1c1f", border: "1px solid #26282c", color: INK },
  badge: {
    marginLeft: 8, background: HAZARD, color: "#141517", fontSize: 11, fontWeight: 700,
    padding: "1px 7px", borderRadius: 10,
  },
  errorBar: { background: "#2a1116", borderBottom: `1px solid ${BAND_COLOR.critical}`, color: "#f0a5b2", padding: "10px 28px", fontSize: 13 },
  main: { maxWidth: 1200, margin: "0 auto", padding: 24 },
  queueWrap: { display: "grid", gridTemplateColumns: "380px 1fr", gap: 20, className: "qwrap" },
  queueList: { display: "flex", flexDirection: "column", gap: 8 },
  sectionHead: { display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", color: "#8b8f88", marginBottom: 6 },
  count: { background: "#26282c", color: INK, padding: "2px 10px", borderRadius: 10, fontSize: 12 },
  muted: { color: "#8b8f88", fontSize: 14, padding: 20 },
  emptyQueue: { textAlign: "center", padding: "50px 20px", background: "#1a1c1f", border: "1px solid #26282c", borderRadius: 8 },
  emptyMark: { fontSize: 36, color: BAND_COLOR.low, marginBottom: 10 },
  emptyTitle: { fontWeight: 700, fontSize: 15 },
  emptySub: { fontSize: 12.5, color: "#8b8f88", marginTop: 4 },
  queueItem: {
    textAlign: "left", background: "#1a1c1f", border: "1px solid #26282c", borderLeft: "3px solid",
    borderRadius: 8, padding: "12px 14px", cursor: "pointer", color: INK, width: "100%",
  },
  queueItemActive: { background: "#20242a", borderColor: "#3a3d42" },
  qiTop: { display: "flex", alignItems: "baseline", gap: 10, marginBottom: 4 },
  qiScore: { fontSize: 22, fontWeight: 800, fontVariantNumeric: "tabular-nums" },
  qiRoute: { fontSize: 12, color: "#8b8f88" },
  qiViolation: { fontSize: 14, fontWeight: 600, textTransform: "capitalize" },
  qiOverride: { fontSize: 11.5, color: BAND_COLOR.critical, marginTop: 4 },
  detail: { background: "#1a1c1f", border: "1px solid #26282c", borderRadius: 8, minHeight: 400 },
  detailEmpty: { display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: 400, textAlign: "center" },
  detailInner: { padding: 24 },
  detailHead: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 },
  detailScore: { fontSize: 48, fontWeight: 800, lineHeight: 1, fontVariantNumeric: "tabular-nums" },
  detailOf: { fontSize: 18, color: "#8b8f88", fontWeight: 400 },
  bandTag: { display: "inline-block", marginTop: 8, fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "#141517", padding: "4px 12px", borderRadius: 4 },
  detailRoute: { textAlign: "right" },
  detailRouteLabel: { fontSize: 11, color: "#8b8f88", letterSpacing: "0.1em", textTransform: "uppercase" },
  detailRouteVal: { fontSize: 16, fontWeight: 700, marginTop: 4 },
  block: { marginBottom: 18 },
  blockLabel: { fontSize: 11, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: "#8b8f88", marginBottom: 8 },
  blockText: { fontSize: 13, lineHeight: 1.55, color: "#b8bcb2", background: "#141517", padding: "12px 14px", borderRadius: 6 },
  overrideRow: { display: "flex", gap: 8, flexWrap: "wrap" },
  overrideChip: { fontSize: 12, padding: "4px 10px", background: "#2a1116", border: `1px solid ${BAND_COLOR.critical}`, borderRadius: 4, color: "#f0a5b2" },
  cite: { padding: "12px 14px", background: "#141517", borderRadius: 6, borderLeft: `3px solid ${HAZARD}`, marginBottom: 8 },
  citeReg: { fontWeight: 700, fontSize: 13.5, color: HAZARD },
  citeText: { fontSize: 12.5, lineHeight: 1.5, color: "#b8bcb2", marginTop: 4 },
  auditRow: { display: "flex", gap: 10, alignItems: "baseline", padding: "8px 0", borderTop: "1px solid #26282c" },
  auditDecision: { fontSize: 12, fontWeight: 700, textTransform: "uppercase", color: HAZARD },
  auditMeta: { fontSize: 12.5, color: "#8b8f88" },
  decisionZone: { marginTop: 22, paddingTop: 18, borderTop: "1px solid #26282c" },
  noteInput: { width: "100%", padding: "11px 14px", background: "#141517", border: "1px solid #3a3d42", borderRadius: 6, color: INK, fontSize: 13.5, marginBottom: 12 },
  decisionBtns: { display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 },
  decBtn: { padding: "12px", border: "none", borderRadius: 6, fontWeight: 700, fontSize: 13.5, cursor: "pointer" },
  approve: { background: BAND_COLOR.low, color: "#fff" },
  escalate: { background: BAND_COLOR.high, color: "#fff" },
  reject: { background: "#3a3d42", color: INK },
  policyNote: { fontSize: 11, color: "#8b8f88", fontFamily: "monospace", marginTop: 10, textAlign: "center" },
  overview: { maxWidth: 720 },
  statRow: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20 },
  statCard: { background: "#1a1c1f", border: "1px solid #26282c", borderRadius: 8, padding: 20 },
  statNum: { fontSize: 40, fontWeight: 800, lineHeight: 1 },
  statLabel: { fontSize: 12.5, color: "#8b8f88", marginTop: 6 },
  distRow: { display: "flex", alignItems: "center", gap: 12, marginBottom: 10 },
  distLabel: { fontSize: 12.5, width: 70, textTransform: "capitalize", color: "#b8bcb2" },
  distTrack: { flex: 1, height: 10, background: "#26282c", borderRadius: 5, overflow: "hidden" },
  distFill: { height: "100%", borderRadius: 5, transition: "width .4s" },
  distCount: { fontSize: 13, fontWeight: 600, width: 24, textAlign: "right", fontVariantNumeric: "tabular-nums" },
  statusRow: { display: "flex", gap: 12, flexWrap: "wrap" },
  statusChip: { background: "#141517", border: "1px solid #26282c", borderRadius: 6, padding: "10px 16px", textAlign: "center" },
  statusVal: { display: "block", fontSize: 22, fontWeight: 800 },
  statusKey: { fontSize: 11.5, color: "#8b8f88", textTransform: "capitalize" },
  modelNote: { fontSize: 13, lineHeight: 1.55, color: "#b8bcb2", background: "#1a1c1f", border: "1px solid #26282c", borderLeft: `3px solid ${HAZARD}`, borderRadius: 6, padding: "14px 16px", marginBottom: 20 },
  table: { width: "100%", borderCollapse: "collapse" },
  th: { textAlign: "left", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "#8b8f88", padding: "8px 10px", borderBottom: "1px solid #26282c" },
  td: { fontSize: 13.5, padding: "12px 10px", borderBottom: "1px solid #1f2124" },
  statusDot: { display: "inline-block", width: 8, height: 8, borderRadius: "50%", marginRight: 7 },
  footer: { textAlign: "center", padding: 20, fontSize: 12, color: "#6a6e67", letterSpacing: "0.03em", fontStyle: "italic" },
};
