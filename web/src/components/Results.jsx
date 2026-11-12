import React, { useState } from "react";
import { useT } from "../i18n.js";

// Interactive bar charts of the final gate numbers. Every bar shows its value, n and the
// baseline; hovering or focusing a bar shows the full detail.

const COLORS = ["#8A94A6", "#5B5BD6", "#2F9E6E"];

function fmt(chart, row, i, lang) {
  if (lang === "en" && row.display_en) return row.display_en[i];
  if (row.display) return row.display[i];
  return chart.unit === "ratio" ? row.values[i].toFixed(3) : `${row.values[i]}/${row.n}`;
}

function Chart({ chart }) {
  const t = useT();
  const series = t.pick(chart, "series");
  const label = (row) => t.pick(row, "label");
  const f = (row, i) => fmt(chart, row, i, t.lang);
  const [active, setActive] = useState(null);
  const max = chart.unit === "ratio" ? 1 : Math.max(...chart.rows.map((r) => r.n));
  return (
    <figure className="chart">
      <figcaption>
        <b>{t.pick(chart, "title")}</b>
        <span className="fine">{t.pick(chart, "note")}</span>
      </figcaption>
      <ul className="chart-legend">
        {series.map((s, i) => (
          <li key={s}>
            <i style={{ background: chart.lower_is_better && i === 1 ? "#2F9E6E" : COLORS[i] }} />
            {s}
          </li>
        ))}
      </ul>
      {chart.rows.map((row) => (
        <div key={row.label} className="chart-row">
          <div className="chart-label">
            {label(row)} <span className="fine">n={row.n}</span>
          </div>
          <div className="bars">
            {row.values.map((v, i) => {
              const denom = chart.unit === "ratio" ? 1 : row.n;
              const pct = Math.max((v / denom) * 100, v === 0 ? 0 : 1.5);
              const id = `${row.label}-${i}`;
              const base = series[0];
              const color = chart.lower_is_better
                ? i === 0 ? "#C2413B" : "#2F9E6E"
                : COLORS[i];
              return (
                <div
                  key={i}
                  className={`bar-line ${active === id ? "active" : ""}`}
                  tabIndex={0}
                  onMouseEnter={() => setActive(id)}
                  onMouseLeave={() => setActive(null)}
                  onFocus={() => setActive(id)}
                  onBlur={() => setActive(null)}
                  aria-label={`${label(row)}: ${series[i]} ${f(row, i)} (n=${row.n}; baseline ${base} ${f(row, 0)})`}
                >
                  <span className="bar" style={{ width: `${pct}%`, background: color }} />
                  <span className="bar-val">{f(row, i)}</span>
                  {active === id && (
                    <span className="bar-tip" role="tooltip">
                      {series[i]}: {f(row, i)} · n={row.n}
                      {i > 0 ? ` · baseline (${base}) ${f(row, 0)}` : t("res.baseline")}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
      {chart.extra && <p className="fine">{t.pick(chart, "extra")}</p>}
      <span hidden>{max}</span>
    </figure>
  );
}

export default function Results({ results }) {
  const t = useT();
  if (!results) return <p className="fine">{t("res.loading")}</p>;
  return (
    <section className="results" aria-label={t("res.label")}>
      <p className="fine">{t.pick(results, "source")}</p>
      <div className="charts">
        {results.charts.map((c) => (
          <Chart key={c.id} chart={c} />
        ))}
      </div>
    </section>
  );
}
