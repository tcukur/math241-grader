"""The demo workspace: a small made-up assignment with six made-up students, for the guided tour.

build(folder) writes everything a real session would have (the assignment, a class list, a Moodle-style download)
and brings it into a new workspace with the app's own import, so the demo behaves like real work. The AI results
are written in advance here: the demo never calls the AI and needs no key. Three students are already graded, so
every screen has something to show, and three are left for the user to try."""
from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import pymupdf

DEMO_NAME = "MATH241 Grader demo"
SAMPLE_MODEL = "sample results"      # shown where the model name goes; never a real model

ASSIGNMENT_ID = "demo_line_fit"

# --------------------------------------------------------------------------------------- the assignment
HANDOUT = """
<h1>Demo assignment: Fitting a line</h1>
<p class="sub">Sample course · AI-assisted assignment · made up for the MATH241 Grader tour</p>
<p>You may use an AI assistant for this assignment. The report must show your own understanding, and the
complete AI conversation must be included.</p>
<h2>Task 1: Derivation</h2>
<p>For the line y = a x + b, derive the least-squares estimates of a and b by minimizing
E(a, b) = sum of (y_i - a x_i - b)^2 over the data points. Show the two normal equations and solve them.</p>
<h2>Task 2: Code and results</h2>
<p>Write Python code that fits the line to the eight points below. Report a, b and the sum of squared errors.</p>
<table>
<tr><th>x</th><td>0</td><td>1</td><td>2</td><td>3</td><td>4</td><td>5</td><td>6</td><td>7</td></tr>
<tr><th>y</th><td>1.1</td><td>2.9</td><td>5.2</td><td>7.1</td><td>8.8</td><td>11.2</td><td>13.1</td><td>14.9</td></tr>
</table>
<h2>Task 3: Verification</h2>
<p>Verify your fit in two ways: (a) show that the residuals sum to zero, (b) compare a and b with numpy.polyfit.
Every value you report must be produced by the code you submit.</p>
<h2>Report format</h2>
<p>At most 3 pages, with the headings Derivation, Implementation, Results, Verification and Discussion.
Appendix A: the complete AI conversation as text. Appendix B: your code as text.</p>
"""

GUIDE = """
<h1>Instructor guide: Fitting a line</h1>
<p>Reference solution. Normal equations: a sum x_i^2 + b sum x_i = sum x_i y_i and a sum x_i + n b = sum y_i.
For the given data, a = 1.9917, b = 1.0667, sum of squared errors 0.1558. The residuals sum to zero up to
rounding, and numpy.polyfit gives the same a and b.</p>
<p>Derivation (30): both partial derivatives set to zero, both normal equations, solved correctly.
Code and results (30): correct a, b and error, produced by the submitted code.
Verification (20): both checks, produced by the code. Discussion (20): what the fit shows and its limits.</p>
"""

RUBRIC = [
    {"id": "derivation", "group": "Task 1: Derivation", "label": "Derivation", "max": 30,
     "description": "The normal equations are derived and solved correctly.",
     "screening_focus": "Both partial derivatives set to zero, both normal equations, a and b solved."},
    {"id": "code_results", "group": "Task 2: Code", "label": "Code and results", "max": 30,
     "description": "The code fits the line and the reported a, b and error are correct.",
     "screening_focus": "a close to 1.9917, b close to 1.0667, error 0.1558, all produced by the submitted code."},
    {"id": "checks", "group": "Task 3: Verification", "label": "Verification", "max": 20,
     "description": "Both checks are done by the submitted code.",
     "screening_focus": "Residual sum and the numpy.polyfit comparison, both computed in Appendix B."},
    {"id": "discussion", "group": "Task 3: Verification", "label": "Discussion", "max": 20,
     "description": "The discussion explains what the fit shows and where it would fail.",
     "screening_focus": "Specific to this data, not generic remarks about least squares."},
]

