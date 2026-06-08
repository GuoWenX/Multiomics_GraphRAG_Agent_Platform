from __future__ import annotations

import argparse
import posixpath
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.neo4j_client import neo4j_session  # noqa: E402


NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"p": "http://schemas.openxmlformats.org/package/2006/relationships"}
RID_ATTR = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

NODE_SHEETS = {
    "基因": ("Gene", "基因"),
    "蛋白": ("Protein", "蛋白"),
    "代谢物": ("Metabolite", "代谢物"),
    "代谢通路": ("Pathway", "代谢通路"),
    "GO功能": ("GOFunction", "GO功能"),
    "疾病": ("Disease", "疾病"),
    "细胞类型": ("CellType", "细胞类型"),
    "文献": ("Literature", "文献"),
    "代谢物类别": ("MetaboliteCategory", "代谢物类别"),
    "实验测量": ("Measurement", "实验测量"),
    "基因功能": ("GeneFunction", "基因功能"),
}

RELATIONSHIP_SHEETS = {
    "编码": ("ENCODES", "编码"),
    "参与通路": ("PARTICIPATES_IN", "参与通路"),
    "催化反应": ("CATALYZES", "催化反应"),
    "通路包含代谢物": ("PATHWAY_CONTAINS_METABOLITE", "通路包含代谢物"),
    "代谢物转化": ("METABOLITE_CONVERTS_TO", "代谢物转化"),
    "通路交叉": ("PATHWAY_CROSSES", "通路交叉"),
    "具有功能": ("HAS_FUNCTION", "具有功能"),
    "关联疾病": ("ASSOCIATED_WITH_DISEASE", "关联疾病"),
    "表达于": ("EXPRESSED_IN", "表达于"),
    "被引用": ("CITED_BY", "被引用"),
    "蛋白互作": ("PROTEIN_INTERACTS_WITH", "蛋白互作"),
    "代谢物关联疾病": ("METABOLITE_ASSOCIATED_WITH_DISEASE", "代谢物关联疾病"),
    "属于类别": ("BELONGS_TO_CATEGORY", "属于类别"),
    "父类为": ("PARENT_CATEGORY_OF", "父类为"),
    "具有测量": ("HAS_MEASUREMENT", "具有测量"),
    "执行功能": ("EXECUTES_FUNCTION", "执行功能"),
    "映射到GO": ("MAPS_TO_GO", "映射到GO"),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="/tmp/windows_tmp")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    source_dir = Path(args.dir)
    node_files = sorted(source_dir.glob("*nodes*.xlsx"))
    relationship_files = sorted(source_dir.glob("*relationships*.xlsx"))
    if not node_files or not relationship_files:
        raise SystemExit(f"No node/relationship xlsx files found in {source_dir}")

    excel_nodes = load_excel_nodes(node_files)
    excel_relationships = load_excel_relationships(relationship_files)
    print(f"Excel nodes: {len(excel_nodes)} from {len(node_files)} files")
    print(f"Excel relationships: {len(excel_relationships)} from {len(relationship_files)} files")

    existing = load_existing_nodes()
    plan = plan_nodes(excel_nodes, existing)
    rel_plan = plan_relationships(excel_relationships, plan["vid_to_element_id"])

    print(f"Node updates: {len(plan['updates'])}")
    print(f"Node creates: {len(plan['creates'])}")
    print(f"Relationship upserts: {len(rel_plan['upserts'])}")
    print(f"Relationship skipped missing endpoints: {len(rel_plan['skipped'])}")
    print_smpd3_ppi_preview(excel_nodes, excel_relationships, plan["vid_to_element_id"])

    if not args.apply:
        print("Dry run only. Re-run with --apply to write Neo4j.")
        return

    apply_node_plan(plan)
    refreshed_vid_map = load_vid_to_element_id()
    rel_plan = plan_relationships(excel_relationships, {**plan["vid_to_element_id"], **refreshed_vid_map})
    apply_relationship_plan(rel_plan)
    print("Import complete.")


def load_excel_nodes(files: list[Path]) -> list[dict]:
    nodes = []
    seen_vids = set()
    for file in files:
        for sheet_name, rows in iter_xlsx_sheets(file):
            if sheet_name not in NODE_SHEETS:
                continue
            label, zh_type = NODE_SHEETS[sheet_name]
            for row in rows:
                vid = clean_value(row.get("vid"))
                name = clean_value(row.get("name"))
                if not vid or not name or vid in seen_vids:
                    continue
                seen_vids.add(vid)
                props = clean_properties(row)
                props["vid"] = vid
                props["name"] = name
                props["entity_type"] = label
                props["entity_type_zh"] = zh_type
                props.setdefault("type", zh_type)
                nodes.append({"vid": vid, "label": label, "props": props})
    return nodes


