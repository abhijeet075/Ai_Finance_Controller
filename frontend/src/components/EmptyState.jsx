export default function EmptyState({ title, message }) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon" aria-hidden="true">◇</div>
      <h3>{title}</h3>
      <p>{message}</p>
    </div>
  );
}