CATEGORIES = [
    {"id": "untraceable_results", "label": "Results or checks not produced by the submitted work",
     "description": "Reported values that the submitted code, its output or the AI record do not produce.",
     "points": 5, "row_cap_pct": 25, "half_row_cap_pct": 50, "default_rows": ["checks"],
     "student_text": "Some reported results or checks could not be traced to the code or AI record you submitted.",
     "ta_check": "Look for the reported values in the code (Appendix B). Confirm only if they are not produced there."},
    {"id": "unsupported_claim", "label": "Claimed process not supported by the AI record",
     "description": "The report describes a correction or step that does not appear in the AI record or code.",
     "points": 4, "row_cap_pct": None, "half_row_cap_pct": None, "default_rows": [],
     "student_text": "The report describes work that does not appear in your submitted AI record or code.",
     "ta_check": "Find the step the report describes, then look for it in the AI record."},
    {"id": "missing_record", "label": "AI record missing",
     "description": "No AI interaction record was submitted at all.", "points": 60, "row_cap_pct": None,
     "half_row_cap_pct": None, "default_rows": [],
     "student_text": "No AI interaction record was submitted. The assignment required it in Appendix A.",
     "ta_check": "Check the end of the PDF for any AI conversation. Confirm if there is none."},
    {"id": "link_only_record", "label": "AI record given only as a link",
     "description": "A share link was given instead of the conversation itself.", "points": 30,
     "row_cap_pct": None, "half_row_cap_pct": None, "default_rows": [],
     "student_text": "The AI record was given only as a link. The assignment required the conversation in the PDF.",
     "ta_check": "Check that the PDF holds only a link and not the conversation."},
    {"id": "incomplete_record", "label": "AI record incomplete or summarized",
     "description": "Responses replaced by descriptions, or parts of the conversation missing.", "points": 8,
     "row_cap_pct": None, "half_row_cap_pct": None, "default_rows": [],
     "student_text": "The AI interaction record was not complete.",
     "ta_check": "Check whether responses are replaced by descriptions or cut off."},
    {"id": "other", "label": "Other integrity concern",
     "description": "Any other concrete concern the grader wants the instructor to see.", "points": 0,
     "row_cap_pct": None, "half_row_cap_pct": None, "default_rows": [],
     "student_text": "An integrity concern was noted by the grader.",
     "ta_check": "Read the note and decide whether it is a real problem."},
]


def pack_json() -> dict:
    return {
        "pack_version": 1, "id": ASSIGNMENT_ID, "course": "Sample course",
        "title": "Demo assignment: Fitting a line", "short_name": "DEMO-LINE",
        "files": {"assignment": "assignment.pdf", "instructor_guide": "instructor_guide.pdf"},
        "model": {"name": "gpt-6-luna", "label": "GPT-6 Luna (default, cheapest)",
                  "escalation_name": "gpt-6-sol", "escalation_label": "GPT-6 Sol (stronger, much more expensive)",
                  "reasoning_effort": "medium", "max_output_tokens": 16000, "max_report_images": 4},
        "report": {"page_limit": 3,
                   "appendix_chat_pattern": r"^(\d+\s+)?appendix\s*a\b",
                   "appendix_code_pattern": r"^(\d+\s+)?appendix\s*b\b",
                   "required_headings": [{"text": "Derivation", "row": "derivation"},
                                         {"text": "Implementation", "row": "code_results"},
                                         {"text": "Results", "row": "code_results"},
                                         {"text": "Verification", "row": "checks"},
                                         {"text": "Discussion", "row": "discussion"}]},
        "rubric": RUBRIC,
        "levels": [100, 75, 50, 25, 0],
        "level_descriptions": {"100": "Correct and complete.",
                               "75": "Mostly correct; one important part is missing or wrong.",
                               "50": "Main idea is present, but several important parts are missing or wrong.",
                               "25": "Only limited correct work is shown.",
                               "0": "Missing, unrelated, or no usable work."},
        "grading_rules": ["Do not deduct twice for the same error if later work follows from it.",
                          "AI use is allowed. Do not deduct because the writing looks AI-generated.",
                          "Results not produced by the submitted code count as not demonstrated."],
        "integrity": {"total_cap": 100, "categories": CATEGORIES,
                      "exclusive_groups": [["missing_record", "link_only_record"]]},
        "reference_checks": [
            {"id": "slope", "row": "code_results", "label": "Slope a close to 1.9917", "type": "number",
             "value": 1.9916667, "rel_tol": 0.002},
            {"id": "intercept", "row": "code_results", "label": "Intercept b close to 1.0667", "type": "number",
             "value": 1.0666667, "rel_tol": 0.002},
        ],
        "trace_checks": [
            {"id": "residual", "row": "checks", "label": "(a) residuals sum to zero",
             "report_patterns": ["residual"], "code_patterns": [r"resid"]},
            {"id": "polyfit", "row": "checks", "label": "(b) comparison with numpy.polyfit",
             "report_patterns": ["polyfit"], "code_patterns": [r"polyfit"]},
        ],
        "chat_placeholder_patterns": [r"\((?:the\s+)?AI\s+(?:provided|gave|wrote|returned)\b"],
        "accepted_alternatives": ["Any correct derivation counts, including matrix form with the normal equations "
                                  "A^T A p = A^T y."],
    }


