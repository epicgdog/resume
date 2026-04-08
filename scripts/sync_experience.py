"""Sync Experience section from resume .tex → portfolio experience.ts

Direction: resume .tex is the source of truth.
Matching: by company name (fuzzy-normalized).
Behavior:
  - If a company exists in both .tex and experience.ts → update bullet points
  - If a company exists only in .tex (including commented-out) → add it
  - If a company exists only in experience.ts → leave it alone (additive)
"""

from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Locate files
# ---------------------------------------------------------------------------

def find_portfolio_dir() -> Path:
    candidates = [
        Path("portfolio"),
        Path("../github_pages/epicgdog.github.io"),
        Path("../epicgdog.github.io"),
    ]
    for c in candidates:
        if (c / "src" / "data" / "experience.ts").exists():
            return c
    raise FileNotFoundError("Could not find portfolio directory with src/data/experience.ts")


# ---------------------------------------------------------------------------
# Parse .tex Experience section  (active + commented-out entries)
# ---------------------------------------------------------------------------

def _strip_latex(text: str) -> str:
    """Remove LaTeX commands and braces to get plain text."""
    text = re.sub(r"\\textbf\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\textit\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\emph\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\href\{[^}]*\}\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\underline\{([^}]*)\}", r"\1", text)
    text = text.replace(r"\%", "%")
    text = text.replace(r"\&", "&")
    text = text.replace(r"\_", "_")
    text = text.replace(r"\#", "#")
    text = text.replace(r"\$", "$")
    text = text.replace(r"\{", "{")
    text = text.replace(r"\}", "}")
    text = text.replace(r"\textbackslash{}", "\\")
    text = text.replace(r"\textasciitilde{}", "~")
    text = text.replace(r"\textasciicircum{}", "^")
    return text.strip()


def _uncomment_line(line: str) -> str:
    """Strip leading '% ' or '%' from a commented line."""
    stripped = line.lstrip()
    if stripped.startswith("% "):
        return stripped[2:]
    if stripped.startswith("%"):
        return stripped[1:]
    return line


def parse_experience_section(tex_text: str) -> list[dict]:
    """Parse the Experience section, including commented-out entries."""
    # Find the Experience section
    exp_start = tex_text.find(r"\section{Experience}")
    if exp_start == -1:
        print("Warning: No Experience section found in .tex")
        return []

    # Find the end of the Experience section (next \section or \end{document})
    exp_end_match = re.search(
        r"\\section\{(?!Experience)", tex_text[exp_start + 1:]
    )
    if exp_end_match:
        exp_end = exp_start + 1 + exp_end_match.start()
    else:
        exp_end = len(tex_text)

    section = tex_text[exp_start:exp_end]
    lines = section.split("\n")

    entries: list[dict] = []
    i = 0

    while i < len(lines):
        line = lines[i].rstrip("\r")
        raw = line.lstrip()

        # Detect \resumeSubheading (active or commented)
        is_commented = raw.startswith("%")
        uncommented = _uncomment_line(line).strip() if is_commented else raw

        if r"\resumeSubheading" in uncommented:
            entry = _parse_subheading_block(lines, i, is_commented)
            if entry:
                entry["commented"] = is_commented
                entries.append(entry)
                # Skip past this block
                i = entry.pop("_end_line", i + 1)
                continue

        i += 1

    return entries


