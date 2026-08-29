import { useState, useRef } from "react";

// SafeWatch AI - Operations Console
// The screen a site safety officer uses: upload evidence, submit, read the
// governance decision. Calls POST /incidents/upload on the SafeWatch API.
//
// Design language borrows from physical site-safety signage: high-visibility
// hazard yellow against charcoal, heavy condensed verdict type, a decisive
// cleared / needs-review split. This is a tool used on a loud, bright, urgent
// site - not a calm SaaS dashboard.

const API_BASE = "http://localhost:8010";

const ROUTE_LABEL = {
  auto_log: "Auto-logged",
  safety_officer: "Safety Officer review",
  hse_manager: "HSE Manager review",
  escalation_committee: "Escalation Committee",
};

const BAND_COLOR = {
  low: "#3ba55d",
  medium: "#e6a817",
  high: "#e2622b",
  critical: "#d3324a",
};

export default function OperationsConsole() {
  const [file, setFile] = useState(null);
  const [workerCount, setWorkerCount] = useState(1);
  const [elevated, setElevated] = useState(false);
  const [permitValid, setPermitValid] = useState(true);
  const [permitExpired, setPermitExpired] = useState(false);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  async function submit() {
    if (!file) {
      setError("Add a site photo before submitting.");
      return;
    }
    setError(null);
    setLoading(true);
    setResult(null);
    try {
      const form = new FormData();
      form.append("image", file);
      form.append("worker_count", String(workerCount));
      form.append("zone_is_elevated", String(elevated));
      form.append("permit_is_valid", String(permitValid));
      form.append("permit_is_expired", String(permitExpired));
      const res = await fetch(`${API_BASE}/incidents/upload`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error(`Submit failed (${res.status})`);
      setResult(await res.json());
    } catch (e) {
      setError(e.message || "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    setResult(null);
    setFile(null);
    setError(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  const packet = result?.reviewer_packet;

  return (
    <div style={S.page}>
      <style>{KEYFRAMES}</style>

      <header style={S.header}>
        <div style={S.brandRow}>
          <span style={S.hazardMark} aria-hidden />
          <div>
            <div style={S.brand}>SAFEWATCH<span style={{ color: HAZARD }}>·</span>AI</div>
            <div style={S.brandSub}>Operations Console — Site Safety Intake</div>
          </div>
        </div>
        <div style={S.siteTag}>SITE&nbsp;INTAKE</div>
      </header>

      <main style={S.main}>
        {/* ---------------- Intake ---------------- */}
        <section style={S.panel}>
          <div style={S.panelLabel}>01 · Evidence</div>

          <label
            style={{
              ...S.dropzone,
              borderColor: file ? HAZARD : "#3a3d42",
              background: file ? "#20241d" : "#1a1c1f",
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              style={{ display: "none" }}
            />
            {file ? (
              <div style={S.fileChosen}>
                <span style={S.fileTick}>▸</span>
                <span style={S.fileName}>{file.name}</span>
                <span style={S.fileHint}>tap to replace</span>
              </div>
            ) : (
              <div style={S.dropInner}>
                <div style={S.dropIcon}>⬍</div>
                <div style={S.dropText}>Add site photo</div>
                <div style={S.dropSub}>PPE, work-at-height, zone entry</div>
              </div>
            )}
          </label>

          <div style={S.stubNote}>
            Detection is a labelled placeholder in v1 — the vision model reads the
            filename, not the pixels. Name the file with the hazard
            (e.g. <code style={S.code}>missing_harness.jpg</code>) to exercise the pipeline.
          </div>

          <div style={S.panelLabel}>02 · Context</div>

          <div style={S.field}>
            <span style={S.fieldLabel}>Workers exposed</span>
            <div style={S.stepper}>
              <button style={S.stepBtn} onClick={() => setWorkerCount((n) => Math.max(0, n - 1))}>–</button>
              <span style={S.stepVal}>{workerCount}</span>
              <button style={S.stepBtn} onClick={() => setWorkerCount((n) => n + 1)}>+</button>
            </div>
          </div>

          <Toggle label="Work at height / elevated zone" value={elevated} onChange={setElevated} />
          <Toggle label="Permit valid" value={permitValid} onChange={setPermitValid} />
          <Toggle label="Permit expired" value={permitExpired} onChange={setPermitExpired} danger />

          {error && <div style={S.error}>{error}</div>}

          <button style={{ ...S.submit, opacity: loading ? 0.6 : 1 }} onClick={submit} disabled={loading}>
            {loading ? "Assessing…" : "Submit for assessment"}
          </button>
        </section>

        {/* ---------------- Verdict ---------------- */}
        <section style={S.panel}>
          <div style={S.panelLabel}>03 · Governance decision</div>

          {!packet && !loading && (
            <div style={S.empty}>
              <div style={S.emptyMark}>⧗</div>
              <div style={S.emptyText}>No assessment yet.</div>
              <div style={S.emptySub}>Submit evidence to see the routing decision.</div>
            </div>
          )}

          {loading && (
            <div style={S.empty}>
              <div style={{ ...S.emptyMark, animation: "pulse 1.1s ease-in-out infinite" }}>◐</div>
              <div style={S.emptyText}>Running the pipeline…</div>
              <div style={S.emptySub}>vision → document → rag → risk → governance</div>
            </div>
          )}

          {packet && (
            <div style={S.verdict}>
              <div
                style={{
                  ...S.verdictBanner,
                  background: packet.requires_human_approval ? "#2a1116" : "#12241a",
                  borderColor: packet.requires_human_approval ? BAND_COLOR.critical : BAND_COLOR.low,
                }}
              >
                <div style={S.verdictRoute}>
                  {packet.requires_human_approval ? "HUMAN REVIEW REQUIRED" : "CLEARED — AUTO-LOGGED"}
                </div>
                <div style={S.verdictDest}>{ROUTE_LABEL[packet.route] ?? packet.route}</div>
              </div>

              <div style={S.scoreRow}>
                <div style={S.scoreBlock}>
                  <div style={S.scoreNum} data-band={packet.risk_band}>
                    {packet.risk_score}
                  </div>
                  <div style={S.scoreOf}>/ 100</div>
                </div>
                <div
                  style={{
                    ...S.bandPill,
                    background: BAND_COLOR[packet.risk_band] ?? "#666",
                  }}
                >
                  {packet.risk_band}
                </div>
              </div>

              <div style={S.meterTrack}>
                <div
                  style={{
                    ...S.meterFill,
                    width: `${packet.risk_score}%`,
                    background: BAND_COLOR[packet.risk_band] ?? "#666",
                  }}
                />
              </div>

              <div style={S.rationale}>{packet.risk_rationale}</div>

              {packet.hard_overrides?.length > 0 && (
                <div style={S.overrides}>
                  <span style={S.overrideLabel}>Hard overrides</span>
                  {packet.hard_overrides.map((o) => (
                    <span key={o} style={S.overrideChip}>{o.replace(/_/g, " ")}</span>
                  ))}
                </div>
              )}

              {packet.citations?.length > 0 && (
                <div style={S.citations}>
                  <div style={S.citHead}>Cited regulation</div>
                  {packet.citations.map((c, i) => (
                    <div key={i} style={S.citation}>
                      <div style={S.citReg}>{c.regulation} · {c.clause}</div>
                      <div style={S.citText}>{c.text}</div>
                    </div>
                  ))}
                </div>
              )}

              <div style={S.footRow}>
                <span style={S.policyTag}>policy {packet.policy_version}</span>
                <button style={S.resetBtn} onClick={reset}>New assessment</button>
              </div>
            </div>
          )}
        </section>
      </main>

      <footer style={S.footer}>
        The LLM proposes · deterministic policy disposes · a human approves
      </footer>
    </div>
  );
}

function Toggle({ label, value, onChange, danger }) {
  return (
    <button style={S.field} onClick={() => onChange(!value)}>
      <span style={S.fieldLabel}>{label}</span>
      <span
        style={{
          ...S.switch,
          background: value ? (danger ? BAND_COLOR.critical : HAZARD) : "#3a3d42",
        }}
      >
        <span style={{ ...S.knob, transform: value ? "translateX(20px)" : "translateX(0)" }} />
      </span>
    </button>
  );
}

const HAZARD = "#d4e34a"; // hi-vis safety yellow-green
const INK = "#e9ebe4";

const KEYFRAMES = `
  @keyframes pulse { 0%,100% { opacity: .4 } 50% { opacity: 1 } }
  @media (max-width: 820px) { main { grid-template-columns: 1fr !important } }
`;

const S = {
  page: {
    minHeight: "100vh",
    background: "#141517",
    color: INK,
    fontFamily: "'Inter', system-ui, sans-serif",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "20px 28px",
    borderBottom: "1px solid #26282c",
    background: "#0f1012",
  },
  brandRow: { display: "flex", alignItems: "center", gap: 14 },
  hazardMark: {
    width: 26,
    height: 26,
    background: `repeating-linear-gradient(45deg, ${HAZARD} 0 6px, #141517 6px 12px)`,
    borderRadius: 4,
  },
  brand: { fontWeight: 800, fontSize: 20, letterSpacing: "0.06em" },
  brandSub: { fontSize: 12, color: "#8b8f88", marginTop: 2, letterSpacing: "0.02em" },
  siteTag: {
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: "0.18em",
    color: "#141517",
    background: HAZARD,
    padding: "6px 12px",
    borderRadius: 3,
  },
  main: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 20,
    padding: 24,
    maxWidth: 1100,
    margin: "0 auto",
  },
  panel: {
    background: "#1a1c1f",
    border: "1px solid #26282c",
    borderRadius: 8,
    padding: 22,
  },
  panelLabel: {
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: "0.16em",
    color: "#8b8f88",
    textTransform: "uppercase",
    margin: "6px 0 14px",
  },
  dropzone: {
    display: "block",
    border: "2px dashed #3a3d42",
    borderRadius: 8,
    padding: "30px 20px",
    cursor: "pointer",
    textAlign: "center",
    transition: "all .15s",
  },
  dropInner: { display: "flex", flexDirection: "column", alignItems: "center", gap: 6 },
  dropIcon: { fontSize: 28, color: HAZARD },
  dropText: { fontWeight: 600, fontSize: 15 },
  dropSub: { fontSize: 12, color: "#8b8f88" },
  fileChosen: { display: "flex", flexDirection: "column", alignItems: "center", gap: 4 },
  fileTick: { color: HAZARD, fontSize: 20 },
  fileName: { fontWeight: 600, fontSize: 14, wordBreak: "break-all" },
  fileHint: { fontSize: 11, color: "#8b8f88" },
  stubNote: {
    fontSize: 11.5,
    lineHeight: 1.5,
    color: "#8b8f88",
    margin: "10px 2px 22px",
    paddingLeft: 10,
    borderLeft: `2px solid ${HAZARD}`,
  },
  code: { color: HAZARD, fontFamily: "monospace", fontSize: 11 },
  field: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    width: "100%",
    padding: "12px 0",
    background: "none",
    border: "none",
    borderTop: "1px solid #26282c",
    cursor: "pointer",
    color: INK,
    textAlign: "left",
  },
  fieldLabel: { fontSize: 13.5 },
  stepper: { display: "flex", alignItems: "center", gap: 12 },
  stepBtn: {
    width: 28,
    height: 28,
    borderRadius: 4,
    border: "1px solid #3a3d42",
    background: "#26282c",
    color: INK,
    fontSize: 16,
    cursor: "pointer",
  },
  stepVal: { fontSize: 15, fontWeight: 600, minWidth: 20, textAlign: "center" },
  switch: {
    width: 42,
    height: 22,
    borderRadius: 22,
    position: "relative",
    transition: "background .15s",
    flexShrink: 0,
  },
  knob: {
    position: "absolute",
    top: 2,
    left: 2,
    width: 18,
    height: 18,
    borderRadius: "50%",
    background: "#fff",
    transition: "transform .15s",
  },
  error: {
    marginTop: 14,
    padding: "10px 12px",
    background: "#2a1116",
    border: `1px solid ${BAND_COLOR.critical}`,
    borderRadius: 6,
    fontSize: 13,
    color: "#f0a5b2",
  },
  submit: {
    width: "100%",
    marginTop: 18,
    padding: "14px",
    background: HAZARD,
    color: "#141517",
    fontWeight: 700,
    fontSize: 14,
    letterSpacing: "0.03em",
    border: "none",
    borderRadius: 6,
    cursor: "pointer",
  },
  empty: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: "60px 20px",
    textAlign: "center",
  },
  emptyMark: { fontSize: 40, color: "#3a3d42", marginBottom: 12 },
  emptyText: { fontWeight: 600, fontSize: 15 },
  emptySub: { fontSize: 12.5, color: "#8b8f88", marginTop: 4 },
  verdict: { animation: "pulse .3s ease-out" },
  verdictBanner: {
    border: "1px solid",
    borderRadius: 8,
    padding: "16px 18px",
    marginBottom: 18,
  },
  verdictRoute: { fontSize: 12, fontWeight: 700, letterSpacing: "0.12em" },
  verdictDest: { fontSize: 20, fontWeight: 800, marginTop: 4 },
  scoreRow: { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 },
  scoreBlock: { display: "flex", alignItems: "baseline", gap: 8 },
  scoreNum: { fontSize: 52, fontWeight: 800, lineHeight: 1, fontVariantNumeric: "tabular-nums" },
  scoreOf: { fontSize: 16, color: "#8b8f88" },
  bandPill: {
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: "0.1em",
    textTransform: "uppercase",
    color: "#141517",
    padding: "6px 14px",
    borderRadius: 4,
  },
  meterTrack: { height: 8, background: "#26282c", borderRadius: 4, overflow: "hidden", marginBottom: 16 },
  meterFill: { height: "100%", borderRadius: 4, transition: "width .5s ease-out" },
  rationale: {
    fontSize: 13,
    lineHeight: 1.55,
    color: "#b8bcb2",
    padding: "12px 14px",
    background: "#141517",
    borderRadius: 6,
    marginBottom: 14,
  },
  overrides: { display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 14 },
  overrideLabel: { fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", color: BAND_COLOR.critical, textTransform: "uppercase" },
  overrideChip: {
    fontSize: 12,
    padding: "4px 10px",
    background: "#2a1116",
    border: `1px solid ${BAND_COLOR.critical}`,
    borderRadius: 4,
    color: "#f0a5b2",
  },
  citations: { marginBottom: 16 },
  citHead: { fontSize: 11, fontWeight: 700, letterSpacing: "0.14em", color: "#8b8f88", textTransform: "uppercase", marginBottom: 8 },
  citation: { padding: "12px 14px", background: "#141517", borderRadius: 6, borderLeft: `3px solid ${HAZARD}`, marginBottom: 8 },
  citReg: { fontWeight: 700, fontSize: 13.5, color: HAZARD },
  citText: { fontSize: 12.5, lineHeight: 1.5, color: "#b8bcb2", marginTop: 4 },
  footRow: { display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 },
  policyTag: { fontSize: 11, color: "#8b8f88", fontFamily: "monospace" },
  resetBtn: {
    padding: "9px 16px",
    background: "none",
    border: "1px solid #3a3d42",
    borderRadius: 6,
    color: INK,
    fontSize: 13,
    cursor: "pointer",
  },
  footer: {
    textAlign: "center",
    padding: "20px",
    fontSize: 12,
    color: "#6a6e67",
    letterSpacing: "0.04em",
    fontStyle: "italic",
  },
};