# --------------------------------------------------------------------------------------- the students
DATA = "x = [0, 1, 2, 3, 4, 5, 6, 7]\ny = [1.1, 2.9, 5.2, 7.1, 8.8, 11.2, 13.1, 14.9]"

GOOD_CODE = DATA + """
n = len(x)
sx, sy = sum(x), sum(y)
sxx = sum(v * v for v in x)
sxy = sum(u * v for u, v in zip(x, y))
a = (n * sxy - sx * sy) / (n * sxx - sx * sx)
b = (sy - a * sx) / n
resid = [v - (a * u + b) for u, v in zip(x, y)]
sse = sum(r * r for r in resid)
print("a =", round(a, 4), "b =", round(b, 4), "SSE =", round(sse, 4))
print("sum of residuals =", sum(resid))
import numpy as np
print("polyfit:", np.polyfit(x, y, 1))
"""

SHORT_CODE = DATA + """
n = len(x)
sx, sy = sum(x), sum(y)
sxx = sum(v * v for v in x)
sxy = sum(u * v for u, v in zip(x, y))
a = (n * sxy - sx * sy) / (n * sxx - sx * sx)
b = (sy - a * sx) / n
print("a =", round(a, 4), "b =", round(b, 4))
"""

POLYFIT_CODE = DATA + """
import numpy as np
a, b = np.polyfit(x, y, 1)
resid = np.array(y) - (a * np.array(x) + b)
print("a =", round(a, 4), "b =", round(b, 4), "SSE =", round(float(resid @ resid), 4))
print("sum of residuals =", resid.sum())
print("polyfit:", np.polyfit(x, y, 1))
"""

CHAT = """<p><b>Student:</b> I need to fit a line y = a x + b to eight points by least squares. Can you explain
how to get the normal equations?</p>
<p><b>Assistant:</b> Start from the error E(a, b), the sum of the squared vertical distances between each point
and the line. E is a smooth function of a and b, so at its minimum both partial derivatives are zero. Taking the
derivative with respect to a gives one linear equation, and the derivative with respect to b gives a second one.
Together they are the normal equations, two linear equations in two unknowns.</p>
<p><b>Student:</b> I wrote dE/da = -2 sum x_i (y_i - a x_i - b). Is that right, and what about b?</p>
<p><b>Assistant:</b> Yes, that is right. For b you get dE/db = -2 sum (y_i - a x_i - b). Setting both to zero and
dividing by -2 gives a sum x_i^2 + b sum x_i = sum x_i y_i and a sum x_i + n b = sum y_i. You can solve these by
elimination, or write them as a 2 by 2 matrix system.</p>
<p><b>Student:</b> How do I check the code without trusting it blindly?</p>
<p><b>Assistant:</b> Two quick checks. The residuals of a least-squares line with an intercept always sum to zero,
so print their sum and expect a number close to zero. Then compare your a and b with numpy.polyfit(x, y, 1), which
fits the same line independently.</p>"""

