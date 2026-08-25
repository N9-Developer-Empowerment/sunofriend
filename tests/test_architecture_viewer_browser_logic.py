from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from devtools.architecture_viewer.analyzer import analyse_source_tree
from devtools.architecture_viewer.renderer import _INDEX_SCRIPT_V2


def test_embedded_browser_logic_navigates_hash_and_searches(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is optional and unavailable")
    package = tmp_path / "src" / "example"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("from .a import PublicA\n", encoding="utf-8")
    (package / "a.py").write_text(
        '''"""Public A."""
from .b import B
class PublicA:
    def run(self):
        return B()
''',
        encoding="utf-8",
    )
    (package / "b.py").write_text("class B: pass\n", encoding="utf-8")
    groups = tmp_path / "groups.json"
    groups.write_text(
        json.dumps(
            {
                "schema": "sunofriend-architecture-groups.v2",
                "default_group": "other",
                "groups": [
                    {"id": "domain", "label": "Domain", "modules": ["a", "b"]},
                    {"id": "other", "label": "Other"},
                ],
            }
        ),
        encoding="utf-8",
    )
    architecture = analyse_source_tree(
        package,
        repository_root=tmp_path,
        groups_path=groups,
    )
    overlays = {
        "schema": "sunofriend-architecture-overlays.v1",
        "documents": [],
        "diagnostics": [],
    }
    check = {
        "status": "passed",
        "contracts": [],
        "violations": [],
        "parse_errors": [],
        "test_parse_errors": [],
    }
    values = {
        "architecture-data": architecture,
        "overlay-data": overlays,
        "comparison-data": None,
        "check-data": check,
    }
    prelude = f'''
class Element {{
  constructor(id="") {{ this.id=id; this.children=[]; this.listeners={{}}; this.dataset={{}}; this.hidden=false; this.checked=false; this.value=""; this._text=""; this._html=""; }}
  set textContent(value) {{ this._text=String(value ?? ""); this._html=this._text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;"); }}
  get textContent() {{ return this._text; }}
  set innerHTML(value) {{ this._html=String(value); }}
  get innerHTML() {{ return this._html; }}
  append(...items) {{ this.children.push(...items); }}
  replaceChildren(...items) {{ this.children=[...items]; }}
  addEventListener(name, callback) {{ this.listeners[name]=callback; }}
  setAttribute(name, value) {{ this[name]=String(value); }}
  getBoundingClientRect() {{ return {{left:0,top:0,width:100,height:80}}; }}
  querySelector() {{ return null; }}
  querySelectorAll() {{ return []; }}
  scrollIntoView() {{}}
}}
const values={json.dumps(values, sort_keys=True)};
const ids=["graph-shell","nodes","edges","detail","graph-title","graph-caption","breadcrumbs","all-edges","edge-control","search","search-results","live"];
const elements=Object.fromEntries(ids.map(id=>[id,new Element(id)]));
globalThis.document={{
  getElementById(id) {{ if(Object.hasOwn(values,id)) return {{textContent:JSON.stringify(values[id])}}; return elements[id] ?? null; }},
  createElement() {{ return new Element(); }},
  createElementNS() {{ return new Element(); }},
  createTextNode(value) {{ const node=new Element(); node.textContent=value; return node; }},
  addEventListener() {{}},
}};
globalThis.history={{replaceState(){{}}}};
globalThis.location={{hash:"#group=domain",pathname:"/index.html"}};
globalThis.CSS={{escape(value){{return String(value)}}}};
globalThis.requestAnimationFrame=()=>{{}};
Object.defineProperty(globalThis,"navigator",{{value:{{}},configurable:true}});
'''
    postlude = '''
const groupStubCount=elements.nodes.children.filter(item=>String(item.className).includes("stub")).length;
elements.search.value="publica";
elements.search.listeners.input();
const searchResultCount=elements["search-results"].children.length;
elements["search-results"].children[0].listeners.click();
process.stdout.write(JSON.stringify({
  title: elements["graph-title"].textContent,
  moduleDetail: elements.detail.innerHTML.includes("Public A."),
  breadcrumbCount: elements.breadcrumbs.children.length,
  groupStubCount,
  searchResultCount,
  searchVisible: !elements["search-results"].hidden,
}));
'''
    script = tmp_path / "browser-smoke.js"
    script.write_text(prelude + _INDEX_SCRIPT_V2 + postlude, encoding="utf-8")

    completed = subprocess.run(
        [node, str(script)],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    result = json.loads(completed.stdout)

    assert result == {
        "title": "Domain",
        "moduleDetail": True,
        "breadcrumbCount": 5,
        "groupStubCount": 1,
        "searchResultCount": 1,
        "searchVisible": False,
    }
