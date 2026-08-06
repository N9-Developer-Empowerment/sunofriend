export const links = {
  email: "mailto:hello@sunofriend.com",
  contact: "https://sunofriend.com/contact/",
  privacy: "https://sunofriend.com/privacy/",
  repo: "https://github.com/N9-Developer-Empowerment/sunofriend",
  securityReport:
    "https://github.com/N9-Developer-Empowerment/sunofriend/security/advisories/new",
  skill:
    "https://github.com/N9-Developer-Empowerment/sunofriend/tree/main/skills/sunofriend",
  rawSkill:
    "https://raw.githubusercontent.com/N9-Developer-Empowerment/sunofriend/main/skills/sunofriend/SKILL.md",
  interfaceContract:
    "https://raw.githubusercontent.com/N9-Developer-Empowerment/sunofriend/main/skills/sunofriend/references/interface-contract.md",
  gettingStarted:
    "https://github.com/N9-Developer-Empowerment/sunofriend/blob/main/docs/GETTING_STARTED.md",
  separationDeveloperGuide:
    "https://github.com/N9-Developer-Empowerment/sunofriend/blob/main/docs/SEPARATION_DEVELOPER_PREVIEW.md",
  stemGuide:
    "https://github.com/N9-Developer-Empowerment/sunofriend/blob/main/docs/STEMS.md",
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

export type ProviderLocation = "Cloud" | "Local" | "Cloud + local option";

export type StemProvider = {
  name: string;
  href: string;
  location: ProviderLocation;
  usefulFor: string;
  boundary: string;
};

export const stemProviders: readonly StemProvider[] = [
  {
    name: "Moises",
    href: "https://moises.ai/",
    location: "Cloud",
    usefulFor:
      "Detailed separation, including narrower drum parts on eligible plans.",
    boundary:
      "Your audio is uploaded. Check the current plan, export format, retention and privacy terms before using private music.",
  },
  {
    name: "BandLab Splitter",
    href: "https://www.bandlab.com/splitter",
    location: "Cloud",
    usefulFor:
      "A low-friction first experiment with separated parts and MIDI export.",
    boundary:
      "Processing is online and some categories require membership. Check the current terms before uploading.",
  },
  {
    name: "Fadr",
    href: "https://fadr.com/",
    location: "Cloud",
    usefulFor:
      "Stems alongside MIDI, chords, key and tempo, with paid refinements.",
    boundary:
      "Review the current privacy and rights terms, especially for unreleased or confidential audio.",
  },
  {
    name: "Suno stem separation",
    href: "https://help.suno.com/en/articles/12702337",
    location: "Cloud",
    usefulFor:
      "Exporting parts from material already created in, or legitimately uploaded to, a Suno workflow.",
    boundary:
      "A paid cloud feature. Confirm upload rights; category labels and requested splits are estimates.",
  },
  {
    name: "LALAL.AI",
    href: "https://www.lalal.ai/stem-splitter/",
    location: "Cloud + local option",
    usefulFor:
      "Target-plus-complement separation and a range of instrument categories.",
    boundary:
      "The desktop app uses cloud processing by default. Check whether your plan and chosen model actually process on-device.",
  },
  {
    name: "Logic Pro Stem Splitter",
    href: "https://support.apple.com/en-gb/guide/logicpro/lgcp61bae908/mac",
    location: "Local",
    usefulFor:
      "On-device broad separation on supported Apple-silicon Macs.",
    boundary:
      "Requires Logic Pro and supported Apple hardware. It is not available inside GarageBand.",
  },
  {
    name: "RipX DAW",
    href: "https://hitnmix.com/",
    location: "Local",
    usefulFor:
      "Desktop separation, note-level inspection and MIDI export.",
    boundary:
      "Commercial software. Check current macOS support and process only audio you are authorised to use.",
  },
] as const;

export type GlossaryEntry = {
  term: string;
  short: string;
  explanation: string;
};

export const glossaryEntries: readonly GlossaryEntry[] = [
  {
    term: "Finished mix",
    short: "The complete stereo song people normally hear.",
    explanation:
      "Its voices, instruments, effects and mastering have already been combined, so the original parts cannot be recovered perfectly from it.",
  },
  {
    term: "Multitracks",
    short: "The discrete tracks from the original recording or production.",
    explanation:
      "Examples include a kick microphone, snare microphone, bass DI, piano and lead vocal. They are usually cleaner and narrower than stems.",
  },
  {
    term: "Stem",
    short: "A synchronized grouped part of a song.",
    explanation:
      "A stem is usually a submix such as all drums, all keys or all backing vocals. It can contain several instruments, performers, microphones and effects.",
  },
  {
    term: "AI-separated stem",
    short: "A model's estimate of one category from a finished mix.",
    explanation:
      "It is useful source material, but it is not the lost original studio track. Bleed, holes, muffling and watery artefacts can remain.",
  },
  {
    term: "Broad stem",
    short: "A large category such as drums, vocals, keys or other.",
    explanation:
      "Broad stems are convenient but often contain several musical parts with different pitches, rhythms and sounds.",
  },
  {
    term: "Refined stem or sub-stem",
    short: "A narrower child made from a broad stem.",
    explanation:
      "For example, drums may be refined into kick, snare, hats, toms, cymbals and other percussion. Refinement is another estimate and may add artefacts.",
  },
  {
    term: "Bleed or leakage",
    short: "Sound from one part that remains in another stem.",
    explanation:
      "Examples include vocals audible in keys or cymbals audible in snare. Leakage can produce false MIDI notes.",
  },
  {
    term: "Residual or complement",
    short: "Everything a separator did not assign to its target.",
    explanation:
      "A residual is not necessarily one coherent instrument. A file named other may contain guitars, keyboards, strings, effects and artefacts together.",
  },
  {
    term: "MIDI",
    short: "Editable note and performance instructions, not recorded sound.",
    explanation:
      "MIDI can describe pitch, timing, duration, velocity and controls. It does not contain words, a singer's voice, instrument texture or the original effects.",
  },
  {
    term: "Instrument or sample bundle",
    short: "Sounds used to play MIDI notes.",
    explanation:
      "A suitable instrument helps a MIDI interpretation resemble the source, but an instrument bundle is not itself a stem.",
  },
  {
    term: "Lossless and lossy audio",
    short: "Two ways audio files preserve or discard signal detail.",
    explanation:
      "WAV, AIFF and FLAC are commonly lossless. MP3 and AAC discard information to reduce size. Converting MP3 to WAV does not restore that discarded detail.",
  },
] as const;

export const stemBoundary = {
  songProjectInputToday: "synchronised, top-level WAV stems",
  sourceImportToday: "one authorised local audio asset at a time",
  sourceFolderImportToday:
    "2–64 already-separated, synchronized top-level audio parts",
  sourceImportOutput:
    "an immutable original copy, canonical PCM24 WAV, receipt and source-project manifest",
  sourceFolderImportOutput:
    "immutable originals, canonical top-level PCM24 WAV stems, per-source and aggregate receipts, and one source-project manifest",
  sourceDoctorCommand: "sunofriend source-doctor",
  sourceImportCommand:
    "sunofriend source-import SOURCE --out-dir FRESH --plan",
  sourceImportExecCommand:
    "sunofriend source-import SOURCE --out-dir FRESH",
  sourceFolderImportCommand:
    "sunofriend source-import-folder SOURCE_FOLDER --out-dir FRESH --rights-category CATEGORY --plan",
  sourceFolderImportExecCommand:
    "sunofriend source-import-folder SOURCE_FOLDER --out-dir FRESH --rights-category CATEGORY",
  builtInSeparationToday: true,
  websiteUploadToday: false,
  folderImportToday: true,
  crossFileOriginComparisonToday: true,
  crossFileAlignmentToday: false,
  directNonWavProjectToday: false,
  nextPlannedInputWork:
    "composite-role handling followed by a measured local-separation bake-off",
} as const;

export const separationResearch = {
  status:
    "public two-stem alpha with an explicit SCNet core-four public opt-in preview",
  publicProductRouteAvailable: true,
  workingPrivateScope:
    "one authorised finished mix to broad vocals, broad instrumental and a diagnostic reconstruction by default; the installed SCNet profile adds an explicit local vocals/drums/bass/grouped-other public opt-in preview",
  downstreamProof:
    "stems the musician finds useful can enter Sunofriend's existing MIDI, interpretation WAV and starter ZIP workflow as a later explicit step",
  evidenceScope:
    "three source-distinct private evidence chains with complete-song and boundary listening, plus a public end-to-end smoke test",
  humanAuthority:
    "human listening decides usefulness and later promotion; preview admission checks licensing, privacy, integrity, timing, resources and reconstruction only",
  developmentLoop: [
    "state one narrow musical or engineering question",
    "seal authorised inputs and run one bounded local experiment",
    "check machine evidence without treating a score as musical taste",
    "bind an explicit human listening review to the exact result",
    "publish after objective gates while preserving useful, poor and inconclusive musical evidence",
  ],
  developerDoctorCommand: ".venv/bin/sunofriend-separate doctor",
  setupPlanCommand: "scripts/setup-separation-alpha-macos.sh --plan",
  separationPlanCommand:
    ".venv/bin/sunofriend-separate separate SONG --out FRESH --rights-category owned",
  feedbackImpact:
    "reports can repair instructions, expose portability gaps and motivate the next bounded experiment; they never select a model or musical default automatically",
  openGates: [
    "collect real-world usefulness feedback without disabling the functioning preview",
    "review after 30 days or 10 valid reports, whichever occurs first",
    "qualify one bounded Studio challenger when repeated poor feedback warrants it",
    "keep 16 GiB and other Apple-silicon classes accessible but clearly unverified",
  ],
  feedbackBoundary:
    "Copy text-only scope/profile-bound observations into the existing GitHub form. Do not attach private audio, stems, review JSON, filenames or metadata. Poor feedback records limitations; it does not disable the last functioning profile.",
} as const;

export const skillInstallPrompt = `Use $skill-installer to install the official Sunofriend skill from:
https://github.com/N9-Developer-Empowerment/sunofriend/tree/main/skills/sunofriend

Do not install the Sunofriend app or any audio dependencies yet. Tell me when the skill is available, then stop.`;

export const newcomerPrompt = `Use $sunofriend to help me try Sunofriend on this Mac.

Use the installed skill, not a generic audio workflow. Start by inspecting what is already available and explain what you would need to change. If setup is needed, ask before preparing the source, show me the exact prepared commit, then ask again before installing that reviewed commit. Then offer me four routes:
1. experimentally separate one authorised finished song locally on a supported Apple-silicon Mac;
2. use my existing authorised separated audio parts, preparing supported formats locally when needed;
3. help me obtain or export authorised stems;
4. run the built-in copyright-safe demo in a fresh folder, then show me what it made.

For my first result, use the skill's beginner-safe route: the agent-oriented create command when I have stems, the demo command when I do not, or Simple / Make my song when I am operating the TUI myself. Keep my audio local. Label automatic output as unreviewed. Do not call the WAV an exact reconstruction or a release master.

If you cannot access local files or run commands, do not pretend that you can. Explain that hands-on setup needs Codex with local workspace access, or give me manual instructions only.`;

export const demoPrompt = `Use $sunofriend to help me try Sunofriend without using any personal music.

Use the installed skill. Explain what you will check and ask before changing my Mac. Then run the built-in copyright-safe demo with:
sunofriend demo --out-dir FRESH

Choose a fresh output folder with me. Do not install optional AI models just for this demo. When it finishes, show me the synthetic stems, individual MIDI, combined MIDI, balanced MIDI-derived WAV, receipt and ZIP. Explain that the output is automatic and unreviewed, not an exact reconstruction or release master.

If you cannot access local files or run commands, do not pretend that you can. Give me manual guidance or tell me to continue in Codex with local workspace access.`;

export const agentSummary =
  "Sunofriend is a local-first, MacBook-tested alpha. On Apple-silicon macOS its opt-in experimental separator defaults to broad vocals and complementary instrumental. Its installed, hash-pinned SCNet-large profile now adds an explicit public opt-in vocals/drums/bass/grouped-other preview after finite offline canaries and catastrophic-output listening checks passed. The first verified class is a 36 GB M3 Max; other Apple-silicon classes remain accessible but unverified. It also prepares existing stems, then turns useful canonical WAV parts into editable MIDI, a balanced MIDI-derived song-interpretation WAV and a starter ZIP. Automatic results stay explicitly unreviewed; Studio preserves candidates for explicit listening and choice.";