DERIV_SHARED = """<p>We want the line that makes the total squared error as small as possible. The error E(a, b) is
the sum over all points of (y_i - a x_i - b)^2. This function is a smooth bowl in the two unknowns, so its lowest
point is where both partial derivatives vanish at the same time. Differentiating with respect to a gives
-2 sum x_i (y_i - a x_i - b) = 0, and differentiating with respect to b gives -2 sum (y_i - a x_i - b) = 0.
Dividing by minus two and collecting the terms that contain the unknowns leads to the two normal equations,
a sum x_i^2 + b sum x_i = sum x_i y_i and a sum x_i + n b = sum y_i. These form a small linear system with two
equations and two unknowns. Solving the second equation for b gives b = (sum y_i - a sum x_i) / n, and putting
this into the first equation leaves one equation in a alone. Solving it gives
a = (n sum x_i y_i - sum x_i sum y_i) / (n sum x_i^2 - (sum x_i)^2). The denominator is zero only when every x
value is the same, which is exactly the case where no unique line exists, so for our data the solution is
unique and the minimum found this way is the global minimum of the error.</p>"""

DISC_SHARED = """<p>The fitted line follows the data closely, and the largest residual is small compared with the
spread of the y values, so a straight line is a good description of these points. The slope tells us that y grows
by roughly two units for every unit of x. The fit would become unreliable if one of the points were an outlier,
because squaring the errors gives large deviations a strong pull on the line. It would also be a poor model if
the points followed a curve, since the residuals would then show a clear pattern instead of looking random.</p>"""

STUDENTS = [
    # key, first, last, Moodle number, ID
    ("ayse", "Ayşe", "Örnek", "7001", "22100101"),
    ("burak", "Burak", "Deneme", "7002", "22100102"),
    ("ceren", "Ceren", "Taslak", "7003", "22100103"),
    ("deniz", "Deniz", "Prova", "7004", "22100104"),
    ("ilker", "İlker", "Sınama", "7005", "22100105"),
    ("zeynep", "Zeynep", "Kurgu", "7006", "22100106"),
]


