export default function StatusBadge({ children, healthy = false }) {
  return (
    <span className={healthy ? "status" : "tag"}>
      {healthy && <i />}
      {children}
    </span>
  );
}
