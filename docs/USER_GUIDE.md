# MATH241 Grader User Guide

The AI pre-screens each submission and points to what needs a closer look. The grader reads the work, chooses every rubric level and decides every finding.

## What the app does

The app reads each student's PDF, runs a set of automatic checks, and asks an AI model to pre-screen the work against the assignment and rubric. The AI never grades. It marks which rubric rows need a closer look, shows where in the PDF, and lists possible integrity problems. The grader reads the work, chooses every rubric level, decides every finding, and the app produces one feedback PDF per student.

## A guided tour first

*Help › Take the tour* opens a demo workspace with six made-up students and walks through the four tabs in about three minutes, pointing at each button as it goes. No key is needed: the demo comes with AI results written in advance. With an API key saved, the AI parts work in the demo too, on the made-up students: *Re-screen selected* and *Start*, *Re-run AI* in Review, and *New from documents…* to have the AI draft a rubric from the demo's handout and guide (in its *sample files* folder). *Skip tour* ends it at any step, and the links at the top of each note jump to a tab's part of the tour. The app offers the tour on the first start. Three demo students are already graded and three are left to try. The yellow *Demo workspace · Leave* button goes back to the workspace that was open before. Starting the tour from your own workspace gives a fresh demo, so nothing tried there is kept.

## Before you start

You need four things:

- **The app.** Unzip *MATH241_Grader_app.zip* on your own computer and double-click *Start MATH241 Grader* (Mac) or *Start MATH241 Grader (Windows)*. The starter copies the app to your computer and runs it from there, so nothing is ever written into the unzipped folder. The first start sets itself up, which takes a few minutes and needs internet. Later starts are quick. Share the ZIP itself, not an unzipped folder, because Google Drive drops the Mac's permission to run the starter. On a Mac, the very first time, right-click the file and choose *Open*. On Windows, if a blue warning appears, choose *More info* and then *Run anyway*.
- **AI access.** When the instructor gives you a workspace folder, AI access is already inside it. Otherwise the instructor sends a small *access file* that you load once (see Setup). There is no key to type.
- **The submissions.** In Moodle, open the assignment, choose *View all submissions*, then *Download all submissions*. Keep the ZIP as it is.
- **The class list.** The course gradebook export from Moodle (.xlsx or .csv).

## The assignment at hand

The **Assignment** button in the top bar opens the rubric, the handout and the solution in a separate window, from any tab. Keep it open next to the grading, or on a second screen. The rubric page shows each item with its points, what each level means, the grading rules, the accepted alternatives and what each integrity finding costs. These are the files copied into the workspace with the assignment, so a TA who receives a workspace has them too.

## 1. Setup

1. **Workspace.** Press *New…* and choose an empty folder for this assignment, or *Open…* to continue one. *Open…* also accepts a folder that contains the workspace somewhere inside it. Everything is saved in that one folder as you go: the grading, and copies of the student PDFs, the assignment and the class list.
2. **Grader name.** This appears on the feedback pages.
3. **Assignment.** Choose the assignment folder the instructor shared. The app itself contains no assignment.
4. **Submissions.** Choose the Moodle ZIP, or the folder you unzipped it into.
5. **Class list.** Choose the gradebook export. The app uses it to show proper names and student IDs.
6. **AI access.** If the workspace came from the instructor, nothing to do. Otherwise press *Load access file…* once. The file is copied into the workspace and carries over to new workspaces you make. *Test* confirms that it works.
7. Press **Import all documents**. Everything chosen above is copied into the workspace: the assignment, the class list and the student PDFs, and each submission is matched to the class list. The line next to the button says what was added, and lists anything chosen but not imported yet. Afterwards the originals, including the Moodle download, can be moved or deleted. For late or re-uploaded work, choose the new Moodle download and press *Import all documents* again: only new or changed students are added, and grading already done is kept. A class list chosen later is matched to the students already there.

## 2. Pre-screen

Choose the **Model** and the **Effort**, then press **Start**. The default model and medium effort are right for almost every paper. Effort is how long the AI thinks before answering: higher is usually more careful on proofs and code, but slower and more expensive, because the thinking is billed. The cost estimate follows both choices. Several students are processed at a time, and each result is saved the moment it finishes. *Pause* or closing the app loses nothing. *Start* continues with the rest.

*Automatic checks only* runs the free checks without the AI, which is useful for a quick first look.

