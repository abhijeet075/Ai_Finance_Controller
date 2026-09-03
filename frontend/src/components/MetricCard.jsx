export default function MetricCard({ label, value, hint, tone = "neutral" }) {
  return (
    <article className={`metric metric--${tone}`}>
      <div className="metric__label">{label}</div>
      <strong className="metric__value">{value}</strong>
      <div className="metric__hint">{hint}</div>
    </article>
  );
}
