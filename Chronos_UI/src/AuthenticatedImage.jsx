import React, { useEffect, useState } from "react";
import { authFetch } from "./auth";

export default function AuthenticatedImage({ src, ...props }) {
  const [localUrl, setLocalUrl] = useState("");
  const parsed = new URL(src || "", window.location.origin);
  const proxiedMedia = parsed.origin === window.location.origin && parsed.pathname.startsWith("/api/media/");
  const protectedMedia = proxiedMedia && parsed.pathname.includes("/media/cache/") && !parsed.searchParams.has("asset_signature");
  useEffect(() => {
    if (!protectedMedia) return;
    let disposed = false;
    let objectUrl;
    setLocalUrl("");
    authFetch(src).then((response) => {
      if (!response.ok) throw new Error("Imagem indisponivel");
      return response.blob();
    }).then((blob) => {
      if (disposed) return;
      objectUrl = URL.createObjectURL(blob);
      setLocalUrl(objectUrl);
    }).catch(() => {});
    return () => { disposed = true; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [src, protectedMedia]);
  const source = protectedMedia ? localUrl : src;
  return source ? <img {...props} src={source} /> : null;
}
