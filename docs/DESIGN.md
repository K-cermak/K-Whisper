# K-Whisper design notes

Working notes for the UI. Update them when the direction changes.

## Brief

- **Subject:** a desktop tool that turns recordings (interviews, lectures, podcasts, video) into subtitles and transcripts on the user's own computer. It only transcribes; editing subtitles is out of scope.
- **Audience:** people who need text out of audio without being speech-recognition experts: journalists, students, teachers, video editors.
- **Primary job:** drop files, pick a model and what to make, press one button, get files next to the originals. Everything else is secondary and stays out of sight until asked for.

## Direction: "caption desk"

The vocabulary comes from subtitling rather than from SaaS dashboards: caption bands, timecodes, a run bar like a transport bar. The memorable element is the **live caption band**: while a recording is transcribed, its row expands and the most recent recognized line is set like a real subtitle (light text on a dark band), with the progress running along its bottom edge. That is the one bold thing; everything around it stays quiet.

## Tokens

| Name | Light | Dark | Use |
|---|---|---|---|
| Desk | `#E9ECEF` | `#1D2125` | window background |
| Sheet | `#FFFFFF` | `#262B30` | lists, inputs, the run bar |
| Ink | `#1E2328` | `#E8EBEE` | text |
| Graphite | `#5D6670` | `#A2ABB4` | secondary text |
| Rule | `#D3D8DD` | `#3A4047` | hairlines, input borders |
| Signal blue | `#1F5FAD` | `#3A73C0` | the one primary action, progress, chosen state, focus |
| Blue tint | `#E4EDF9` | `#233B5C` | selected rows and segments, menu highlight |
| Band | `#16191C` | `#101315` | caption band; its progress line is `#5B9BE8` |
| Sheet alt | `#F2F4F6` | `#2E343A` | pressed buttons, the queue row under the pointer |

Status colors are only used as text: done `#2E7A4E` / `#6FCF97`, failed `#B83A2B` / `#F08A7E`.

Contrast (WCAG): white on signal blue 6.4:1 light, 4.8:1 dark; the dark-mode hover gets darker, not lighter, to stay above 4.5:1. Graphite on desk 4.9:1.

Rejected: indigo accent (the generic "AI app" purple of pass 2), gradient washes, cream + terracotta, near-black + acid green. Caption yellow (pass 3) was replaced by blue at the client's request.

## Type

- **Atkinson Hyperlegible Next** (Braille Institute, OFL) for all UI text. It was drawn for maximum legibility, which fits a tool whose output is captions, an accessibility medium.
- **Atkinson Hyperlegible Mono** only where the content is genuinely tabular: durations, sizes, the engine log. Not for decorative labels.
- Scale (px): 12 small, 13 body, 14 names and buttons, 15 section headings, 22 page headings. Weights: 400 body, 600 emphasis, 700 headings and the primary button. Sentence case everywhere; no all-caps labels.
- The stylesheet sets the font family globally, which overrides `setFont()`; monospace text uses the `mono` label role (or painter fonts in delegates).

## Layout

```
┌──────────────────────────────────────────────────────────────────┐
│ ▣ K-Whisper   Queue  Models                    Running on Metal ⚙ │  top bar, underline tabs
├──────────────────────────────────────────────────────────────────┤
│ 4 recordings                             Add folder  Add files  … │  heading says what is there
│ 1 done, 1 waiting, 1 failed                                       │
│──────────────────────────────────────────────────────────────────│
│ interview.mp4                   12:41   Transcribing 46%          │  aligned columns, hairlines
│ ~/Movies/Interviews                     about 2 min left          │
│ ▐ ask not what your country can do for you,                    ▌  │  live caption band
│ podcast.mp3          [Open SRT] [Show in Finder] 48:02  Done     │  buttons on the row under the pointer
│ Saved SRT, TXT next to the recording    took 3:10                 │
├──────────────────────────────────────────────────────────────────┤
│                                              [⚌ Advanced options] │  run bar: settings left,
│ Model         Make                        Spoken language         │  two buttons stacked right
│ [turbo-q5 ▾]  [Subtitles|Transcript|Both] [Detect ▾] ☐ English  [ ▷ Transcribe 3 ] │
└──────────────────────────────────────────────────────────────────┘
```

