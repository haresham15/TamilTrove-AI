"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient, isAbortError, isNetworkError } from "../lib/api-client";
import type { DataQualityReport } from "../types/api";
import { DEMO_MOVIES } from "../lib/demo-data";
import { useApp } from "./app-provider";
import { Icon } from "./icons";

function demoReport(): DataQualityReport {
  return {
    datasetVersion: "demo-catalog-v2",
    generatedAt: new Date().toISOString(),
    sourceRecords: DEMO_MOVIES.length,
    acceptedRecords: DEMO_MOVIES.length,
    invalidRecords: [],
    duplicateIdentities: [],
    needsReview: 0,
    missingPosters: DEMO_MOVIES.filter((movie) => !movie.posterUrl).length,
    shortOverviews: DEMO_MOVIES.filter((movie) => movie.overview.length < 80)
      .length,
    embeddingErrors: [],
    qualityDistribution: {
      validated: DEMO_MOVIES.length,
      needsReview: 0,
      quarantined: 0,
    },
    semanticBackend: "on-device lexical preview",
    degradedReasons: [
      "Live admin API is unreachable; showing the bundled preview catalog.",
    ],
  };
}

export function DataQualityPage() {
  const { profile, token } = useApp();
  const [report, setReport] = useState<DataQualityReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const load = useCallback(async () => {
    controller.current?.abort();
    controller.current = new AbortController();
    setLoading(true);
    setError(null);
    try {
      setReport(await apiClient.dataQuality(token, controller.current.signal));
    } catch (loadError) {
      if (isAbortError(loadError)) return;
      if (isNetworkError(loadError)) setReport(demoReport());
      else
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Unable to load data quality report.",
        );
    } finally {
      setLoading(false);
    }
  }, [token]);
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => {
      window.clearTimeout(timer);
      controller.current?.abort();
    };
  }, [load]);

  if (!profile?.isAdmin)
    return (
      <div className="page-shell narrow-page">
        <section className="state-panel error-panel">
          <Icon name="shield" width={38} height={38} />
          <h1>Admin access required</h1>
          <p>
            Data-quality details can expose ingestion internals and are
            restricted to authorized administrators.
          </p>
          <div className="state-actions">
            <Link className="button button-primary" href="/auth">
              Sign in with admin access
            </Link>
            <Link className="button button-secondary" href="/">
              Return home
            </Link>
          </div>
        </section>
      </div>
    );
  if (loading)
    return (
      <div className="page-shell">
        <div className="state-panel">
          <span className="spinner dark" />
          <h1>Validating catalog health</h1>
        </div>
      </div>
    );
  if (error || !report)
    return (
      <div className="page-shell">
        <section className="state-panel error-panel" role="alert">
          <Icon name="retry" width={36} height={36} />
          <h1>Report unavailable</h1>
          <p>{error}</p>
          <button className="button button-primary" onClick={() => void load()}>
            Retry
          </button>
        </section>
      </div>
    );
  const acceptanceRate = report.sourceRecords
    ? Math.round((report.acceptedRecords / report.sourceRecords) * 1000) / 10
    : 0;
  return (
    <div className="page-shell admin-page">
      <header className="page-hero split-hero">
        <div>
          <span className="eyebrow">
            <Icon name="shield" width={16} height={16} /> Restricted operations
            view
          </span>
          <h1>Catalog data quality</h1>
          <p>
            Validation, quarantine, identity, provenance, and embedding health
            for the active dataset.
          </p>
        </div>
        <button className="button button-secondary" onClick={() => void load()}>
          <Icon name="retry" width={17} height={17} />
          Refresh
        </button>
      </header>
      {report.degradedReasons.length > 0 && (
        <div className="inline-notice warning">
          <Icon name="info" width={18} height={18} />
          <div>
            <strong>Degraded view</strong>
            {report.degradedReasons.map((reason) => (
              <p key={reason}>{reason}</p>
            ))}
          </div>
        </div>
      )}
      <section className="quality-stats" aria-label="Catalog quality summary">
        <article>
          <span>Acceptance</span>
          <strong>{acceptanceRate}%</strong>
          <small>
            {report.acceptedRecords} of {report.sourceRecords} records
          </small>
        </article>
        <article>
          <span>Needs review</span>
          <strong>{report.needsReview}</strong>
          <small>Records below validation threshold</small>
        </article>
        <article>
          <span>Quarantined</span>
          <strong>{report.qualityDistribution.quarantined}</strong>
          <small>Blocked from canonical catalog</small>
        </article>
        <article>
          <span>Missing posters</span>
          <strong>{report.missingPosters}</strong>
          <small>Fallback artwork shown</small>
        </article>
      </section>
      <div className="admin-grid">
        <section className="admin-card">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Validation outcomes</span>
              <h2>Quality distribution</h2>
            </div>
          </div>
          <div className="distribution-bars">
            <div>
              <span>Validated</span>
              <progress
                value={report.qualityDistribution.validated}
                max={Math.max(1, report.sourceRecords)}
              />
              <strong>{report.qualityDistribution.validated}</strong>
            </div>
            <div>
              <span>Needs review</span>
              <progress
                value={report.qualityDistribution.needsReview}
                max={Math.max(1, report.sourceRecords)}
              />
              <strong>{report.qualityDistribution.needsReview}</strong>
            </div>
            <div>
              <span>Quarantined</span>
              <progress
                value={report.qualityDistribution.quarantined}
                max={Math.max(1, report.sourceRecords)}
              />
              <strong>{report.qualityDistribution.quarantined}</strong>
            </div>
          </div>
        </section>
        <section className="admin-card">
          <span className="eyebrow">Active versions</span>
          <h2>Dataset & retrieval</h2>
          <dl className="admin-definition-list">
            <div>
              <dt>Dataset</dt>
              <dd>{report.datasetVersion}</dd>
            </div>
            <div>
              <dt>Generated</dt>
              <dd>
                {report.generatedAt
                  ? new Date(report.generatedAt).toLocaleString()
                  : "Unknown"}
              </dd>
            </div>
            <div>
              <dt>Semantic backend</dt>
              <dd>{report.semanticBackend}</dd>
            </div>
            <div>
              <dt>Embedding failures</dt>
              <dd>{report.embeddingErrors.length}</dd>
            </div>
          </dl>
        </section>
      </div>
      <section className="admin-card issue-table-section">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Action queue</span>
            <h2>Validation issues</h2>
          </div>
          <span>
            {report.invalidRecords.length +
              report.duplicateIdentities.length +
              report.embeddingErrors.length}{" "}
            open
          </span>
        </div>
        {report.invalidRecords.length ||
        report.duplicateIdentities.length ||
        report.embeddingErrors.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Record</th>
                  <th>Reason</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {report.invalidRecords.map((issue) => (
                  <tr key={`invalid-${issue.index}`}>
                    <td>Validation</td>
                    <td>Source row {issue.index}</td>
                    <td>{issue.reason}</td>
                    <td>
                      <span className="status-badge status-error">
                        Quarantined
                      </span>
                    </td>
                  </tr>
                ))}
                {report.duplicateIdentities.map((identity) => (
                  <tr key={identity}>
                    <td>Identity</td>
                    <td>{identity}</td>
                    <td>Potential duplicate canonical identity</td>
                    <td>
                      <span className="status-badge status-warning">
                        Review
                      </span>
                    </td>
                  </tr>
                ))}
                {report.embeddingErrors.map((message) => (
                  <tr key={message}>
                    <td>Embedding</td>
                    <td>Vector job</td>
                    <td>{message}</td>
                    <td>
                      <span className="status-badge status-error">Failed</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="inline-empty success-empty">
            <Icon name="check" width={28} height={28} />
            <div>
              <strong>No open quality issues</strong>
              <p>The active validation run accepted every preview record.</p>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