def _parse_subheading_block(
    lines: list[str], start: int, is_commented: bool
) -> Optional[dict]:
    """Parse a \\resumeSubheading block starting at `start`."""
    # Collect all relevant lines for this block
    block_lines: list[str] = []
    i = start

    # We need to find: \resumeSubheading, {title}{period}, {company}{location},
    # then \resumeItemListStart ... items ... \resumeItemListEnd
    while i < len(lines):
        raw = lines[i].rstrip("\r")
        uncommented = _uncomment_line(raw).strip() if is_commented else raw.strip()
        block_lines.append(uncommented)

        if r"\resumeItemListEnd" in uncommented:
            break
        # Safety: don't go past next subheading
        if (
            i > start + 1
            and r"\resumeSubheading" in uncommented
        ):
            break
        i += 1

    block_text = "\n".join(block_lines)
    end_line = i + 1

    # Parse the subheading arguments:
    # .tex format: \resumeSubheading{Company/Org}{Period}{Role/Title}{Location}
    # portfolio:   title = Role, company = Org
    heading_match = re.search(
        r"\\resumeSubheading\s*\n?\{([^}]*)\}\{([^}]*)\}\s*\n?\{([^}]*)\}\{([^}]*)\}",
        block_text,
    )
    if not heading_match:
        return None

    # arg1 = company/org, arg2 = period, arg3 = role/title, arg4 = location
    company = _strip_latex(heading_match.group(1))
    period = _strip_latex(heading_match.group(2))
    title = _strip_latex(heading_match.group(3))
    location = _strip_latex(heading_match.group(4))

    # Parse bullet items using brace-counting (handles nested braces like \textbf{})
    accomplishments: list[str] = []
    for item_content in _extract_resume_items(block_text):
        text = _strip_latex(item_content)
        # Remove trailing period if present (portfolio style omits them)
        text = text.rstrip(".")
        accomplishments.append(text)

    return {
        "title": title,
        "company": company,
        "period": period,
        "location": location,
        "accomplishments": accomplishments,
        "_end_line": end_line,
    }


def _extract_resume_items(block_text: str) -> list[str]:
    """Extract \resumeItem{} contents handling nested braces."""
    items = []
    # Find all occurrences of \resumeItem{
    idx = 0
    while True:
        idx = block_text.find(r"\resumeItem{", idx)
        if idx == -1:
            break
        
        # We found "\resumeItem{", now we need to find the matching closing brace
        brace_start = idx + len(r"\resumeItem{")
        depth = 1
        end_idx = -1
        for i in range(brace_start, len(block_text)):
            if block_text[i] == '{':
                depth += 1
            elif block_text[i] == '}':
                depth -= 1
                if depth == 0:
                    end_idx = i
                    break
        
        if end_idx != -1:
            items.append(block_text[brace_start:end_idx])
            idx = end_idx + 1
        else:
            # If we didn't find a matching brace, just increment to avoid infinite loop
            idx += 1
            
    return items
# Parse .tex Projects section  (active + commented-out entries)
# ---------------------------------------------------------------------------

def parse_projects_section(tex_text: str) -> list[dict]:
    """Parse the Projects section, including commented-out entries."""
    proj_start = tex_text.find(r"\section{Projects}")
    if proj_start == -1:
        print("Warning: No Projects section found in .tex")
        return []

    proj_end_match = re.search(
        r"\\section\{(?!Projects)", tex_text[proj_start + 1:]
    )
    if proj_end_match:
        proj_end = proj_start + 1 + proj_end_match.start()
    else:
        proj_end = tex_text.find(r"\end{document}", proj_start)
        if proj_end == -1:
            proj_end = len(tex_text)

    section = tex_text[proj_start:proj_end]
    lines = section.split("\n")

    entries: list[dict] = []
    i = 0

    while i < len(lines):
        line = lines[i].rstrip("\r")
        raw = line.lstrip()

        is_commented = raw.startswith("%")
        uncommented = _uncomment_line(line).strip() if is_commented else raw

        if r"\resumeProjectHeading" in uncommented:
            entry = _parse_project_block(lines, i, is_commented)
            if entry:
                entry["commented"] = is_commented
                entries.append(entry)
                i = entry.pop("_end_line", i + 1)
                continue

        i += 1

    return entries


