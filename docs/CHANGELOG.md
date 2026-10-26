# What's new

The version you are running is shown in the bar at the top left and under *Help › About*. All versions were released in October 2026.

## 0.8.0: Guided tour

- **Take the tour** under *Help*, and offered on the first start. It opens a demo workspace with six made-up students and a short assignment, and walks through Setup, Pre-screen, Review and grade, and Export, lighting up each part it explains. Every step has *Skip tour*, *Back* and *Next*, and links to jump to any tab's part of the tour. Arrow keys and Enter move on, Escape ends it.
- The demo needs no key: its AI results are written in advance. With a key saved, the AI parts work in the demo too, on the made-up students: re-screening, *Re-run AI* and *New from documents…*. Three students are already graded, so the overview and the export have something to show, and three are left to try, including two with similar work to compare side by side.
- A yellow *Demo workspace · Leave* button shows while the demo is open and goes back to the workspace open before. The demo is never reopened at start or listed under recent workspaces.
- Text written with typographic ligatures (common in LaTeX PDFs, where "fi" is one character) is now read as plain letters, so headings such as "Verification" and words such as "polyfit" are recognized by the automatic checks.

## 0.7.3

- The grading panel now saves a student only when something was changed on screen. The student it loads in the background when a workspace opens (the first in the list, even if the Review tab is never visited) can no longer be written back over newer results, for example after a pre-screen run, at the 15-minute backup or when the app closes.
- Students are listed in Turkish alphabetical order: Çağrı after Can, İsmail after Işık, Ömer after Osman. Before, names starting with Ç, İ, Ö, Ş or Ü came after Z.

## 0.7.2

- **Fixed: lost integrity findings.** When a student was open in *Review and grade* while their pre-screen result arrived (often the first student in the list, which opens by default), moving on could save the older copy over the new result, so the AI's integrity findings disappeared from the grading. Saving now keeps findings added in the meantime, and a student on screen is refreshed when their result arrives. Findings lost this way are put back when the workspace is opened, those students are marked to decide again, and the Setup tab names them.
- **Integrity findings column** on the Pre-screen tab counts everything to decide, as Review lists it: from the AI, the automatic checks and the similarity check. Hover for the breakdown. It shows 0 instead of an empty cell.
- **Clear list colours** with a legend under the student list. Red: a likely problem or an integrity finding. Amber: only items to check. White: nothing flagged. Before, amber also covered students with nothing flagged, and findings from the automatic checks did not count.

## 0.7.1

- **Effort.** Choose how long the AI thinks before answering (low, medium or high) next to the model on the Pre-screen tab, and in *Re-run AI* in Review. Medium is the default. The cost estimates follow the choice, every result records its effort level, Review shows it, and the log has it. A model that does not accept an effort level is run without one.

## 0.7.0: AI instructions, one-step import and a workspace log

- **Import all documents.** The Scan button is gone. Choose the assignment, the submissions and the class list, then press *Import all documents* once. It copies everything in, matches each submission to the class list, and says what was added. A class list chosen later is matched to the students already there. *Clear* for the class list works again.
- **Points and penalties** is a blue button, so it is easy to find.
- **AI instructions** on the Pre-screen tab: see the instructions the AI follows and the complete prompt for one student. The instructor can edit them or restore the default. A short fixed part that keeps the app's safeguards working is always added. Read-only in TA workspaces and without an API key on this computer.
- **Model choice** for a run on the Pre-screen tab, with the cost estimate for that model.
- **Prompt versions.** Every result records the version of the class-wide prompt (instructions and note), the model and whether a student note was used. After a change, the app offers to re-screen everyone done with the earlier version, or lists them with *Re-screen them*. Review shows which prompt made each result.
- **Workspace log.** *logs/grader.log* in each workspace records every step and every error, never the API key. *Help › Open log folder* opens it.
- Fixed: *Open export folder* with no workspace open caused an error.

## 0.6.4

- Dates and numbers are always in English. On a computer set to another language, dates such as *23 Eki 2026* now read *23 Oct 2026*, and number boxes show *5.0* rather than *5,0*.

