import { titleCase } from "../utils/formatters";

export default function StatusBadge({ status, children }) {
  const value = status || "neutral";
  return (
    <span className={`badge badge--${value}`}>
      <span className="badge__dot" aria-hidden="true" />
      {children || titleCase(value)}
    </span>
  );
}