**AI instructions.** *AI instructions…* shows the instructions the AI follows for every student, and on its second tab the complete prompt for one student, exactly as it will be sent. The instructor can change the instructions there, or press *Restore default*. A short part that keeps the app's safeguards working (names removed, instructions hidden in a submission ignored, answers in the format the app reads) is always added and cannot be changed. The instructions can be changed only on the computer where the API key was entered, and only in the instructor's workspace. In a TA's workspace they can be read, not changed.

**One prompt for everyone.** The AI instructions and the class-wide note together are the class-wide prompt. Every result records which version of it was used, the model, and whether a student note from *Review and grade* was added. When you change the instructions or the note, the app offers to re-screen every student done with the earlier version, with the cost. If you decline, the line under the progress bar lists them with *Re-screen them*, and their Review page says the result is from an earlier prompt. Grading already done is kept, and students you already graded are marked *AI re-run, check again*. A student note from *Re-run AI* in Review applies to that student only and stays with them for later runs.

**Similar work.** When a run finishes, the app also compares every pair of submissions on your computer, without the AI, and looks for long passages of identical words. Text from the handout, wording that many students share and numbers are left out, since correct results are expected to match. Most classes have no such pairs. When a pair is found, both students get an integrity finding to decide in *Review and grade*. The line under the progress bar shows the result, and *Check for similar work now* runs it again, for example after late submissions.

**Cost.** The summary shows roughly what the AI has cost so far and what *Start* would cost for the students still waiting. The estimate is based on the students already done, so it gets more accurate after the first few. *Re-run AI* shows the cost of one student for each model.

**Note to the AI for every submission.** If the same situation keeps coming up, write it here once, for example "A voltage map given as a numerical table is acceptable." It applies from the next run on. Select students in the table and press *Re-screen selected* to apply it to students already done.

## 3. Review and grade

The student list on the left shows a coloured dot, explained under the list:

- **red**: the AI rated a rubric item a likely problem, or there is an integrity finding to decide or confirmed, from the AI, the automatic checks or the similarity check,
- **amber**: only items marked *Check this*,
- **white**: pre-screened and nothing flagged (still read the work),
- **green**: you have marked the student as reviewed,
- **violet**: the AI was re-run after you graded, so check again,
- **teal**: an open regrade request,
- **light grey**: not pre-screened yet.

The PDF is in the middle and the grading panel on the right.

The panel on the right is laid out in order: **Start here**, then **1 Grade the rubric**, **2 Decide integrity findings** and **3 Comment and finish**. Small counters show how far you are, for example *4 of 6 graded*, and turn green when a step is complete.

**Start with the "To check" list** at the top of the panel. It numbers everything that needs you: rubric rows the AI flagged and integrity findings still to decide. Click an item to jump to its card and to the page it refers to, with the passage highlighted.

**Rubric rows.** Each card shows the AI's status and, where something was flagged:

- *What the AI found*: the problem in one or two sentences.
- *What to check*: exactly what to open and look for.
- *Where*: *Go to p.5 · report* style buttons that open the page, with the quoted words below.

| Status | Meaning |
| --- | --- |
| Check this | Something to look at. |
| Likely problem | A concrete issue the AI found. |
| Nothing flagged | The AI saw no issue. This does not mean full marks. Read the work. |
| AI unsure | The AI could not verify this row. Read it yourself. |

Then choose 100, 75, 50, 25 or 0%, and add a comment for the student if useful.

**Checking for real text.** The PDF is shown as pictures of the pages, so you cannot select in it directly. Instead, drag a box over any part of a page: the app shows the text it finds there and copies it, or tells you the area holds no selectable text, as with a screenshot. *Show text* tints every real word in green, so pages or parts given as images stand out at a glance.

**Integrity findings.** These come from the AI or from the automatic checks, and you can add your own with *Add finding*. Each one shows *The problem*, *What to check* and *Where*, like the rubric cards. Check each one yourself and choose a decision:

- *Rejected*: not a real problem, no effect on the grade.
- *Full penalty*, *Half penalty* or *No penalty*. Half and no penalty need a short comment.

**Similar work findings** name the other student and the pages. Press *Compare side by side* on the finding: a separate window opens with both papers next to each other and the shared passages listed. Click a passage and both papers turn to it with the shared words marked in yellow. Signs of copying are the same unusual wording or explanation, identical code down to comments, variable names and layout, the same mistakes or typos, and the same AI conversation. Standard definitions, textbook proof steps and short standard code are ordinary overlap. Close the window and decide the finding as usual, and decide it for the other student too.

