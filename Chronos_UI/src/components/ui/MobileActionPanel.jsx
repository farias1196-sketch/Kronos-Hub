import { useState } from "react";
import { ChevronRight } from "lucide-react";
import MobileDialog from "./MobileDialog";
import "./mobileActionPanel.css";

export default function MobileActionPanel({ mobile, title, children, open, onOpen, onClose, feedback }) {
  const [localOpen, setOpen] = useState(false);
  const isOpen = open ?? localOpen;
  if (!mobile) return children;
  return <>
    <button type="button" className="mobile-action-panel" onClick={() => { setOpen(true); onOpen?.(); }}>{title}<ChevronRight size={18} /></button>
    {isOpen && <MobileDialog title={title} onClose={() => { setOpen(false); onClose?.(); }}>{feedback && <p role="status">{feedback}</p>}{children}</MobileDialog>}
  </>;
}