def load_excel_relationships(files: list[Path]) -> list[dict]:
    relationships = []
    seen = set()
    for file in files:
        for sheet_name, rows in iter_xlsx_sheets(file):
            if sheet_name not in RELATIONSHIP_SHEETS:
                continue
            relationship_type, zh_type = RELATIONSHIP_SHEETS[sheet_name]
            for row in rows:
                src = clean_value(row.get("src"))
                dst = clean_value(row.get("dst"))
                if not src or not dst:
                    continue
                props = clean_properties({k: v for k, v in row.items() if k not in {"src", "dst"}})
                props["relationship_type"] = relationship_type
                props["relationship_type_zh"] = zh_type
                key = (src, dst, relationship_type, tuple(sorted(props.items())))
                if key in seen:
                    continue
                seen.add(key)
                relationships.append({"src_vid": src, "dst_vid": dst, "type": relationship_type, "props": props})
    return relationships


def load_existing_nodes() -> dict:
    query = """
    MATCH (n:KGNode)
    RETURN elementId(n) AS element_id, labels(n) AS labels, properties(n) AS props
    """
    by_vid = {}
    by_identity = {}
    with neo4j_session() as session:
        for record in session.run(query):
            element_id = record["element_id"]
            props = dict(record["props"] or {})
            labels = list(record["labels"] or [])
            vid = clean_value(props.get("vid"))
            if vid:
                by_vid[vid] = element_id
            for label in labels:
                if label == "KGNode":
                    continue
                for key in identity_keys(label, props):
                    if key and key not in by_identity:
                        by_identity[key] = element_id
    return {"by_vid": by_vid, "by_identity": by_identity}


def load_vid_to_element_id() -> dict[str, str]:
    with neo4j_session() as session:
        return {
            record["vid"]: record["element_id"]
            for record in session.run(
                "MATCH (n:KGNode) WHERE n.vid IS NOT NULL RETURN toString(n.vid) AS vid, elementId(n) AS element_id"
            )
        }


def plan_nodes(excel_nodes: list[dict], existing: dict) -> dict:
    updates = []
    creates = []
    vid_to_element_id = dict(existing["by_vid"])
    by_identity = dict(existing["by_identity"])
    pending_identity_vid = {}
    for node in excel_nodes:
        vid = node["vid"]
        label = node["label"]
        props = node["props"]
        keys = identity_keys(label, props)
        element_id = vid_to_element_id.get(vid) or next((by_identity[key] for key in keys if key in by_identity), None)
        if element_id:
            updates.append({"element_id": element_id, "label": label, "props": props})
            vid_to_element_id[vid] = element_id
            for key in keys:
                by_identity[key] = element_id
            continue
        pending_vid = next((pending_identity_vid[key] for key in keys if key in pending_identity_vid), None)
        if pending_vid:
            vid_to_element_id[vid] = pending_vid
            continue
        creates.append({"vid": vid, "label": label, "props": props})
        for key in keys:
            pending_identity_vid[key] = vid
    return {"updates": updates, "creates": creates, "vid_to_element_id": vid_to_element_id}


def plan_relationships(relationships: list[dict], vid_to_element_id: dict[str, str]) -> dict:
    upserts = []
    skipped = []
    for rel in relationships:
        source_id = vid_to_element_id.get(rel["src_vid"])
        target_id = vid_to_element_id.get(rel["dst_vid"])
        if not source_id or not target_id:
            skipped.append(rel)
            continue
        upserts.append({**rel, "source_id": source_id, "target_id": target_id})
    return {"upserts": upserts, "skipped": skipped}


def apply_node_plan(plan: dict) -> None:
    update_groups = defaultdict(list)
    for row in plan["updates"]:
        update_groups[row["label"]].append(row)
    create_groups = defaultdict(list)
    for row in plan["creates"]:
        create_groups[row["label"]].append(row)

    with neo4j_session("WRITE") as session:
        for label, rows in update_groups.items():
            for batch in chunks(rows, 500):
                query = f"""
                UNWIND $rows AS row
                MATCH (n)
                WHERE elementId(n) = row.element_id
                SET n:KGNode:{escape_identifier(label)}
                SET n += row.props
                """
                session.run(query, {"rows": batch}).consume()
        for label, rows in create_groups.items():
            for batch in chunks(rows, 500):
                query = f"""
                UNWIND $rows AS row
                CREATE (n:KGNode:{escape_identifier(label)})
                SET n = row.props
                """
                session.run(query, {"rows": batch}).consume()


def apply_relationship_plan(plan: dict) -> None:
    groups = defaultdict(list)
    for row in plan["upserts"]:
        groups[row["type"]].append(row)
    with neo4j_session("WRITE") as session:
        for relationship_type, rows in groups.items():
            for batch in chunks(rows, 500):
                query = f"""
                UNWIND $rows AS row
                MATCH (source), (target)
                WHERE elementId(source) = row.source_id AND elementId(target) = row.target_id
                MERGE (source)-[r:{escape_identifier(relationship_type)}]->(target)
                SET r += row.props
                """
                session.run(query, {"rows": batch}).consume()