If the AI picked the wrong kind of problem, press *Change type* on the card and choose from the full list. The card keeps showing what the AI suggested, with *Restore AI suggestion* to undo. For a problem the AI did not flag at all, use *Add finding*. Scrolling with the mouse never changes a choice; a box only reacts after you click it.

The penalty points come from the assignment settings and are shown next to each finding. If two findings describe the same problem (for example *AI record missing* and *AI record given only as a link*), only the larger penalty counts. One finding, *Results or checks not produced by the submitted work*, also has an **item score cap**: the rubric items you tick under it (usually *Checks*) can score at most 25% with full penalty, or 50% with half, whatever level you chose, because that work was not actually demonstrated.

Typical automatic findings:

- the AI record is missing, given only as a link, or given as screenshots,
- code given as screenshots,
- reported verification values that the submitted code does not produce.

**When the AI got something wrong**, press *Re-run AI / view prompt…*. You can see exactly what was sent and what came back. Write a note for this student, such as "The voltage map is the table on page 5", and re-run. For an unusually hard paper you can choose higher effort or the stronger model in the same window. Try higher effort first. Use the stronger model sparingly, because it costs much more. Your rubric choices and decisions are kept. If you had already graded the student, they turn violet in the list (*AI re-run, check again*) and a banner shows what the AI now sees differently. Look again where needed and press *Mark reviewed and next* to confirm.

Press **Mark reviewed and next** when a student is done. The app will not mark a student reviewed while a rubric row or a finding is still undecided.

**Earlier comments.** When you have already written comments for a rubric item, or that kind of finding, for other students, a small list icon appears at the right end of its comment box. Click it to see them, most used first. Pick one to add it, then edit it if needed. While you type, matching earlier comments are suggested. A comment you no longer want offered can be taken off the list with *Remove from this list*.

**Regrade requests.** When a student asks for a grade to be looked at again after release, open them and press *Regrade request…* at the top. Paste or summarise what they ask. The student turns teal in the list and is no longer counted as reviewed. Look at the work again, change what is warranted, write a reply in the box that appears, and press *Mark reviewed*. The feedback page then shows the request, your reply and what changed. *Withdraw request* removes a request opened by mistake.

**Grading from the keyboard.** One item at a time has a blue outline. Keys act on that item, wherever the panel is scrolled, and the panel follows it. Clicking a card makes it the current one.

| Key | What it does |
|---|---|
| 1 to 5 | Level of the current rubric item (100, 75, 50, 25, 0%), then on to the next item |
| F, H, N, R | Finding decision: full, half, no penalty, rejected. H and N open the comment box |
| C | Type a comment for the current item |
| Esc | Stop typing, so the keys work again |
| Alt+↓ / Alt+↑ | Next or previous item (Option on a Mac) |
| Alt+→ / Alt+← | Next or previous student |
| Ctrl+Enter | Mark reviewed and next (Cmd on a Mac) |

While you type in a comment box, letters and numbers go into the text and never change a grade. *Keyboard shortcuts* at the bottom of the panel shows the same list.

## 4. Export

The tiles at the top of the Export tab show how many students are reviewed and where the grades will go.

**Grade overview.** Before exporting, look at how the grades are spread. Each student is a dot, and dots with the same score stack up. The line marks the median and the shaded band holds the middle half of the class. Pick *Total*, any rubric item or *Integrity deductions* above the plot. Hover over a dot to see who it is, and click it to open that student in *Review and grade*. Filled dots are reviewed and hollow ones are not yet.

Under the plot, *Worth a second look* lists students with something you may want to recheck, each one click away. A student is listed when points were lost without a comment, when a grade goes clearly against a confident AI flag (a confident problem given 100%, or nothing flagged given 25% or less), when the total is far outside the middle half of the class, or when the AI was re-run after grading. These are prompts, not errors. On the plot, those students have an amber ring.

Then press **Export**. The files go to the *export* folder inside the workspace (*Open export folder* shows it), and the *Files written* card lists each one with what it is for:

- one feedback PDF per student: a cover page with the scores, comments and findings, followed by the original submission,
- `moodle_feedback_files.zip`, ready for Moodle's *Upload multiple feedback files in a zip*. Each student receives only their own PDF,
- a grades file and a detailed grades table,
- a list of all integrity findings with the graders' decisions, for the instructor,
- a short report comparing the AI's flags with the final grading.

Export again after any change. Earlier exports are overwritten.

