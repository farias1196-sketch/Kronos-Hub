import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const ports = { core: 18802, nexus: 18803, adm: 18805, media: 18809, loja: 18806, agenda: 18807, stock: 18815 };
const proxy = Object.fromEntries(Object.entries(ports).map(([service, port]) => [
  "^/api/" + service + "(?:/|$)",
  { target: "http://127.0.0.1:" + port, rewrite: path => path.replace("/api/" + service, "") },
]));
const blockUnavailable = (req, res, next) => {
  const match = /^\/api\/([^/?]+)/.exec(req.url);
  if (!match || Object.hasOwn(ports, match[1])) return next();
  res.writeHead(503, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ detail: "Serviço indisponível nesta distribuição local." }));
};
const local = { host: "127.0.0.1", port: 18800, strictPort: true, proxy };
export default defineConfig({
  plugins: [react(), { name: "local-services",
    configureServer(server) { server.middlewares.use(blockUnavailable); },
    configurePreviewServer(server) { server.middlewares.use(blockUnavailable); },
  }],
  server: local, preview: local,
});
