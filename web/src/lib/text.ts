// Source metadata (Crossref/OpenAlex titles and venues) sometimes arrives HTML-escaped,
// e.g. "Science &amp; Technology". Decode for display only; stored data is untouched.
export function decodeEntities(s: string | null | undefined): string {
  if (!s || !s.includes("&")) return s ?? "";
  const el = document.createElement("textarea");
  el.innerHTML = s;
  return el.value;
}

// Canonical paper ids (src/atlas/ids.py): doi:… arxiv:… pmid:… openalex:… s2:… sha1:…
const PAPER_ID = /(?:doi|arxiv|pmid|openalex|s2|sha1):[^\s,;\]]+/g;
const CITATION_GROUP = /\[([^\]]*?(?:doi|arxiv|pmid|openalex|s2|sha1):[^\]]*)\]/g;

/**
 * Replace inline citation groups like "[doi:10.1/x, arxiv:2401.1]" with numbered markdown
 * links "[[1]](/runs/r/paper/doi%3A10.1%2Fx) [[2]](…)". `numbering` is shared across the
 * report so a paper keeps one number everywhere; ids are numbered in order of first use.
 */
export function numberCitations(md: string, runId: string, numbering: Map<string, number>): string {
  return md.replace(CITATION_GROUP, (group: string, inner: string) => {
    const ids = inner.match(PAPER_ID);
    if (!ids) return group;
    return ids
      .map((id) => {
        if (!numbering.has(id)) numbering.set(id, numbering.size + 1);
        return `[[${numbering.get(id)}]](/runs/${runId}/paper/${encodeURIComponent(id)})`;
      })
      .join("");
  });
}
