# AI-assisted first song

This is the easiest current route for someone who wants to hear what
Sunofriend can do without learning its command line first.

You need a Mac and a Codex session that can work with a local folder. A normal
web chat that cannot access files or run local commands cannot install or run
Sunofriend on the Mac.

## 1. Install only the skill

Open Codex and send:

```text
Use $skill-installer to install the Sunofriend skill from
https://github.com/N9-Developer-Empowerment/sunofriend/tree/main/skills/sunofriend.
Do not install the application yet. Tell me when the skill is available.
```

The skill is a small set of instructions for the agent. Installing it is not
the same as installing the audio application and its dependencies.

If `$sunofriend` is not recognised in the next message, restart Codex once.

## 2. Let the skill guide the setup

Send:

```text
Use $sunofriend. I am new to music software. Help me choose between:
1. trying the built-in demo,
2. using stems I already have, or
3. getting stems I am allowed to process.
Explain one thing at a time. Inspect my Mac and show me an installation plan
before making system or network changes. Keep my audio local.
```

The agent should not begin with a page of shell commands. It should first ask
which journey you want, run a read-only setup inspection, translate the result
and request permission before making changes.

## 3. Choose a starting point

### Try the demo

Choose this if you have no stems or simply want to know whether the result is
useful. Sunofriend generates a small synthetic song locally, transcribes it
through the normal production path and creates the normal automatic bundle.

The demo does not use or download copyrighted music. It is deliberately small
so the first run is easier to understand.

### Use stems you already have

Give the agent the folder path. It should inventory the folder without changing
it and confirm:

- the WAV files are directly inside the folder;
- the filenames contain useful role words such as `kick`, `bass`, `keys` or
  `vocals`;
- the key and BPM are known; and
- the output will be a new folder outside the source folder.

### Get authorised stems

Sunofriend is not a stem separator. Ask the agent to check current official
provider instructions before you subscribe or export because plans and
features change.

Common routes are:

- export separate tracks from GarageBand or another DAW;
- export stems or multitracks from a generator project you are allowed to use;
- use Moises or another separator and export the separated tracks; or
- record separate parts yourself.

Use only material you own or are authorised to process. A subscription,
download button or locally available file does not by itself settle music
rights.

## 4. Review the setup plan

The installed skill includes a conservative macOS setup helper. Its default
action is inspection only. It reports:

- whether a suitable Sunofriend checkout already exists;
- whether Homebrew, Python and FluidSynth are present;
- whether the isolated Python environment is ready;
- whether the exact verified preview SoundFont is present; and
- what would be installed or downloaded.

The helper does not update or overwrite an existing checkout. It does not
install Homebrew itself. The agent must explain any missing prerequisite and
ask before changing the machine or using the network.

For a new installation there are two approvals:

1. **Prepare source:** clone only the public source, with no package or audio
   installation.
2. **Install:** review the exact 40-character Git commit and the remaining
   plan, then approve installation bound to that same commit.

The second step never fetches or switches the prepared checkout. This prevents
the code being installed from changing between review and approval.

Approve each step only if the location and changes make sense to you. You can
stop and ask what any item means.

## 5. Hear the result

For the demo or a real Simple-mode run, ask the agent to show:

1. the balanced MIDI-derived WAV;
2. `START-HERE.txt`;
3. the folder of individual MIDI parts; and
4. the ZIP.

Listen to the WAV first. It is often the quickest way to hear the simplified
rhythm, harmony and melody together.

The WAV is made from the MIDI interpretation. The original stem audio is not
mixed into it. It will not reproduce a singer's words, a synth's exact buzzing
texture, guitar effects or a finished master.

## 6. Continue in GarageBand

1. Create a GarageBand project.
2. Set its BPM to the exact value in `START-HERE.txt`.
3. Drag all individual MIDI files to the same recorded-zero project position.
4. Choose a GarageBand sound for each software-instrument track.
5. Keep quantisation off during the first comparison.

The instrument choice can change the emotional result substantially. Treat
the supplied General MIDI sounds as clear proxies, not final artistic choices.

## 7. Use Studio only when you want more control

Simple mode makes a useful automatic starting point. Studio is the deeper
route for:

- comparing multiple analytical and AI candidates;
- hearing a source stem beside each MIDI result;
- seeing waveforms and note timelines;
- saving explicit choices and feedback;
- repairing bounded note problems;
- trying instrument matches; and
- creating a reviewed GarageBand handoff.

Ask the agent to explain one Studio task at a time. There is no need to learn
the entire Workbench before making a first song.

## 8. Give useful feedback

The most valuable beginner feedback is:

- Did the agent-led setup finish without unexplained commands?
- Was it clear what would change before you approved it?
- Did the demo or stem folder produce a WAV, MIDI and ZIP?
- Did the WAV help you understand or enjoy the song?
- Did the MIDI import at the correct BPM?
- Where did you stop, hesitate or need technical help?

Use the
[beginner first-song issue form](https://github.com/N9-Developer-Empowerment/sunofriend/issues/new?template=beginner-first-song.yml).
Do not attach private stems or music you cannot redistribute.

## Manual fallback

If you prefer to understand and run every setup command yourself, follow
[Getting started](GETTING_STARTED.md). Developers can inspect the generated
[public interface contract](../skills/sunofriend/references/interface-contract.md)
and the [technical tour](TECHNICAL_TOUR.md).
