import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import "./mobileDialog.css";

export default function MobileDialog({ title, onClose, children }) {
  const ref = useRef(null);
  useEffect(() => { const dialog = ref.current; dialog.showModal(); return () => dialog.close(); }, []);
  return <dialog ref={ref} className="chronos-mobile-dialog" aria-label={title} onCancel={event => { event.preventDefault(); onClose(); }}>
    <header><h2>{title}</h2><button type="button" onClick={onClose} aria-label="Fechar janela" autoFocus><X size={20} /></button></header>
    <div className="chronos-mobile-dialog-body">{children}</div>
  </dialog>;
}