def _report(key: str) -> tuple[str, str, str]:
    """(report html, chat html, code) for one student."""
    if key == "ayse":
        rep = """
<h2>Derivation</h2>
<p>I minimize E(a, b), the sum of (y_i - a x_i - b)^2. At the minimum both partial derivatives are zero.
From dE/da = 0 and dE/db = 0, after dividing by -2, I get the normal equations
a Sxx + b Sx = Sxy and a Sx + n b = Sy, where Sx, Sy, Sxx and Sxy are the sums of x, y, x squared and x times y.
Eliminating b gives a = (n Sxy - Sx Sy) / (n Sxx - Sx^2) and then b = (Sy - a Sx) / n. The denominator is
positive whenever the x values are not all equal, so the solution exists and is unique.</p>
<h2>Implementation</h2>
<p>The code in Appendix B computes the four sums directly and then a and b from the closed form. It also computes
the residuals, their sum, the sum of squared errors, and the numpy.polyfit result for comparison.</p>
<h2>Results</h2>
<p>For the eight points: a = 1.9917, b = 1.0667, and the sum of squared errors is 0.1558.</p>
<h2>Verification</h2>
<p>(a) The residuals sum to 2.4e-14, which is zero up to rounding. (b) numpy.polyfit gives
[1.99166667, 1.06666667], the same values as my closed form.</p>
<h2>Discussion</h2>
<p>The largest residual is 0.23, small next to the range of y, so the line describes the data well. The point at
x = 4 lies furthest below the line. One wrong measurement would move the line noticeably, because least squares
weighs large errors heavily.</p>"""
        return rep, CHAT, GOOD_CODE
    if key == "burak":
        rep = """
<h2>Derivation</h2>
<p>The squared error is E(a, b) = sum (y_i - a x_i - b)^2. Setting the derivative with respect to a and the
derivative with respect to b to zero gives a Sxx + b Sx = Sxy and a Sx + n b = Sy. Solving the second for b and
substituting into the first gives a = (n Sxy - Sx Sy) / (n Sxx - Sx^2), then b = (Sy - a Sx) / n.</p>
<h2>Implementation</h2>
<p>Appendix B computes the sums and the closed-form a and b.</p>
<h2>Results</h2>
<p>a = 1.9917 and b = 1.0667. The sum of squared errors is 0.1558.</p>
<h2>Verification</h2>
<p>(a) The residuals sum to 1.1e-15, so they cancel as expected. (b) numpy.polyfit returns a = 1.99167 and
b = 1.06667, which agrees with my results.</p>
<h2>Discussion</h2>
<p>The points lie close to the line, with no visible pattern in the errors, so a linear model fits. Since the
errors are squared, a single outlier would pull the line towards itself, which is the main weakness of the method
for real measurements.</p>"""
        return rep, CHAT, SHORT_CODE
    if key == "ceren":
        rep = """<h2>Derivation</h2>""" + DERIV_SHARED + """
<h2>Implementation</h2>
<p>My code computes the sums, then a and b from the formulas above, and the residuals.</p>
<h2>Results</h2>
<p>a = 1.9917, b = 1.0667, sum of squared errors 0.1558.</p>
<h2>Verification</h2>
<p>The residuals sum to 2.4e-14, which is zero within rounding error.</p>
<h2>Discussion</h2>""" + DISC_SHARED
        return rep, CHAT, GOOD_CODE.replace('import numpy as np\nprint("polyfit:", np.polyfit(x, y, 1))\n', "")
    if key == "deniz":
        rep = """<h2>Derivation</h2>""" + DERIV_SHARED + """
<h2>Implementation</h2>
<p>The code uses the closed form, prints the residual sum and compares with numpy.polyfit.</p>
<h2>Results</h2>
<p>a = 1.99, b = 1.1, sum of squared errors 0.16.</p>
<h2>Verification</h2>
<p>(a) Sum of residuals: 2.4e-14. (b) numpy.polyfit gives the same slope and intercept.</p>
<h2>Discussion</h2>""" + DISC_SHARED
        return rep, CHAT, GOOD_CODE
    if key == "ilker":
        rep = """
<h2>Derivation</h2>
<p>I minimize E(a, b), the sum of the squared differences between y_i and a x_i + b. Setting dE/da = 0 gives
a Sxx + b Sx = Sxy. With the formula for b from the averages, b = mean(y) - a mean(x), this gives
a = 1.9917 for our data.</p>
<h2>Implementation</h2>
<p>The code in Appendix B uses the closed-form formulas and checks the result with numpy.</p>
<h2>Results</h2>
<p>a = 1.9917, b = 1.0667, and the sum of squared errors is 0.1558.</p>
<h2>Verification</h2>
<p>(a) The sum of the residuals is 2.4e-14. (b) numpy.polyfit gives 1.99166667 and 1.06666667.</p>
<h2>Discussion</h2>
<p>All residuals are below 0.25, so the linear fit is good. Extrapolating far beyond x = 7 would be risky, since
nothing in eight points tells us the trend continues.</p>"""
        chat = "<p>My full AI conversation: https://chatgpt.com/share/demo-0000-line-fit</p>"
        return rep, chat, GOOD_CODE
    # zeynep
    rep = """
<h2>Derivation</h2>
<p>E(a, b) is the sum of (y_i - a x_i - b)^2. The AI first gave me dE/da with the wrong sign, and I corrected it
by redoing the chain rule myself. Setting the derivatives to zero gives a Sxx - b Sx = Sxy and a Sx + n b = Sy,
which I solved for a and b.</p>
<h2>Implementation</h2>
<p>I used numpy.polyfit for the fit and computed the residuals and their squares.</p>
<h2>Results</h2>
<p>a = 1.9917, b = 1.0667, sum of squared errors 0.1558.</p>
<h2>Verification</h2>
<p>(a) The residuals add up to -3.6e-15. (b) The polyfit values match the slope and intercept above.</p>
<h2>Discussion</h2>
<p>The fit is close, with residuals of at most 0.23 and alternating signs, so there is no sign of curvature. With
only eight points the slope estimate would still change if one point were removed.</p>"""
    return rep, CHAT, POLYFIT_CODE


# what the AI pre-screen "found", written in advance for each student --------------------------------------
def _row(rid, status, reason, check="", excerpt="", page=1, conf="high"):
    return {"row_id": rid, "status": status, "reason": reason, "ta_check": check, "confidence": conf,
            "evidence": [{"source": "report", "page": page, "excerpt": excerpt}] if excerpt else []}