def _parse_project_block(
    lines: list[str], start: int, is_commented: bool
) -> Optional[dict]:
    """Parse a \\resumeProjectHeading block."""
    block_lines: list[str] = []
    i = start

    while i < len(lines):
        raw = lines[i].rstrip("\r")
        uncommented = _uncomment_line(raw).strip() if is_commented else raw.strip()
        block_lines.append(uncommented)

        if r"\resumeItemListEnd" in uncommented:
            break
        if i > start + 1 and r"\resumeProjectHeading" in uncommented:
            break
        i += 1

    block_text = "\n".join(block_lines)
    end_line = i + 1

    # Extract project name
    name_match = re.search(r"\\textbf\{(?:\\href\{[^}]*\}\{)?([^}]*)\}?\}", block_text)
    if not name_match:
        return None
    name = name_match.group(1).strip()

    # Extract GitHub URL
    url_match = re.search(r"\\href\{(https?://[^}]*)\}", block_text)
    url = url_match.group(1) if url_match else ""

    # Extract tech stack from \emph{...}
    tech_match = re.search(r"\\emph\{([^}]*)\}", block_text)
    tech = tech_match.group(1) if tech_match else ""

    # Parse bullet items
    accomplishments: list[str] = []
    for item_match in re.finditer(r"\\resumeItem\{(.+?)\}(?:\s*$)", block_text, re.MULTILINE):
        text = _strip_latex(item_match.group(1))
        text = text.rstrip(".")
        accomplishments.append(text)

    # Detect award in first bullet
    award = ""
    for acc in accomplishments:
        award_match = re.match(r"Awarded\s+(.+?)(?:\s+for\b|\s+out\b)", acc)
        if award_match:
            award = award_match.group(1)
            break

    return {
        "name": name,
        "url": url,
        "tech": tech,
        "accomplishments": accomplishments,
        "award": award,
        "_end_line": end_line,
    }


# ---------------------------------------------------------------------------
# Normalize company/project names for matching
# ---------------------------------------------------------------------------

