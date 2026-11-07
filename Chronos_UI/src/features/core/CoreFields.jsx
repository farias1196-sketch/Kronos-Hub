export function CoreField({ className = "", label, type = "text", value, onChange }) {
  return (
    <label className={`core-field ${className}`}>
      <span>{label}</span>
      <input type={type} value={value || ""} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

export function CoreReadonly({ label, value }) {
  return (
    <div className="core-readonly">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