## 0.6.3

- **Points and penalties.** The *Penalties…* window is now *Points and penalties…* and also sets the points of each rubric item. Levels already chosen stay, and every total is recalculated. *Preview* shows whose totals change. Graders see the original points next to a changed item, and feedback pages show only the current points. A change to the total asks first.
- The AI prompt no longer contains points, and the AI is told that points play no role, so re-weighting never needs a new pre-screen.
- Clearer wording for item score caps: the columns are now *Item score cap, full penalty* and *half penalty*, with *no cap* instead of *none*.

## 0.6.2

- **Similar work is now part of grading.** The check runs by itself when a pre-screen run finishes, and the Similar work tab is gone. A pair that shares long passages gives both students an integrity finding to decide in *Review and grade*. The finding's *Compare side by side* button opens a separate window with both papers next to each other and the shared passages listed and marked. The Pre-screen tab shows the result and has *Check for similar work now*.
- The check runs again after a pre-screen only when a submission was added or replaced, and it remembers each PDF's text while the app is open, so repeated checks are quick.
- Fixed: grading the student on screen while a similarity check finished could stop that student's further changes from being saved. The student is now saved first and shown again with the new finding.
- Fixed: switching workspace during a check could store its result in the other workspace.
- The shared passages in the side-by-side window are shown as printed in the PDF, with capitals and punctuation.

## 0.6.1

- **Less crowded grading panel.** Earlier comments open from a small list icon inside the comment box, shown only when there are earlier comments, instead of a separate button beside it. The keyboard shortcut line at the bottom is now a *Keyboard shortcuts* link next to the total, showing the list when you point at it or click it.

## 0.6.0: Similar work, earlier comments and regrade requests

- **Similar work tab.** Compares every pair of submissions on your computer, without the AI, and lists only pairs that share long passages of identical words. Handout text, wording many students share and numbers are left out. On the 14 real submissions no pair was listed. Click a pair to see both papers side by side, then click a shared passage and both turn to it with the shared words marked. *Add a finding to both* sends a pair to the grading and the instructor's list, and *Not a concern* sets it aside.
- **Earlier comments.** Each comment box offers what you already wrote for that item for other students, most used first, and suggests matching comments as you type.
- **Regrade requests.** *Regrade request…* reopens a reviewed student with the student's request, asks for a reply, and records the grade before and after. The feedback page shows the request, the reply and what changed. Export can write only the regraded students, to a separate folder, and a log of all requests.
- **Cost.** The Pre-screen tab shows what the AI has cost so far and estimates what *Start* would cost. *Re-run AI* shows the cost of one student for each model.
- On narrow windows the tab names are shortened so all five fit.

## 0.5.0: Backups, keyboard grading and a grade overview

- **Automatic backups.** The grading is copied into the workspace's *backups* folder when the workspace is opened each day, every 15 minutes while something changes, when the app closes, and before the assignment, the penalties or an imported package change anything. The newest 30 are kept.
- **Restore.** *Backups…* on the Setup tab lists every copy with when and why it was made and how many students it has reviewed. You can also make one by hand. A restore backs up the current state first, so it can be undone.
- **Grading from the keyboard.** 1 to 5 set the level of the current rubric item, F, H, N and R decide a finding, C opens the comment, Alt+arrows move between items and students, and Ctrl+Enter (Cmd on a Mac) marks reviewed. The current item has a blue outline and the panel scrolls to it. Keys never act while you type in a text box.
- **Grade overview** at the top of the Export tab. Each student is a dot, for the total, any rubric item or the integrity deductions, with the median and the middle half of the class marked. Hover for the name, click to open the student.
- **Worth a second look.** Under the plot, a list of students where points were lost without a comment, a grade goes clearly against a confident AI flag, the total is far from the rest, or the AI was re-run after grading. One click opens each student.

## 0.4.9

- Fixed codes such as `&quot;` showing instead of quotation marks in the *Suggested headings* line on the Review tab. File names with an apostrophe or "&" now also display correctly.