def normalize(name: str) -> str:
    """Lowercase, strip non-alphanumeric for fuzzy matching."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


# ---------------------------------------------------------------------------
# Merge experience entries into experience.ts
# ---------------------------------------------------------------------------

def read_ts_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def merge_experiences(
    tex_entries: list[dict],
    ts_text: str,
) -> str:
    """Update experience.ts entries from .tex, preserving fields like icon, tags, category."""

    # Parse existing TS entries to know what's there
    # We'll do targeted replacements rather than full regeneration
    # to preserve icons, tags, categories, and ordering

    for tex_entry in tex_entries:
        company_norm = normalize(tex_entry["company"])

        # Find matching entry in TS by company name
        # Pattern: company: '...'  (match the value)
        pattern = re.compile(
            r"(company:\s*')([^']*)('" + r")",
            re.MULTILINE,
        )
        match_found = False
        for m in pattern.finditer(ts_text):
            existing_company = m.group(2)
            if normalize(existing_company) == company_norm:
                match_found = True
                # Update title
                ts_text = _update_string_field(
                    ts_text, existing_company, "title", tex_entry["title"]
                )
                # Update period
                ts_text = _update_string_field(
                    ts_text, existing_company, "period", tex_entry["period"]
                )
                # Update location
                ts_text = _update_string_field(
                    ts_text, existing_company, "location", tex_entry["location"]
                )
                # Update accomplishments
                ts_text = _update_accomplishments(
                    ts_text, existing_company, tex_entry["accomplishments"]
                )
                break

        if not match_found:
            # New entry - append before the closing ]
            new_entry = _build_new_experience_entry(tex_entry)
            ts_text = _append_to_array(ts_text, "experiences", new_entry)
            print(f"  Added new experience: {tex_entry['company']}")

    return ts_text


def _find_entry_block(ts_text: str, company: str) -> tuple[int, int] | None:
    """Find the { ... } block for a given company in the TS text."""
    pattern = re.compile(r"company:\s*'" + re.escape(company) + r"'")
    m = pattern.search(ts_text)
    if not m:
        return None

    # Walk backwards to find the opening {
    open_brace = ts_text.rfind("{", 0, m.start())
    if open_brace == -1:
        return None

    # Walk forward to find the matching closing }
    depth = 0
    for i in range(open_brace, len(ts_text)):
        if ts_text[i] == "{":
            depth += 1
        elif ts_text[i] == "}":
            depth -= 1
            if depth == 0:
                return (open_brace, i + 1)

    return None


def _update_string_field(
    ts_text: str, company: str, field: str, new_value: str
) -> str:
    """Update a string field within the entry for `company`."""
    block = _find_entry_block(ts_text, company)
    if not block:
        return ts_text

    start, end = block
    entry_text = ts_text[start:end]

    # Match field: '...'
    pattern = re.compile(
        r"(" + re.escape(field) + r":\s*')([^']*)('" + r")"
    )
    new_entry = pattern.sub(
        lambda m: m.group(1) + new_value + m.group(3),
        entry_text,
        count=1,
    )

    return ts_text[:start] + new_entry + ts_text[end:]


def _update_accomplishments(
    ts_text: str, company: str, new_accomplishments: list[str]
) -> str:
    """Replace the accomplishments array for a given company."""
    if not new_accomplishments:
        return ts_text

    block = _find_entry_block(ts_text, company)
    if not block:
        return ts_text

    start, end = block
    entry_text = ts_text[start:end]

    # Find accomplishments: [ ... ]
    acc_match = re.search(
        r"(accomplishments:\s*\[)([\s\S]*?)(\])", entry_text
    )
    if not acc_match:
        # Need to add accomplishments field - insert before tags or closing }
        indent = "      "
        acc_lines = [f"{indent}'{a}'," for a in new_accomplishments]
        acc_block = f"    accomplishments: [\n" + "\n".join(acc_lines) + f"\n    ],\n"
        # Insert before the last line (closing })
        insert_pos = entry_text.rfind(",\n")
        if insert_pos == -1:
            insert_pos = entry_text.rfind("\n}")
        if insert_pos != -1:
            new_entry = entry_text[:insert_pos + 2] + acc_block + entry_text[insert_pos + 2:]
        else:
            return ts_text
    else:
        # Replace existing accomplishments
        indent = "      "
        acc_lines = [f"{indent}'{_escape_ts_string(a)}'," for a in new_accomplishments]
        new_acc = acc_match.group(1) + "\n" + "\n".join(acc_lines) + "\n    " + acc_match.group(3)
        new_entry = entry_text[: acc_match.start()] + new_acc + entry_text[acc_match.end() :]

    return ts_text[:start] + new_entry + ts_text[end:]


def _escape_ts_string(s: str) -> str:
    """Escape single quotes for TS string literals."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def _build_new_experience_entry(entry: dict) -> str:
    """Build a new experience.ts entry block."""
    lines = ["  {"]
    lines.append(f"    title: '{_escape_ts_string(entry['title'])}',")
    lines.append(f"    company: '{_escape_ts_string(entry['company'])}',")
    lines.append(f"    iconLabel: '{_escape_ts_string(_make_icon_label(entry['company']))}',")
    lines.append(f"    location: '{_escape_ts_string(entry['location'])}',")
    lines.append(f"    period: '{_escape_ts_string(entry['period'])}',")
    lines.append(f"    category: 'engineer',")

    if entry.get("accomplishments"):
        lines.append("    accomplishments: [")
        for acc in entry["accomplishments"]:
            lines.append(f"      '{_escape_ts_string(acc)}',")
        lines.append("    ],")

    lines.append("    tags: [],")
    lines.append("  },")
    return "\n".join(lines)


def _make_icon_label(company: str) -> str:
    """Generate a short icon label from company name."""
    words = company.split()
    if len(words) == 1:
        return company[:4].upper()
    return "".join(w[0] for w in words if w[0].isupper())[:4] or company[:4].upper()


# ---------------------------------------------------------------------------
# Merge project entries into projects.ts
# ---------------------------------------------------------------------------

