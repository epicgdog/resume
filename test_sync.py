"""Dry-run test: verify the sync script parses the .tex file correctly."""
import sys
import json
sys.path.insert(0, "scripts")

from sync_experience import parse_experience_section, parse_projects_section
from pathlib import Path

resume = Path("gerard_consuelo_resume.tex").read_text(encoding="utf-8")

print("=" * 60)
print("EXPERIENCE ENTRIES")
print("=" * 60)
for entry in parse_experience_section(resume):
    status = "[COMMENTED]" if entry.get("commented") else "[ACTIVE]"
    print(f"\n{status} {entry['title']} @ {entry['company']}")
    print(f"  Period: {entry['period']}")
    print(f"  Location: {entry['location']}")
    for bullet in entry.get("accomplishments", []):
        print(f"  • {bullet}")

print("\n" + "=" * 60)
print("PROJECT ENTRIES")
print("=" * 60)
for entry in parse_projects_section(resume):
    status = "[COMMENTED]" if entry.get("commented") else "[ACTIVE]"
    print(f"\n{status} {entry['name']}")
    print(f"  URL: {entry.get('url', 'N/A')}")
    print(f"  Tech: {entry.get('tech', 'N/A')}")
    if entry.get("award"):
        print(f"  Award: {entry['award']}")
    for bullet in entry.get("accomplishments", []):
        print(f"  • {bullet}")