def print_smpd3_ppi_preview(nodes: list[dict], relationships: list[dict], vid_to_element_id: dict[str, str]) -> None:
    smpd3_protein_vids = {
        node["vid"]
        for node in nodes
        if node["label"] == "Protein" and normalize(node["props"].get("name")) == "smpd3"
    }
    ppi_rows = [
        rel
        for rel in relationships
        if rel["type"] == "PROTEIN_INTERACTS_WITH"
        and (rel["src_vid"] in smpd3_protein_vids or rel["dst_vid"] in smpd3_protein_vids)
    ]
    resolvable = [
        rel for rel in ppi_rows if vid_to_element_id.get(rel["src_vid"]) and vid_to_element_id.get(rel["dst_vid"])
    ]
    print(f"SMPD3 protein vids in Excel: {sorted(smpd3_protein_vids)}")
    print(f"SMPD3 PPI rows in Excel: {len(ppi_rows)}")
    print(f"SMPD3 PPI rows currently resolvable: {len(resolvable)}")


def identity_keys(label: str, props: dict) -> list[tuple]:
    name = normalize(props.get("name"))
    if not name:
        return []
    if label in {"Gene", "Protein"}:
        organism = normalize(props.get("organism"))
        keys = [(label, name)]
        if organism:
            keys.insert(0, (label, name, organism))
        return keys
    if label == "GOFunction":
        return [(label, normalize(props.get("go_id")) or name)]
    if label == "Pathway":
        return [(label, normalize(props.get("kegg_id")) or name)]
    if label == "Literature":
        return [(label, normalize(props.get("pmid")) or name)]
    if label == "Measurement":
        return [(label, name, normalize(props.get("experiment_id")))]
    if label == "CellType":
        return [(label, name, normalize(props.get("tissue")))]
    if label == "MetaboliteCategory":
        return [(label, name, normalize(props.get("category_level")))]
    if label == "GeneFunction":
        return [(label, name, normalize(props.get("function_category")))]
    return [(label, name)]


def iter_xlsx_sheets(path: Path):
    with ZipFile(path) as archive:
        shared_strings = read_shared_strings(archive)
        for sheet_name, sheet_path in workbook_sheets(archive):
            rows = iter_sheet_rows(archive, sheet_path, shared_strings)
            try:
                header = next(rows)
            except StopIteration:
                continue
            header = [str(item).strip() for item in header]
            dict_rows = []
            for row in rows:
                item = {header[index]: row[index] if index < len(row) else "" for index in range(len(header))}
                if any(clean_value(value) for value in item.values()):
                    dict_rows.append(item)
            yield sheet_name, dict_rows


def workbook_sheets(archive: ZipFile) -> list[tuple[str, str]]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    relmap = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels.findall("p:Relationship", REL_NS)}
    sheets = []
    for sheet in workbook.findall("a:sheets/a:sheet", NS):
        target = relmap[sheet.attrib[RID_ATTR]].lstrip("/")
        if not target.startswith("xl/"):
            target = posixpath.normpath(posixpath.join("xl", target))
        sheets.append((sheet.attrib["name"], target))
    return sheets


def read_shared_strings(archive: ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(text.text or "" for text in item.findall(".//a:t", NS)) for item in root.findall("a:si", NS)]


def iter_sheet_rows(archive: ZipFile, sheet_path: str, shared_strings: list[str]):
    root = ET.iterparse(archive.open(sheet_path), events=("end",))
    for _, element in root:
        if not element.tag.endswith("}row"):
            continue
        values = []
        for cell in element.findall("a:c", NS):
            index = column_index(cell.attrib.get("r", "A1"))
            while len(values) <= index:
                values.append("")
            values[index] = cell_value(cell, shared_strings)
        yield values
        element.clear()


def cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//a:t", NS))
    value = cell.find("a:v", NS)
    if value is None:
        return ""
    raw = value.text or ""
    if cell_type == "s":
        return shared_strings[int(raw)] if raw.isdigit() and int(raw) < len(shared_strings) else raw
    return raw


def column_index(cell_ref: str) -> int:
    letters = "".join(char for char in cell_ref if char.isalpha())
    value = 0
    for char in letters:
        value = value * 26 + ord(char.upper()) - 64
    return value - 1


def clean_properties(row: dict) -> dict:
    return {str(key).strip(): value for key, value in ((k, clean_value(v)) for k, v in row.items()) if key and value != ""}


def clean_value(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def normalize(value) -> str:
    return clean_value(value).lower()


def escape_identifier(value: str) -> str:
    return f"`{value.replace('`', '``')}`"


def chunks(items: list, size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


if __name__ == "__main__":
    main()