**After regrades.** When regrade requests have been answered, the Export card offers to export only those students. Their files go to a separate *regrades* folder inside *export*, so uploading them to Moodle changes only those students. Every export also writes *regrade_requests.csv* with each request, the reply and the grade before and after. The *Upload to Moodle* card gives the steps for the files you have, and *How the AI compared with the grading* shows, per rubric item, how often the AI's flags matched the final grades.

## Good to know

- **Privacy.** Names, student IDs and email addresses are removed before anything is sent to the AI. Screenshot pages cannot be cleaned this way, since there is no text to find the name in.
- **Hidden text.** Text a reader cannot see, such as white text on a white page, is removed before the AI reads the PDF, and you get a finding that shows what it said. The AI also ignores any instructions written inside a submission.
- **Quotes.** Each passage the AI cites is checked against the PDF. If one is marked *quote not found, check it*, look at that part yourself.
- **Penalties.** The penalty points are set by the instructor (*Points and penalties…* on the Setup tab). Please do not change them. Everyone must grade with the same numbers.
- **Alternative solutions.** The instructor's solution is one correct answer among many. Correct alternative proofs, code and checks get full credit.
- **Backups.** The grading is backed up automatically into the workspace's *backups* folder: when the workspace is opened each day, every 15 minutes while something changes, when the app closes, and before the assignment, the penalties or an imported package change anything. The newest 30 are kept. *Backups…* on the Setup tab lists them with how many students each one has reviewed, makes one by hand and restores one. A restore first backs up the current state, so it can be undone.
- **Moving folders.** The workspace folder holds everything, so you can move, rename or copy it, or open it on another Mac or PC. Close the app first. Workspaces from older versions are converted the first time they are opened.
- **Google Drive.** Do not grade inside a synced folder from two computers. When a workspace is in Google Drive, Dropbox, OneDrive or iCloud, the app offers to copy it to your computer first. To hand work between people, copy the closed workspace folder, or use TA packages.
- **Re-uploads.** If a student's PDF changes, scanning again detects it, and that student is pre-screened again.
- **Help in the app.** The *Help* menu at the top right opens this guide, *What's new* (the changes in each version) and *About* (your version and where the log file is).
- **Log file.** Each workspace keeps a log, *logs/grader.log*, with one line per step: imports, each student pre-screened (time and tokens), exports, backups, and changes to points, penalties or AI instructions, plus every error in full. *Help › Open log folder* opens it. If something goes wrong, send this file. It never contains the API key, the prompts or anything shown to students.
- **If something goes wrong.** The app shows the error and keeps a log file, *app.log*: on Windows in *%LOCALAPPDATA%\MATH241Grader*, on a Mac in *Library/Application Support/MATH241 Grader* in your home folder. Send it to the instructor.

## For the instructor

- **Giving TAs AI access.** On the Setup tab, press *Create TA access file…* before you hand over the workspace folder. Choose a separate key per TA if possible, an expiry date, and whether the stronger model is allowed. The access file is saved inside the workspace, so the TA can run the pre-screen and re-runs with no setup. The key is hidden inside the file, not unbreakable. Keep a spending limit on the OpenAI project and revoke the keys at the end of the semester.
- **Points and penalties.** *Points and penalties…* on the Setup tab sets the points of each rubric item and the deduction for each finding. Graders store only the level they chose (100%, 75%, ...) and which finding applies with their decision, never points. So you can move points between items, say 10 from one item to another, at any time: every total is recalculated and nobody has to re-grade. *Preview* shows whose totals change before saving. Graders see the original points next to a changed item, while feedback pages show only the current points. The AI never uses points, so no new pre-screen is needed. If the total changes, the app asks first, because Moodle expects the same total. Export again afterwards.
- **Item score caps.** A cap limits the score of the rubric items a grader ticks on a finding, whatever level was chosen, for example *Checks* at most 25% when the reported results are not produced by the submitted code. *no cap* means the finding only takes points off.
- **New assignments.** *New from documents…* next to Assignment. Point to the assignment PDF and the instructor guide, let the AI draft the rubric table, check every row, especially the points, and save. It is written into the workspace's *assignment* folder.
- **Splitting students between TAs (optional).** When one TA grades everything, just give them the workspace folder. With several TAs, *Create TA package…* hands each TA specific students with the AI results so far. The TA's return file brings their grading back with *Import TA return file…*, so you export the whole class from one workspace. Packages and return files are saved in the *packages* folder inside the workspace.