AI = {
    "ayse": {"rows": [
        _row("derivation", "green", "Both normal equations derived and solved, uniqueness explained.",
             excerpt="Eliminating b gives"),
        _row("code_results", "green", "a, b and the error match the reference and come from the code in Appendix B.",
             excerpt="a = 1.9917, b = 1.0667"),
        _row("checks", "green", "Both checks are reported and both are computed in Appendix B.",
             excerpt="numpy.polyfit gives"),
        _row("discussion", "green", "Specific to this data: names the largest residual and the effect of an outlier.",
             excerpt="The largest residual is 0.23"),
    ], "integrity": [], "overall_note": "Complete and consistent. Nothing needs a closer look."},
    "burak": {"rows": [
        _row("derivation", "green", "Normal equations derived and solved correctly.", excerpt="Solving the second for b"),
        _row("code_results", "yellow", "a and b are correct and printed by the code. The sum of squared errors is "
             "reported but the code never computes it.", "Check whether 0.1558 can come from the submitted code.",
             excerpt="The sum of squared errors is 0.1558"),
        _row("checks", "red", "Both checks are reported, but the code in Appendix B computes neither the residuals "
             "nor a numpy.polyfit comparison.", "Confirm that neither check appears in Appendix B or in the AI record.",
             excerpt="The residuals sum to 1.1e-15"),
        _row("discussion", "green", "Short but specific: no pattern in the errors, sensitivity to outliers.",
             excerpt="a single outlier would pull the line"),
    ], "integrity": [{
        "category": "untraceable_results",
        "summary": "The residual sum 1.1e-15, the polyfit values and the error 0.1558 are reported, but the code in "
                   "Appendix B only prints a and b, and the AI record does not show these values either.",
        "ta_check": "Read Appendix B. Confirm if none of these values can come from it.",
        "affected_rows": ["checks"],
        "evidence": [{"source": "report", "page": 1, "excerpt": "The residuals sum to 1.1e-15"}]}],
        "overall_note": "The checks are reported but not done by the submitted code."},
    "ceren": {"rows": [
        _row("derivation", "green", "Full derivation with a uniqueness argument.", excerpt="smooth bowl"),
        _row("code_results", "green", "Correct values, produced by the code.", excerpt="a = 1.9917, b = 1.0667"),
        _row("checks", "yellow", "Only the residual check is done. The numpy.polyfit comparison is missing.",
             "Decide how much the missing second check costs.", excerpt="The residuals sum to 2.4e-14"),
        _row("discussion", "yellow", "Correct but general. It does not refer to particular points or residuals.",
             "Decide whether this is specific enough for full marks.", excerpt="a good description of these points",
             conf="medium"),
    ], "integrity": [], "overall_note": "One of the two checks is missing."},
    "deniz": {"rows": [
        _row("derivation", "green", "Full derivation with a uniqueness argument.", excerpt="smooth bowl"),
        _row("code_results", "yellow", "Values are rounded too much: b = 1.1 and an error of 0.16 hide the precision "
             "the code gives.", "Decide whether the rounding costs anything.", excerpt="a = 1.99, b = 1.1",
             conf="medium"),
        _row("checks", "green", "Both checks are reported and computed in Appendix B.",
             excerpt="Sum of residuals: 2.4e-14"),
        _row("discussion", "yellow", "Correct but general. It does not refer to particular points or residuals.",
             "Decide whether this is specific enough for full marks.", excerpt="a good description of these points",
             conf="medium"),
    ], "integrity": [], "overall_note": "Results are over-rounded."},
    "ilker": {"rows": [
        _row("derivation", "yellow", "Only the equation for a is derived. b comes from a formula that is stated, not "
             "derived from the second normal equation.", "Decide whether stating b's formula is enough.",
             excerpt="With the formula for b from the averages"),
        _row("code_results", "green", "Correct values, produced by the code.", excerpt="a = 1.9917, b = 1.0667"),
        _row("checks", "green", "Both checks are reported and computed in Appendix B.",
             excerpt="numpy.polyfit gives 1.99166667"),
        _row("discussion", "green", "Specific: residual size and a warning about extrapolation.",
             excerpt="Extrapolating far beyond x = 7"),
    ], "integrity": [{
        "category": "link_only_record",
        "summary": "Appendix A contains only a share link, not the conversation.",
        "ta_check": "Check that the PDF has no conversation text.",
        "affected_rows": [], "evidence": [{"source": "chat", "page": 2, "excerpt": "chatgpt.com/share"}]}],
        "overall_note": "The AI record is only a link."},
    "zeynep": {"rows": [
        _row("derivation", "red", "Sign error: the first normal equation is written as a Sxx - b Sx = Sxy. The "
             "results are still right because the code uses numpy.polyfit, not this derivation.",
             "Grade the derivation on its own.", excerpt="a Sxx - b Sx = Sxy"),
        _row("code_results", "green", "Correct values from numpy.polyfit in Appendix B.", excerpt="a = 1.9917, b = 1.0667"),
        _row("checks", "green", "Both checks are computed in Appendix B.", excerpt="The residuals add up to"),
        _row("discussion", "green", "Specific: residual size, alternating signs, sensitivity with eight points.",
             excerpt="alternating signs"),
    ], "integrity": [{
        "category": "unsupported_claim",
        "summary": "The report says the AI first gave dE/da with the wrong sign and that the student corrected it. "
                   "In the AI record the assistant confirms the student's own derivative and never gives a wrong sign.",
        "ta_check": "Read the AI record. Confirm if no wrong sign from the AI appears there.",
        "affected_rows": ["derivation"],
        "evidence": [{"source": "report", "page": 1, "excerpt": "The AI first gave me dE/da with the wrong sign"}]}],
        "overall_note": "Derivation has a sign error, and the story about correcting the AI is not in the record."},
}

