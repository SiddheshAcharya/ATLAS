import { useSyncExternalStore } from "react";

// One global theme, stored on <html data-theme> (index.css reads it). index.html applies it
// before first paint, so there is no dark flash when the projector is set to light.
// Until the user picks one, the theme follows the OS setting live; a pick is remembered
// in localStorage and wins from then on.
export type Theme = "dark" | "light";
const KEY = "atlas-theme";
const listeners = new Set<() => void>();
const systemLight = window.matchMedia("(prefers-color-scheme: light)");

function storedTheme(): Theme | null {
  try {
    const t = localStorage.getItem(KEY);
    return t === "light" || t === "dark" ? t : null;
  } catch {
    return null;
  }
}

export function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

let fadeTimer: number | undefined;

function apply(t: Theme) {
  const root = document.documentElement;
  if (root.dataset.theme === t) return;
  // cross-fade colours for this one change only (index.css .theme-transition)
  root.classList.add("theme-transition");
  window.clearTimeout(fadeTimer);
  fadeTimer = window.setTimeout(() => root.classList.remove("theme-transition"), 350);
  root.dataset.theme = t;
  listeners.forEach((l) => l());
}

export function setTheme(t: Theme) {
  try {
    localStorage.setItem(KEY, t);
  } catch {
    // private mode / blocked storage: the theme still applies for this page load
  }
  apply(t);
}

systemLight.addEventListener("change", (e) => {
  if (!storedTheme()) apply(e.matches ? "light" : "dark");
});

export function useTheme(): [Theme, () => void] {
  const theme = useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    currentTheme,
  );
  return [theme, () => setTheme(theme === "dark" ? "light" : "dark")];
}

/** Resolve a CSS custom property (index.css) for code outside Tailwind, e.g. Cytoscape. */
export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
