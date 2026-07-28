export const links = {
  repo: "https://github.com/N9-Developer-Empowerment/sunofriend",
  skill:
    "https://github.com/N9-Developer-Empowerment/sunofriend/tree/main/skills/sunofriend",
  rawSkill:
    "https://raw.githubusercontent.com/N9-Developer-Empowerment/sunofriend/main/skills/sunofriend/SKILL.md",
  interfaceContract:
    "https://raw.githubusercontent.com/N9-Developer-Empowerment/sunofriend/main/skills/sunofriend/references/interface-contract.md",
  gettingStarted:
    "https://github.com/N9-Developer-Empowerment/sunofriend/blob/main/docs/GETTING_STARTED.md",
  outOfPlace:
    "https://soundcloud.com/ezzye-1/out-of-place?si=93616bdf10d7406c838be366106c1025&utm_source=clipboard&utm_medium=text&utm_campaign=social_sharing",
  lidl:
    "https://soundcloud.com/ezzye-1/the-aisle-at-lidl?si=97cf744ff4a743bca875bec3db88024f&utm_source=clipboard&utm_medium=text&utm_campaign=social_sharing",
  lidlPack:
    "https://github.com/N9-Developer-Empowerment/sunofriend/tree/main/examples/the-aisle-at-lidl",
  firstSong:
    "https://github.com/N9-Developer-Empowerment/sunofriend/issues/new?template=beginner-first-song.yml",
  compatibility:
    "https://github.com/N9-Developer-Empowerment/sunofriend/issues/new?template=daw-ai-compatibility.yml",
  license:
    "https://github.com/N9-Developer-Empowerment/sunofriend/blob/main/LICENSE",
  brandGuide:
    "https://github.com/N9-Developer-Empowerment/sunofriend/blob/main/BRAND.md",
  hindiName:
    "https://www.hindwi.org/hindi-dictionary/meaning-of-sunnaa-2",
  sunoStemHelp: "https://help.suno.com/en/articles/12702337",
  moisesExportHelp:
    "https://help.moises.ai/hc/en-us/articles/360013691720-How-do-I-export-my-file",
};

export const skillInstallPrompt = `Use $skill-installer to install the official Sunofriend skill from:
https://github.com/N9-Developer-Empowerment/sunofriend/tree/main/skills/sunofriend

Do not install the Sunofriend app or any audio dependencies yet. Tell me when the skill is available, then stop.`;

export const newcomerPrompt = `Use $sunofriend to help me try Sunofriend on this Mac.

Use the installed skill, not a generic audio workflow. Start by inspecting what is already available and explain what you would need to change. If setup is needed, ask before preparing the source, show me the exact prepared commit, then ask again before installing that reviewed commit. Then offer me three routes:
1. use my existing authorised WAV stems;
2. help me obtain or export authorised stems (Sunofriend itself does not separate audio);
3. run the built-in copyright-safe demo in a fresh folder, then show me what it made.

For my first result, use the skill's beginner-safe route: the agent-oriented create command when I have stems, the demo command when I do not, or Simple / Make my song when I am operating the TUI myself. Keep my audio local. Label automatic output as unreviewed. Do not call the WAV an exact reconstruction or a release master.

If you cannot access local files or run commands, do not pretend that you can. Explain that hands-on setup needs Codex with local workspace access, or give me manual instructions only.`;

export const demoPrompt = `Use $sunofriend to help me try Sunofriend without using any personal music.

Use the installed skill. Explain what you will check and ask before changing my Mac. Then run the built-in copyright-safe demo with:
sunofriend demo --out-dir FRESH

Choose a fresh output folder with me. Do not install optional AI models just for this demo. When it finishes, show me the synthetic stems, individual MIDI, combined MIDI, balanced MIDI-derived WAV, receipt and ZIP. Explain that the output is automatic and unreviewed, not an exact reconstruction or release master.

If you cannot access local files or run commands, do not pretend that you can. Give me manual guidance or tell me to continue in Codex with local workspace access.`;

export const agentSummary =
  "Sunofriend is a local-first macOS alpha that turns authorised top-level WAV stems into editable MIDI, a balanced MIDI-derived song-interpretation WAV and a starter ZIP. Its focused agent create command and TUI Simple mode make an automatic, explicitly unreviewed first result. Studio preserves multiple analytical and AI candidates for explicit listening and choice.";