# three students already graded, so the overview and the export have something to show ---------------------------
GRADED = {
    "ayse": ({"derivation": 100, "code_results": 100, "checks": 100, "discussion": 75},
             {"discussion": "Good. Say what the residual pattern means for the model."}, {},
             "Very clear and complete work."),
    "burak": ({"derivation": 100, "code_results": 75, "checks": 25, "discussion": 100},
              {"code_results": "The error 0.1558 is not computed by your code.",
               "checks": "Neither check is done by the submitted code."}, {"untraceable_results": "full"},
              "Every value you report has to come from the code you submit."),
    "zeynep": ({"derivation": 50, "code_results": 100, "checks": 100, "discussion": 100},
               {"derivation": "Sign error in the first normal equation."}, {"unsupported_claim": "rejected"},
               "Check the signs when you differentiate."),
}


# --------------------------------------------------------------------------------------- writing the files
CSS = """
* { font-family: sans-serif; }
body { font-size: 10.5pt; color: #111; }
h1 { font-size: 15pt; margin: 0 0 4pt 0; }
h2 { font-size: 12pt; margin: 12pt 0 3pt 0; }
p { margin: 0 0 6pt 0; line-height: 1.35; }
.sub { color: #555; font-size: 9.5pt; }
pre { font-family: monospace; font-size: 9pt; }
table { border-collapse: collapse; margin: 4pt 0 8pt 0; }
td, th { border: 1px solid #999; padding: 2pt 6pt; font-size: 9.5pt; }
"""


def _pdf(parts: list[str]) -> bytes:
    """One PDF from HTML parts; each part starts on a new page."""
    out = pymupdf.open()
    for html in parts:
        buf = io.BytesIO()
        story = pymupdf.Story(html=html, user_css=CSS)
        writer = pymupdf.DocumentWriter(buf)
        box = pymupdf.paper_rect("a4")
        more = True
        while more:
            dev = writer.begin_page(box)
            more, _ = story.place(box + (56, 56, -56, -56))
            story.draw(dev)
            writer.end_page()
        writer.close()
        with pymupdf.open("pdf", buf.getvalue()) as d:
            out.insert_pdf(d)
    data = out.tobytes(garbage=3, deflate=True)
    out.close()
    return data


def _student_pdf(key: str, first: str, last: str, sid_number: str) -> bytes:
    import html as h
    rep, chat, code = _report(key)
    head = (f"<h1>Fitting a line</h1><p class='sub'>{h.escape(first)} {h.escape(last)} · Student ID {sid_number}"
            f" · Demo assignment</p>")
    return _pdf([head + rep, "<h2>Appendix A: AI conversation</h2>" + chat,
                 "<h2>Appendix B: Code</h2><pre>" + h.escape(code.strip()) + "</pre>"])