- Left aligned text; numbers (durations, sizes) right aligned in their own column.
- No cards: the queue is one sheet with hairline rules, because the recordings are a list, not a set of tiles.
- Radius follows hierarchy: 6 px controls, 4 px caption band, 0 on sheets.
- Page headings never repeat the tab name; they state what is on the page ("4 recordings", "1 model downloaded").
- The model choice lists only downloaded models, smallest first with each size. When the chosen one is missing, new recordings use the biggest downloaded model; with none downloaded a "Download a model…" button takes the choice's place and leads to the Models page, Transcribe is off.
- Waiting recordings always use the run bar settings, so a row shows where the file is, not its settings. With nothing waiting, the button offers to transcribe the finished (or selected) recordings again with them.
- A row under the pointer shows its next step as buttons: open the result and show it in the file manager, the log and another try for a failed one, Stop for the one being transcribed. Double-click, the context menu and Ctrl+. stay as before.
- Advanced options live in a separate window, opened by a real button in the run bar that says how many options differ from the defaults.
- The run bar: the settings with captions on the left; on the right a column with Advanced options above Transcribe, both as wide as the Transcribe button needs for its longest label, so nothing reflows mid-run. Both sides sit on the bottom edge, so the fields line up with Transcribe.
- Long lists (the spoken languages) open with a search field above them; the list keeps its height while typing, so the field does not jump when the list opens above the run bar.
- Buttons: solid blue for the default action of a dialog, at the size of the buttons beside it; only the one action of a page (Transcribe, the first model download) is large.
- Dialog forms share one label column across sections, so the fields line up.
- The empty queue is a dashed drop zone with its content centered, because that is what it is: a place to drop files.
- Files are never overwritten without consent: before starting, existing files are listed with Replace / Keep both / Skip; Settings can make the choice permanent.
- Drop-down lists open below their field (`combobox-popup: 0`); Fusion's default popup ignores the visible item limit.

## Principles

1. One button starts the work, and it says what it will do ("Transcribe 3 recordings").
2. Structure carries information: columns for comparable values, rules between items, nothing ornamental.
3. Solid blue means "the action"; blue tint means "chosen". Nothing else is blue.
4. Empty and error states say what to do next: no model points to the Models page, a failed row shows why.
5. Focus outlines appear only for keyboard use: buttons take focus from Tab, not from clicks.
6. Message boxes have no icon, a short bold headline with the details below, and buttons named after their action. A destructive one has red text and is never the default; it keeps an ordinary role, since Qt sets destructive-role buttons apart on macOS.

## History

- Pass 1: stock Qt widgets with a toolbar and table. Read as dated.
- Pass 2: sidebar, indigo accent, rounded cards, pill chips, all-caps section labels, a settings inspector always on screen. Read as generated: the SaaS-card kit plus template chrome from the skill's list.
- Pass 3: "caption desk" with caption yellow, top bar, one queue sheet, live caption band, advanced options in their own window.
- Pass 4: signal blue instead of yellow, subtitle editor removed (transcription only), empty state that guides the first model download, download-and-transcribe when the model is missing, model choice from the Models page, flat blue app icon.
- Pass 6: the client's logo (a K in corner brackets) replaces the waveform icon: transparent in the top bar with a dark or white letter by theme, on a white tile with a soft shadow as the app icon (`scripts/make_icons.py`). Advanced options and Transcribe stacked on the right of the run bar, Stop moved to the running row, search in the language list, the model choice smallest first with each size and only downloaded models (the download-and-transcribe offer is gone).
- Pass 5: finishing pass. Models sorted by size with a Recommended tag and "compressed" explained instead of "quantized"; Advanced options as a button; dialog buttons no longer oversized; aligned dialog forms; row buttons in the queue; drop zone; transcribe again; asking before overwriting files.
- Pass 7 (current): a new logo, a navy bird (`#3F4775`, cheeks and beak `#479AF4`), replaces the K in corner brackets. The top bar shows it at 26 px; in dark mode its body is lightened to `#7D87C7`, since navy on the dark desk is barely visible. The app icon keeps the white tile; on macOS 26 in dark mode it switches to the lightened bird on the dark sheet colour (`#262B30`), because the system's own darkening of the classic icon also turned the white eyes dark. Source files for other uses (the icon and the logo with the name, each also for dark backgrounds) are in `docs/brand/`.
