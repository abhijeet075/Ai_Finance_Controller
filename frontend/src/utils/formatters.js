export function formatNumber(value) {
  return value == null ? "—" : new Intl.NumberFormat("en-IN").format(value);
}

export function formatPercent(value, digits = 1) {
  return value == null ? "Not evaluated" : `${(Number(value) * 100).toFixed(digits)}%`;
}

export function formatConfidence(value) {
  return value == null ? "—" : `${Number(value).toFixed(1)}%`;
}

export function formatCurrency(value, currency = "INR") {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(Number(value));
}

export function formatDuration(milliseconds) {
  if (milliseconds == null) return "—";
  if (milliseconds < 1000) return `${Number(milliseconds).toFixed(0)} ms`;
  return `${(Number(milliseconds) / 1000).toFixed(2)} sec`;
}

export function formatThroughput(value) {
  return value == null ? "—" : `${Number(value).toFixed(1)}/sec`;
}

export function shortId(value, length = 8) {
  if (!value) return "—";
  return value.length > length ? `${value.slice(0, length)}…` : value;
}

export function titleCase(value) {
  if (!value) return "—";
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
