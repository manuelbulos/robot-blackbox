# Position paper

**"Interventions per 1,000 Robot-Hours: Toward Standardized Reliability Evidence for Deployed Robot Fleets"**

LaTeX source and compiled PDF ([paper.pdf](paper.pdf)) for the position paper. The paper proposes the metrics, schema, and intervention taxonomy that `robot-blackbox` implements.

Published directly here on GitHub. An arXiv submission is optional future work — checklist below if you ever want it.

## Build

No local LaTeX needed — either:

- **Overleaf (easiest):** create a new project, upload `paper.tex` + `references.bib`, compile with pdfLaTeX.
- **Local:** `pdflatex paper && bibtex paper && pdflatex paper && pdflatex paper` (requires a TeX distribution, e.g. `brew install --cask mactex-no-gui`).

## arXiv submission checklist

1. Category: **cs.RO** (Robotics). First-time submitters need an [endorsement](https://info.arxiv.org/help/endorsement.html) — ask a published researcher in cs.RO, or a professor contact.
2. Upload `paper.tex` + `references.bib` (arXiv compiles LaTeX server-side; it will run bibtex automatically if you include the `.bib`, but the safer standard practice is to include the generated `.bbl` file instead).
3. License: arXiv's default non-exclusive license is fine.
4. After it's live, add the arXiv link to the repo README and the blog post.
