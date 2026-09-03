const rows = [
  ["matched", "Matched"],
  ["review", "Review"],
  ["exceptions", "Exceptions"],
];

export default function DistributionBars({ metrics }) {
  const total = Number(metrics?.total_records || 0);
  return (
    <div className="distribution">
      {rows.map(([key, label]) => {
        const count = Number(metrics?.[key] || 0);
        const width = total ? Math.max((count / total) * 100, count ? 2 : 0) : 0;
        return (
          <div className="distribution__row" key={key}>
            <div className="distribution__meta">
              <span>{label}</span>
              <strong>{count.toLocaleString("en-IN")}</strong>
            </div>
            <div className="distribution__track">
              <span
                className={`distribution__bar distribution__bar--${key}`}
                style={{ width: `${width}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
