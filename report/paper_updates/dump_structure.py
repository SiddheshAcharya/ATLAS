"""Print a numbered outline of a .docx body (paragraphs, tables, images) for editing by index."""
import sys
from docx import Document
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
d = Document(sys.argv[1])
for i, el in enumerate(d.element.body.iterchildren()):
    tag = el.tag.split("}")[1]
    if tag == "p":
        txt = "".join(t.text or "" for t in el.iter(W + "t"))
        img = "[IMG]" if list(el.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip")) else ""
        st = el.find(f".//{W}pStyle")
        st = st.get(W + "val") if st is not None else ""
        print(f"{i:4} P[{st}]{img} {txt[:105]}")
    elif tag == "tbl":
        rows = el.findall(W + "tr")
        first = "|".join("".join(t.text or "" for t in tc.iter(W + "t")) for tc in rows[0].findall(W + "tc"))
        print(f"{i:4} TABLE {len(rows)} rows: {first[:100]}")
    else:
        print(f"{i:4} {tag}")
