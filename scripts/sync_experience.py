from __future__ import annotations

import re
from pathlib import Path


def find_source_file() -> Path:
    candidates = [
        Path("portfolio/src/data/experience.ts"),
        Path("../github_pages/epicgdog.github.io/src/data/experience.ts"),
        Path("../epicgdog.github.io/src/data/experience.ts"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not find source experience.ts")


def extract_experience_array(ts_text: str) -> str:
    marker = "export const experiences"
    start = ts_text.find(marker)
    if start == -1:
        raise ValueError("Could not find 'export const experiences'")

    open_bracket = ts_text.find("[", start)
    if open_bracket == -1:
        raise ValueError("Could not find opening '[' for experiences")

    depth = 0
    for i in range(open_bracket, len(ts_text)):
        ch = ts_text[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return ts_text[open_bracket + 1 : i]
    raise ValueError("Could not find closing ']' for experiences")


def split_top_level_objects(array_body: str) -> list[str]:
    objects: list[str] = []
    depth = 0
    start = -1
    in_string = False
    string_char = ""
    escape = False

    for i, ch in enumerate(array_body):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == string_char:
                in_string = False
            continue

        if ch in ("'", '"'):
            in_string = True
            string_char = ch
            continue

        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                objects.append(array_body[start : i + 1])
                start = -1

    return objects


def parse_string_field(block: str, field: str) -> str | None:
    match = re.search(rf"\b{re.escape(field)}\s*:\s*'([^']*)'", block)
    return match.group(1).strip() if match else None


def parse_bool_field(block: str, field: str) -> bool:
    return bool(re.search(rf"\b{re.escape(field)}\s*:\s*true\b", block))


def parse_string_array_field(block: str, field: str) -> list[str]:
    match = re.search(rf"\b{re.escape(field)}\s*:\s*\[([\s\S]*?)\]", block)
    if not match:
        return []
    return [item.strip() for item in re.findall(r"'([^']*)'", match.group(1))]


def latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def parse_source_experiences(ts_text: str) -> list[dict[str, object]]:
    array_body = extract_experience_array(ts_text)
    blocks = split_top_level_objects(array_body)

    parsed: list[dict[str, object]] = []
    for block in blocks:
        title = parse_string_field(block, "title")
        company = parse_string_field(block, "company")
        period = parse_string_field(block, "period")
        location = parse_string_field(block, "location")
        if not (title and company and period and location):
            continue

        accomplishments = parse_string_array_field(block, "accomplishments")
        in_progress = parse_bool_field(block, "inProgress")
        focus_areas = parse_string_array_field(block, "focusAreas")

        parsed.append(
            {
                "title": title,
                "company": company,
                "period": period,
                "location": location,
                "accomplishments": accomplishments,
                "inProgress": in_progress,
                "focusAreas": focus_areas,
            }
        )
    return parsed


def existing_keys_from_tex(tex_text: str) -> set[str]:
    pattern = re.compile(
        r"\\resumeSubheading\s*\n\{([^}]*)\}\{([^}]*)\}\s*\n\{([^}]*)\}\{([^}]*)\}",
        re.MULTILINE,
    )
    keys: set[str] = set()
    for match in pattern.finditer(tex_text):
        title = match.group(1).strip()
        period = match.group(2).strip()
        company = match.group(3).strip()
        key = f"{title}|{company}|{period}"
        keys.add(key)
    return keys


def build_entry_block(entry: dict[str, object]) -> str:
    title = latex_escape(str(entry["title"]))
    period = latex_escape(str(entry["period"]))
    company = latex_escape(str(entry["company"]))
    location = latex_escape(str(entry["location"]))
    accomplishments = [latex_escape(item) for item in entry["accomplishments"]]  # type: ignore[index]

    lines = [
        r"\resumeSubheading",
        f"{{{title}}}{{{period}}}",
        f"{{{company}}}{{{location}}}",
        r"\resumeItemListStart",
    ]

    if entry["inProgress"]:
        focus = entry["focusAreas"]  # type: ignore[index]
        if focus:
            focus_text = latex_escape(", ".join(str(item) for item in focus))
            lines.append(f"\resumeItem{{In progress. Focus areas: {focus_text}.}}")
        else:
            lines.append(r"\resumeItem{In progress.}")
    else:
        for item in accomplishments:
            lines.append(
                f"\resumeItem{{{item}.}}"
                if not item.endswith(".")
                else f"\resumeItem{{{item}}}"
            )

    lines.append(r"\resumeItemListEnd")
    return "\n".join(lines)


def insert_entries(tex_text: str, blocks: list[str]) -> str:
    section_start = tex_text.find(r"\section{Experience}")
    if section_start == -1:
        raise ValueError("Could not find Experience section")

    section_end = tex_text.find(r"\resumeSubHeadingListEnd", section_start)
    if section_end == -1:
        raise ValueError("Could not find end of Experience section")

    insert_text = "\n\n" + "\n\n".join(blocks) + "\n\n"
    return tex_text[:section_end] + insert_text + tex_text[section_end:]


def main() -> None:
    source_file = find_source_file()
    resume_file = Path("gerard_consuelo_resume.tex")

    source_text = source_file.read_text(encoding="utf-8")
    resume_text = resume_file.read_text(encoding="utf-8")

    entries = parse_source_experiences(source_text)
    existing_keys = existing_keys_from_tex(resume_text)

    new_entries: list[dict[str, object]] = []
    for entry in entries:
        key = f"{entry['title']}|{entry['company']}|{entry['period']}"
        if key not in existing_keys:
            new_entries.append(entry)

    if not new_entries:
        print("No new experience entries to append.")
        return

    blocks = [build_entry_block(entry) for entry in new_entries]
    updated = insert_entries(resume_text, blocks)
    resume_file.write_text(updated, encoding="utf-8")
    print(f"Appended {len(new_entries)} new experience entr(y/ies).")


if __name__ == "__main__":
    main()