def merge_projects(
    tex_entries: list[dict],
    ts_text: str,
) -> str:
    """Update projects.ts entries from .tex, preserving existing tags."""

    for tex_entry in tex_entries:
        name_norm = normalize(tex_entry["name"])

        # Also try matching by URL
        url_norm = normalize(tex_entry.get("url", ""))

        match_found = False

        # Try name match first
        pattern = re.compile(r"name:\s*'([^']*)'", re.MULTILINE)
        for m in pattern.finditer(ts_text):
            existing_name = m.group(1)
            if normalize(existing_name) == name_norm:
                match_found = True
                ts_text = _update_project_fields(ts_text, existing_name, tex_entry)
                break

        # Try URL match if name didn't match
        if not match_found and url_norm:
            url_pattern = re.compile(r"url:\s*'([^']*)'", re.MULTILINE)
            for m in url_pattern.finditer(ts_text):
                existing_url = m.group(1)
                if normalize(existing_url) == url_norm:
                    # Find the name for this entry
                    block = _find_project_block_by_url(ts_text, existing_url)
                    if block:
                        match_found = True
                        name_m = re.search(r"name:\s*'([^']*)'", ts_text[block[0]:block[1]])
                        if name_m:
                            ts_text = _update_project_fields(
                                ts_text, name_m.group(1), tex_entry
                            )
                    break

        if not match_found:
            new_entry = _build_new_project_entry(tex_entry)
            ts_text = _append_to_array(ts_text, "projects", new_entry)
            print(f"  Added new project: {tex_entry['name']}")

    return ts_text


def _find_project_block(ts_text: str, name: str) -> tuple[int, int] | None:
    """Find the { ... } block for a given project name."""
    pattern = re.compile(r"name:\s*'" + re.escape(name) + r"'")
    m = pattern.search(ts_text)
    if not m:
        return None

    open_brace = ts_text.rfind("{", 0, m.start())
    if open_brace == -1:
        return None

    depth = 0
    for i in range(open_brace, len(ts_text)):
        if ts_text[i] == "{":
            depth += 1
        elif ts_text[i] == "}":
            depth -= 1
            if depth == 0:
                return (open_brace, i + 1)
    return None


def _find_project_block_by_url(ts_text: str, url: str) -> tuple[int, int] | None:
    """Find the { ... } block for a given project URL."""
    pattern = re.compile(r"url:\s*'" + re.escape(url) + r"'")
    m = pattern.search(ts_text)
    if not m:
        return None

    open_brace = ts_text.rfind("{", 0, m.start())
    if open_brace == -1:
        return None

    depth = 0
    for i in range(open_brace, len(ts_text)):
        if ts_text[i] == "{":
            depth += 1
        elif ts_text[i] == "}":
            depth -= 1
            if depth == 0:
                return (open_brace, i + 1)
    return None


def _update_project_fields(ts_text: str, name: str, tex_entry: dict) -> str:
    """Update a project's fields in TS text."""
    block = _find_project_block(ts_text, name)
    if not block:
        return ts_text

    start, end = block
    entry_text = ts_text[start:end]

    # Update tech
    if tex_entry.get("tech"):
        tech_pattern = re.compile(r"(tech:\s*')([^']*)('" + r")")
        entry_text = tech_pattern.sub(
            lambda m: m.group(1) + tex_entry["tech"] + m.group(3),
            entry_text,
            count=1,
        )

    # Update accomplishments
    if tex_entry.get("accomplishments"):
        acc_match = re.search(
            r"(accomplishments:\s*\[)([\s\S]*?)(\])", entry_text
        )
        if acc_match:
            indent = "      "
            acc_lines = [f"{indent}'{_escape_ts_string(a)}'," for a in tex_entry["accomplishments"]]
            new_acc = (
                acc_match.group(1) + "\n" + "\n".join(acc_lines) + "\n    " + acc_match.group(3)
            )
            entry_text = entry_text[: acc_match.start()] + new_acc + entry_text[acc_match.end() :]

    # Update award
    if tex_entry.get("award"):
        award_pattern = re.compile(r"(award:\s*')([^']*)('" + r")")
        if award_pattern.search(entry_text):
            entry_text = award_pattern.sub(
                lambda m: m.group(1) + _escape_ts_string(tex_entry["award"]) + m.group(3),
                entry_text,
                count=1,
            )

    # Update URL
    if tex_entry.get("url"):
        url_pattern = re.compile(r"(url:\s*')([^']*)('" + r")")
        entry_text = url_pattern.sub(
            lambda m: m.group(1) + tex_entry["url"] + m.group(3),
            entry_text,
            count=1,
        )

    return ts_text[:start] + entry_text + ts_text[end:]


