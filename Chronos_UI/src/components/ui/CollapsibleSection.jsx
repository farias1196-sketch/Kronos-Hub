import { useId, useState } from "react";
import { ChevronDown } from "lucide-react";

export default function CollapsibleSection({
  title,
  description,
  summary,
  defaultOpen = false,
  open,
  onOpenChange,
  className = "",
  children,
}) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(defaultOpen);
  const isOpen = open ?? uncontrolledOpen;
  const contentId = useId();

  return (
    <section className={`collapsible-section ${className} ${isOpen ? "is-open" : ""}`}>
      <button
        type="button"
        className="collapsible-section-trigger"
        aria-expanded={isOpen}
        aria-controls={contentId}
        onClick={() => {
          const nextOpen = !isOpen;
          if (open === undefined) setUncontrolledOpen(nextOpen);
          onOpenChange?.(nextOpen);
        }}
      >
        <span>
          <strong>{title}</strong>
          {description && <span>{description}</span>}
          {summary && <small>{summary}</small>}
        </span>
        <ChevronDown size={18} aria-hidden="true" />
      </button>
      <div id={contentId} className="collapsible-section-content" aria-hidden={!isOpen} inert={isOpen ? undefined : ""}>
        <div className="collapsible-section-inner">{children}</div>
      </div>
    </section>
  );
}
