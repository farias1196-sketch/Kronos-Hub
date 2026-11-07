export const chronosThemes = [
  { id: "rosa-branco", label: "Rosa branco", swatch: "#ec4899" },
  { id: "verde-branco", label: "Verde branco", swatch: "#22c55e" },
  { id: "azul-branco", label: "Azul branco", swatch: "#2563eb" },
  { id: "laranja-cinza", label: "Laranja cinza", swatch: "#f97316" },
  { id: "rosa-preto", label: "Rosa preto", swatch: "#f472b6" },
  { id: "prata-cinza", label: "Prata cinza", swatch: "#475569" },
];

export const DEFAULT_THEME = "rosa-branco";

export function resolveTheme(value) {
  return chronosThemes.some((theme) => theme.id === value) ? value : DEFAULT_THEME;
}

export function getStoredTheme() {
  return resolveTheme(localStorage.getItem("chronos-theme"));
}