def write_sources(root: Path) -> dict:
    """The files an instructor would start from: assignment folder, class list, Moodle download."""
    import openpyxl
    root.mkdir(parents=True, exist_ok=True)
    asg = root / "Demo assignment"
    asg.mkdir(exist_ok=True)
    (asg / "pack.json").write_text(json.dumps(pack_json(), indent=1, ensure_ascii=False), encoding="utf-8")
    (asg / "assignment.pdf").write_bytes(_pdf([HANDOUT]))
    (asg / "instructor_guide.pdf").write_bytes(_pdf([GUIDE]))
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["First name", "Last name", "ID number", "Email address"])
    for key, first, last, _, idn in STUDENTS:
        ws.append([first, last, idn, f"{key}@example.edu"])
    cls = root / "class list.xlsx"
    wb.save(cls)
    moodle = root / "Moodle download"
    for key, first, last, num, idn in STUDENTS:
        d = moodle / f"{first} {last}_{num}_assignsubmission_file_"
        d.mkdir(parents=True, exist_ok=True)
        (d / "line_fit_report.pdf").write_bytes(_student_pdf(key, first, last, idn))
    return {"pack": asg, "classlist": cls, "submissions": moodle}


class DemoScreener:
    """Stands in for the AI in the demo: returns the results written above. Never touches the network."""

    def __init__(self, pack):
        self.pack = pack

    def screen(self, ext, checks, pdf_path, global_note="", ta_note="", model_override=None, on_stage=None,
               custom_instructions=None, effort=None) -> dict:
        from .llm import prompt_version, validate
        key = _key_for(pdf_path)
        data = validate(self.pack, json.loads(json.dumps(AI.get(key) or AI["ayse"])))
        data["_meta"] = {"model": SAMPLE_MODEL, "input_tokens": 0, "output_tokens": 0, "images": [],
                         "instructions": "default", "effort": "medium",
                         "prompt_version": prompt_version(custom_instructions or "", global_note),
                         "student_note": bool((ta_note or "").strip())}
        data["_prompt_text"] = "(Demo: sample results written in advance. Nothing was sent to the AI.)"
        data["_raw"] = None
        return data


def _key_for(pdf_path) -> str:
    """Submissions are kept as submissions/<Moodle number>.pdf."""
    return {num: key for key, _, _, num, _ in STUDENTS}.get(Path(pdf_path).stem, "")


def is_demo(store) -> bool:
    try:
        return bool(store and store.get_meta("demo"))
    except Exception:  # noqa: BLE001
        return False


def build(folder: Path) -> Path:
    """Make a fresh demo workspace in `folder` (replacing an older demo there). Returns the folder."""
    from .pack import load_pack
    from .pipeline import process_submission, register_submissions
    from .scoring import new_review_from_screen
    from .store import Store
    from .workspace import import_classlist, import_pack
    from . import similarity
    folder = Path(folder)
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    src = write_sources(folder / "sample files")
    store = Store(folder / "grading.db")
    store.set_meta("demo", True)
    store.set_meta("reviewer", "Demo grader")
    pack = load_pack(import_pack(store, src["pack"]))
    cls = import_classlist(store, src["classlist"])
    store.set_meta("submissions_path", str(src["submissions"]))
    register_submissions(store, src["submissions"], cls)
    store.set_meta("submissions_path", str(folder / "submissions"))     # as after a real import
    by_num = {num: key for key, _, _, num, _ in STUDENTS}
    screener = DemoScreener(pack)
    for r in store.submissions():
        process_submission(store, pack, r["sub_id"], screener)
    rep = similarity.run(store, pack, folder)
    store.set_meta(similarity.REPORT_KEY, rep)
    for r in store.submissions():
        key = by_num.get(r["sub_id"])
        if key not in GRADED:
            continue
        levels, comments, decisions, overall = GRADED[key]
        rev = new_review_from_screen(pack, json.loads(r["screen"]), "Demo grader")
        rev["levels"].update(levels)
        rev["comments"].update(comments)
        for f in rev["findings"]:
            if f["category"] in decisions:
                f["decision"] = decisions[f["category"]]
                if f["decision"] == "rejected":
                    f["comment"] = "Not a real problem."
        rev["overall_comment"] = overall
        rev["reviewed"] = True
        store.save_review(r["sub_id"], rev)
    similarity.add_findings(store, pack, rep, "Demo grader")
    return folder
