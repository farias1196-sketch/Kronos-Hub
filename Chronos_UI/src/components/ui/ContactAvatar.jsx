import { useEffect, useRef, useState } from "react";
import { UserRound } from "lucide-react";
import { authFetch } from "../../auth";
import "./contactAvatar.css";

const cache = new Map();
const pending = new Map();
const queue = [];
let running = 0;
const scope = () => `${localStorage.getItem("chronos-token") || ""}:${localStorage.getItem("chronos-current-tenant-slug") || ""}`;
function pump() {
  while (running < 2 && queue.length) {
    const job = queue.shift();
    running += 1;
    job().finally(() => { running -= 1; pump(); });
  }
}
function loadPhoto(src, owner) {
  const key = `${owner}:${src}`;
  if (cache.get(key)?.until > Date.now()) return Promise.resolve(cache.get(key).blob);
  if (pending.has(key)) return pending.get(key);
  const job = new Promise((resolve) => {
    queue.push(async () => {
      let blob = null;
      try {
        if (owner !== scope()) return resolve(null);
        const response = await authFetch(src, { signal: AbortSignal.timeout(18000) });
        if (response.ok && response.status !== 204 && /^image\/(jpeg|png|webp)$/.test(response.headers.get("content-type")?.split(";")[0] || "")) {
          const data = await response.blob();
          if (data.size && data.size <= 512 * 1024) blob = data;
        }
      } catch { /* Keep the neutral avatar when the photo is unavailable. */ }
      cache.set(key, { blob, until: Date.now() + (blob ? 300000 : 30000) });
      while (cache.size > 150) cache.delete(cache.keys().next().value);
      resolve(blob);
    });
  }).finally(() => pending.delete(key));
  pending.set(key, job);
  pump();
  return job;
}

export default function ContactAvatar({ src, name, className = "" }) {
  const element = useRef(null);
  const [photo, setPhoto] = useState(null);
  const owner = scope();
  const key = `${owner}:${src}`;
  useEffect(() => {
    if (!src) return;
    let disposed = false, objectUrl;
    const observer = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;
      observer.disconnect();
      loadPhoto(src, owner).then((blob) => {
        if (disposed || !blob || owner !== scope()) return;
        objectUrl = URL.createObjectURL(blob);
        setPhoto({ key, url: objectUrl });
      });
    }, { rootMargin: "80px" });
    observer.observe(element.current);
    return () => { disposed = true; observer.disconnect(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [src, owner, key]);
  return <span ref={element} className={`contact-avatar ${className}`}>
    {photo?.key === key ? <img src={photo.url} alt={`Foto de ${name || "contato"}`} onError={() => setPhoto(null)} /> : <UserRound size={22} aria-hidden="true" />}
  </span>;
}
