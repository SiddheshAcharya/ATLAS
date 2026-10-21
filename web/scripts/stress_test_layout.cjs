// R6 tripwire (docs/RISKS.md): "Synthetic test with 1000 nodes... before you have real
// data to hide behind." Runs the exact fcose layout call GraphView.tsx uses, headless
// (no DOM/canvas needed for layout computation), against synthetic citation-graph-shaped
// data at increasing scale, to measure whether the UI's own mitigation ("batch layout
// every 25 additions") is actually load-bearing.
//
// Run from web/: node scripts/stress_test_layout.cjs

const cytoscape = require("cytoscape");
const fcose = require("cytoscape-fcose");
cytoscape.use(fcose);

function buildSynthetic(n, avgEdgesPerNode) {
  const nodes = [];
  const edges = [];
  for (let i = 0; i < n; i++) {
    nodes.push({ data: { id: `p${i}`, label: `Paper ${i}`, cluster_id: i % 12, pagerank: Math.random() } });
  }
  let eid = 0;
  for (let i = 0; i < n; i++) {
    const k = 1 + Math.floor(Math.random() * avgEdgesPerNode);
    for (let j = 0; j < k; j++) {
      const target = Math.floor(Math.random() * n);
      if (target === i) continue;
      edges.push({ data: { id: `e${eid++}`, source: `p${i}`, target: `p${target}` } });
    }
  }
  return [...nodes, ...edges];
}

const sizes = [100, 500, 1000];
console.log("nodes\tedges\tfull-layout ms");
for (const n of sizes) {
  const elements = buildSynthetic(n, 3);
  const cy = cytoscape({ headless: true, elements: [] });
  cy.add(elements);
  const t0 = Date.now();
  cy.layout({ name: "fcose", animate: false, randomize: false }).run();
  const t1 = Date.now();
  console.log(`${n}\t${elements.length - n}\t${t1 - t0}`);
  cy.destroy();
}
