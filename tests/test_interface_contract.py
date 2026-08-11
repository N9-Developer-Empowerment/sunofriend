from __future__ import annotations

import argparse
import json
import unittest
from pathlib import Path

from sunofriend.cli import _COMMANDS, build_parser
from sunofriend.interface_contract import (
    DIRECT_TUI_COMMANDS,
    INTERFACE_CONTRACT_VERSION,
    PUBLIC_COMMAND_GROUPS,
    PUBLIC_COMMANDS,
    command_category,
    render_skill_interface_reference,
)
from sunofriend.product_contract import PRODUCT_SUMMARY


class InterfaceContractTests(unittest.TestCase):
    def test_registry_is_unique_and_matches_every_cli_subcommand(self) -> None:
        flattened = [
            command
            for commands in PUBLIC_COMMAND_GROUPS.values()
            for command in commands
        ]
        parser_commands = _parser_commands(build_parser())

        self.assertEqual(len(flattened), len(set(flattened)))
        self.assertEqual(set(flattened), set(PUBLIC_COMMANDS))
        self.assertEqual(set(PUBLIC_COMMANDS), set(_COMMANDS))
        self.assertEqual(set(PUBLIC_COMMANDS), parser_commands)
        for command in PUBLIC_COMMANDS:
            self.assertIn(command_category(command), PUBLIC_COMMAND_GROUPS)
        self.assertLessEqual(DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS)

    def test_canonical_skill_and_agent_surfaces_are_synchronised(self) -> None:
        root = Path(__file__).resolve().parents[1]
        skill = root / "skills" / "sunofriend" / "SKILL.md"
        agents = root / ".agents" / "skills" / "sunofriend"
        claude = root / ".claude" / "skills" / "sunofriend"
        openai = root / "skills" / "sunofriend" / "agents" / "openai.yaml"
        advanced = (
            root / "skills" / "sunofriend" / "references" / "advanced-operations.md"
        )

        self.assertEqual(agents.resolve(), skill.parent.resolve())
        self.assertEqual(claude.resolve(), skill.parent.resolve())
        skill_text = skill.read_text(encoding="utf-8")
        openai_text = openai.read_text(encoding="utf-8")
        advanced_text = advanced.read_text(encoding="utf-8")
        self.assertIn(
            f"sunofriend-interface-contract: {INTERFACE_CONTRACT_VERSION}",
            skill_text,
        )
        self.assertIn(
            f"sunofriend-interface-contract: {INTERFACE_CONTRACT_VERSION}",
            advanced_text,
        )
        self.assertIn("sunofriend tui", skill_text)
        self.assertIn("TUI", openai_text)
        self.assertIn("Workbench", openai_text)

    def test_checked_in_skill_command_reference_matches_registry(self) -> None:
        root = Path(__file__).resolve().parents[1]
        reference = (
            root / "skills" / "sunofriend" / "references" / "interface-contract.md"
        )

        self.assertEqual(
            reference.read_text(encoding="utf-8"),
            render_skill_interface_reference(),
        )

    def test_agent_capabilities_publish_the_current_interface_version(self) -> None:
        root = Path(__file__).resolve().parents[1]
        capabilities = json.loads(
            (root / "website" / "public" / "agent-capabilities.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(
            capabilities["interface_contract_version"],
            INTERFACE_CONTRACT_VERSION,
        )

    def test_cli_and_generated_reference_present_the_paired_product_goal(
        self,
    ) -> None:
        parser = build_parser()
        reference = render_skill_interface_reference()

        self.assertEqual(parser.description, PRODUCT_SUMMARY)
        self.assertIn("Editable MIDI arrangement", reference)
        self.assertIn("MIDI-derived song-interpretation WAV", reference)
        self.assertIn("Simple / Make my song", reference)
        self.assertIn("automatic and", reference)
        self.assertIn("sunofriend tui --mode studio", reference)
        self.assertIn("visible Simple/Studio", reference)
        self.assertIn("without starting work", reference)
        self.assertIn("not waveform reconstruction", reference)
        self.assertIn("never imply a preference", reference)

    def test_generated_reference_keeps_public_and_private_separation_lanes_distinct(
        self,
    ) -> None:
        reference = render_skill_interface_reference()

        self.assertIn(
            "Finished-mix separation has four deliberately distinct lanes", reference
        )
        self.assertIn("public default `broad-vocals-v1`", reference)
        self.assertIn("public explicit opt-in `core-four-stems-v1`", reference)
        self.assertIn("private research: unregistered Mega-53 synth", reference)
        self.assertIn(
            "private_review_package_recovered_model_free_resource_gate_incomplete",
            reference,
        )
        self.assertIn("Full objective qualification is false", reference)
        self.assertIn("rather than proven for it", reference)
        self.assertNotIn("The execution remains forbidden", reference)
        self.assertNotIn("The next no-effects full-song plan", reference)

    def test_active_separation_docs_record_consumed_recovery_authority(self) -> None:
        root = Path(__file__).resolve().parents[1]
        documents = (
            root / "README.md",
            root / "docs" / "FINE_STEM_FULL_SONG_PLAN.md",
            root / "docs" / "FULL_STEM_SEPARATION_PLAN.md",
            root / "docs" / "STEM_SEPARATION_ALPHA.md",
            root / "skills" / "sunofriend" / "SKILL.md",
        )

        for document in documents:
            text = document.read_text(encoding="utf-8")
            with self.subTest(document=document.name):
                self.assertIn(
                    "private_review_package_recovered_model_free_resource_gate_incomplete",
                    text,
                )
                self.assertNotIn("executor has not been authorised or run", text)
                self.assertNotIn("Execution remains blocked until", text)
                self.assertNotIn("non-executable until its exact plan hash", text)

    def test_skill_frontmatter_description_stays_within_validator_limit(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "skills" / "sunofriend" / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = text.split("---", 2)[1]
        description = next(
            line.partition(":")[2].strip()
            for line in frontmatter.splitlines()
            if line.startswith("description:")
        )
        self.assertLessEqual(len(description), 1024)


def _parser_commands(parser: argparse.ArgumentParser) -> set[str]:
    action = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    return set(action.choices)
