---
title: ATLAS GROBID
emoji: 📄
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 8070
pinned: false
---

GROBID 0.9.1 (CRF models) for the ATLAS literature-review project: PDF → TEI XML with
sections and references. Only open-access PDFs are sent here.

Health check: `GET /api/isalive` → `true`. Point ATLAS at it with
`GROBID_URL=https://<user>-<space-name>.hf.space` in `.env`.

A free Space sleeps after ~48 h without traffic; the first request wakes it (a few
minutes). Hit `/api/isalive` before starting a crawl.
