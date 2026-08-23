import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / ".agents" / "skills"
SKILL_NAMES = {
    "investment-analysis", "company-data", "expectations", "valuation", "portfolio",
    "macro-context",
    "investor-policy",
}


def test_only_public_skills_are_installed():
    installed = {path.parent.name for path in SKILLS_DIR.glob("*/SKILL.md")}
    assert installed == SKILL_NAMES


def test_every_skill_has_frontmatter_and_current_cli_paths():
    combined = []
    for name in SKILL_NAMES:
        text = (SKILLS_DIR / name / "SKILL.md").read_text()
        assert text.startswith("---\n")
        frontmatter = text[4:text.index("\n---", 4)]
        assert f"name: {name}" in frontmatter
        assert "description:" in frontmatter
        combined.append(text)

    all_text = "\n".join(combined)
    for command_group in ("data", "valuation", "analysis", "portfolio"):
        assert f"thesis {command_group}" in all_text


def test_claude_compatibility_symlink_resolves_to_canonical_skills():
    claude_skills = REPO_ROOT / ".claude" / "skills"
    assert claude_skills.is_symlink()
    assert claude_skills.resolve() == SKILLS_DIR.resolve()


def test_agents_md_references_every_public_skill():
    agents_md = (REPO_ROOT / "AGENTS.md").read_text()
    for name in SKILL_NAMES:
        assert name in agents_md


def test_investor_policy_example_is_small_and_valid_json():
    policy = json.loads((REPO_ROOT / "config" / "investor-policy.example.json").read_text())
    assert set(policy) == {
        "base_currency", "investment_horizon_years", "emergency_fund_months",
        "max_single_position_pct", "max_sector_pct", "max_portfolio_drawdown_pct",
    }