## 0.4.8

- **Whole-picture judgement.** When the handout lists qualities or examples, such as "clarity, simplicity, generality" or "generate, modify, or debug", the AI now judges that part as a whole and does not flag a sound answer for leaving one listed word out. Separately requested items, such as the lettered verification checks, are still each expected.

## 0.4.7

- **Fewer false flags from the automatic checks.** A verification item is now recognised in the student's own words, for example a "(d)" item about currents, and Word's maths letters are read as normal letters. On the 14 real submissions this removed two wrong "check not presented" flags and left every genuine flag in place.
- When a reference value is not found in the report text but parts of the report are pictures, the note now says so, since the value may be in an image that the AI was shown.

## 0.4.6: A sturdier AI pre-screen

- **Hidden text.** Text a reader cannot see (white on a white page, microscopic, or set to invisible) is removed before anything reaches the AI, and the grader gets a finding that quotes it. Students cannot slip instructions to the AI this way. Light text on dark code boxes and the text layer of scans are not affected. Students pre-screened by an earlier version are checked when opened in the Review tab.
- **The AI ignores instructions inside a submission.** Everything in the PDF, including the student's own prompts to other AI assistants, is treated as material to assess. Any attempt to influence the assessment is reported as a finding.
- **Quotes checked.** Each passage the AI cites is looked up in the PDF. A wrong page number is corrected, and a quote that is not in the PDF is marked *quote not found, check it*.
- **No cut-off answers.** The AI has more room for its answer. If an answer is still cut off, it is retried once with extra room instead of failing after four identical paid attempts.
- **Clearer AI instructions.** The list of integrity findings no longer contradicts itself, the app's own length markers are not mistaken for an incomplete record, and a valid alternative approach is never presented as a concern.
- **Headings.** Suggested headings that are not used are now information only and never flag a rubric row.
- **Cost.** The Pre-screen tab shows how much of the input was repeated material billed at the lower cached rate.
- The User guide no longer opens with a version line.

## 0.4.5

- **Re-running the AI on a graded student.** Your grades, comments and decisions are kept, as before. The student now turns violet in the list with *AI re-run, check again*, and no longer counts as reviewed until you press *Mark reviewed* again.
- A banner on that student shows when the AI ran again and what it now sees differently, for example *Checks: likely problem → nothing flagged*, or that nothing changed, and lists any new findings to decide.
- New AI findings of a kind you have already decided are no longer added a second time.
- The student list has a new filter, *AI re-run, check again*.

## 0.4.4

- **Clearer Export tab.** Status tiles at the top show how many students are reviewed and where the grades will go. The rest is laid out in separate cards: *Export*, *Files written* (each file with what it is for and who it is for), *How the AI compared with the grading* (a table per rubric item, with the terms explained) and *Upload to Moodle* as numbered steps.

## 0.4.3

- **Live progress while pre-screening.** A *Now processing* box on the Pre-screen tab shows each document being worked on and the step it is at: reading the PDF, automatic checks, removing names and preparing pages, waiting for the AI, saving. Each row has a running timer, and finished documents stay listed with their time. The Status column in the table follows along.
- The text log at the bottom of the Pre-screen tab is gone. The progress box and the table show the same and more, and short messages such as *Nothing to do* appear on the progress box's status line.
- **About** now names the developer and lists the open-source components the app uses, with their licences.

## 0.4.2

- **Version history.** *Help* is now a menu: *User guide*, *What's new* (this page) and *About*.
- **About** shows the version, where the app runs from and where its log file is kept.

## 0.4.1

- Opening a workspace that is still open in another copy of the app, or in an older version, now gives a clear message instead of a database error.
- Workspaces made by older versions that still have side files next to the database (*grading.db-wal*, *grading.db-shm*) are folded into *grading.db* when opened, so no grading is lost.

## 0.4.0: Windows reliability