def _build_new_project_entry(entry: dict) -> str:
    """Build a new projects.ts entry block."""
    lines = ["  {"]
    lines.append(f"    name: '{_escape_ts_string(entry['name'])}',")
    lines.append(f"    url: '{entry.get('url', '')}',")
    lines.append(f"    tech: '{_escape_ts_string(entry.get('tech', ''))}',")

    if entry.get("award"):
        lines.append(f"    award: '{_escape_ts_string(entry['award'])}',")

    lines.append("    accomplishments: [")
    for acc in entry.get("accomplishments", []):
        lines.append(f"      '{_escape_ts_string(acc)}',")
    lines.append("    ],")
    lines.append("    tags: [],")
    lines.append("  },")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Array append helper
# ---------------------------------------------------------------------------

def _append_to_array(ts_text: str, array_name: str, new_block: str) -> str:
    """Append a new entry block before the closing ] of the named array."""
    # Find the array
    pattern = re.compile(
        r"export\s+const\s+" + re.escape(array_name) + r"\s*[:\s=]",
    )
    m = pattern.search(ts_text)
    if not m:
        return ts_text

    # Find the opening [
    open_bracket = ts_text.find("[", m.end())
    if open_bracket == -1:
        return ts_text

    # Find matching ]
    depth = 0
    close_bracket = -1
    for i in range(open_bracket, len(ts_text)):
        if ts_text[i] == "[":
            depth += 1
        elif ts_text[i] == "]":
            depth -= 1
            if depth == 0:
                close_bracket = i
                break

    if close_bracket == -1:
        return ts_text

    return ts_text[:close_bracket] + new_block + "\n" + ts_text[close_bracket:]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    resume_file = Path("gerard_consuelo_resume.tex")
    if not resume_file.exists():
        raise FileNotFoundError(f"Resume file not found: {resume_file}")

    portfolio_dir = find_portfolio_dir()
    experience_ts = portfolio_dir / "src" / "data" / "experience.ts"
    projects_ts = portfolio_dir / "src" / "data" / "projects.ts"

    resume_text = resume_file.read_text(encoding="utf-8")

    # --- Sync Experience ---
    print("=== Syncing Experience ===")
    tex_experiences = parse_experience_section(resume_text)
    print(f"Found {len(tex_experiences)} experience entries in .tex "
          f"({sum(1 for e in tex_experiences if e.get('commented'))} commented)")

    if experience_ts.exists():
        ts_exp_text = read_ts_file(experience_ts)
        updated_exp = merge_experiences(tex_experiences, ts_exp_text)
        if updated_exp != ts_exp_text:
            experience_ts.write_text(updated_exp, encoding="utf-8")
            print("experience.ts updated.")
        else:
            print("experience.ts already up to date.")
    else:
        print(f"Warning: {experience_ts} not found, skipping experience sync.")

    # --- Sync Projects ---
    print("\n=== Syncing Projects ===")
    tex_projects = parse_projects_section(resume_text)
    print(f"Found {len(tex_projects)} project entries in .tex "
          f"({sum(1 for p in tex_projects if p.get('commented'))} commented)")

    if projects_ts.exists():
        ts_proj_text = read_ts_file(projects_ts)
        updated_proj = merge_projects(tex_projects, ts_proj_text)
        if updated_proj != ts_proj_text:
            projects_ts.write_text(updated_proj, encoding="utf-8")
            print("projects.ts updated.")
        else:
            print("projects.ts already up to date.")
    else:
        print(f"Warning: {projects_ts} not found, skipping projects sync.")

    print("\nSync complete.")


if __name__ == "__main__":
    main()