- **Error log and messages.** On Windows the app runs without a console window. All output now goes to a log file, *app.log*, and any unexpected error is shown on screen with the log's location instead of closing silently.
- **Long file names.** Moodle ZIPs are unpacked through a short temporary folder, so long student file names inside deep Google Drive folders stay within Windows' 260-character path limit.
- **No locked files.** The PDF viewer reads each file into memory, so a re-scan can replace a student's PDF even while it is on screen.
- **Local copies.** *Copy to this computer* now uses your home folder, not Documents, which OneDrive or iCloud often sync.
- **Starter.** The Windows starter uses Windows line endings and finds the setup tool wherever it was installed.

## 0.3.9: Submissions inside the workspace

- After a scan, the Submissions row shows the workspace's own *submissions* folder. The Moodle download can be deleted.
- Scanning again with nothing new chosen says that all submissions are already in the workspace.
- **Late submissions.** Choose the new Moodle ZIP and scan. Only new or changed students are added, and only they are pre-screened. Grading already done is kept.

## 0.3.8: Clearer grading panel

- The panel on the right is laid out in steps: *Start here*, *1 Grade the rubric*, *2 Decide integrity findings*, *3 Comment and finish*.
- Counters such as *4 of 6 graded* and *1 of 3 decided* show your progress and turn green when a step is done.
- Rubric items are numbered and grouped under their task, with the task's points.

## 0.3.6 and 0.3.7: Checking for real text

- **Drag a box** on a PDF page to see the text the PDF really contains there. It is copied to the clipboard, or the app tells you the area is an image, such as a screenshot.
- **Show text** tints every real word in green, so pages given as images stand out at a glance.
- Clicking one of the AI's *Go to* pointers clears your selection, so the highlighted quote is the only thing marked.

## 0.3.3 to 0.3.5: New look

- An app bar at the top with the four steps as a menu, the workspace name and version, *Help* and *Quit*.
- Rounded cards, softer colours, slim scroll bars and the Inter font, so the app looks the same on Mac and Windows.
- **Quit** button. Your grading is saved as you go, and Quit saves anything still pending.
- Fixed quotation marks showing as `&quot;` in the *To check* list.

## 0.3.0 to 0.3.2: One self-contained workspace

- **Everything in one folder.** Scanning copies the student PDFs into the workspace. The assignment, the class list, AI access for TAs, exports and TA packages all live inside it too. The folder can be moved, renamed, copied or opened on another Mac or PC.
- **Open and New.** *Open…* finds the workspace even inside the folder you pick, and *New…* makes one. Choosing the wrong folder never shows an empty class.
- **Cloud folders.** A workspace in Google Drive, Dropbox, OneDrive or iCloud is offered a copy on this computer first.
- **Starter.** The starter copies the app to the computer and runs it from there, so nothing is written into a shared folder. It removes the *.venv* folder left by the first version.
- **No side files.** The database no longer keeps *-wal* or *-shm* files next to it.
- **No bundled assignment.** The app contains only the program. You choose the assignment folder and it is copied into the workspace.
- Workspaces from older versions are converted the first time they are opened.

## 0.2.0: Grading tools

- **Penalties…** edits the deduction for each kind of finding and recalculates every student. Findings that describe the same problem count once.
- **Score limit** for results the submitted work does not produce: the ticked rubric rows can score at most 25%, or 50% with half penalty.
- **Change type** and **Restore AI suggestion** for findings. Scrolling with the mouse never changes a choice.
- **To check** list at the top of each student, with *Go to* buttons that open the page and highlight the quoted words.
- **Re-run** for a single paper, with the prompt visible, a note for the AI and the stronger model on request.
- **TA access files** and **TA packages**, and **New from documents** to draft a new assignment's rubric with the AI.
- Students matched to the Moodle gradebook export, so names and student IDs are right.

## 0.1.0: First version

- AI pre-screen of each submission against the assignment and rubric, with the AI's confidence. The grader decides every grade.
- Automatic checks for a missing AI record, an AI record given only as a link, chat, code or report given as images, page limit, required headings, reference values and results the code does not produce.
- Names, student IDs and email addresses removed before anything is sent to the AI.
- Resumable runs with progress, feedback PDFs for every student and a Moodle feedback ZIP.
