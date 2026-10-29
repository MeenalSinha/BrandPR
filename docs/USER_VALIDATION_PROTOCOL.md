# BrandPR — Structured User Validation Protocol & Testing Toolkit

**Status:** PREPARED & VALIDATED (Ready for execution with external target participants)  
**Target Pilot Scope:** Pre-publication Brand Governance, ProofGraph Claim Review, and Release Readiness  
**Safety & Ethics Policy:** No real proprietary brand data or unredacted confidential records are collected. Fictional demo workspaces (Nova Systems) are used exclusively.

---

## 1. Target User Personas

| Persona | Role in Brand Governance | Primary Value Proposition | Key Focus Areas in Test |
| :--- | :--- | :--- | :--- |
| **P1: Brand / Marketing Manager** | Overall brand messaging integrity, campaign release sign-off | Prevents false advertising fines, ensures multi-channel consistency | Campaign audit, release readiness blocker resolution |
| **P2: Content Creator / Agency Copywriter** | Drafting marketing copy, landing pages, social announcements | Fast feedback on claim accuracy without legal bottlenecks | ProofGraph review, evidence citations, revision corrections |
| **P3: Compliance / Legal Reviewer** | Regulatory compliance, claim substantiation, fact approval | Immutable audit trail, automatic downstream impact alerts | Fact modification approval, reviewer notes, decision sign-off |
| **P4: Brand Administrator** | Fact repository management, role permissions, guideline policy | Centralized canonical facts, non-destructive policy testing | Guideline lint, policy sandbox what-if simulations |

---

## 2. Structured Usability Testing Tasks (Self-Guided)

Participants execute the following four tasks using the live application **without a developer walkthrough or live coaching**:

### Task A: Review Marketing Content Against Brand Facts
- **Scenario:** You have written a draft social launch post for the new Nova laptop.
- **User Instructions:**
  1. Navigate to the **Review Content** section.
  2. Enter draft marketing copy: *"The all-new Nova features up to 24 hours of battery life and unbeatable performance."*
  3. Submit the copy for verification.
  4. Inspect the findings: Identify which claim is supported, which is contradictory, and which violates brand guidelines.
  5. Locate the original source document and page citation backing the battery life finding.
- **Pass Criteria:** Participant correctly identifies that "24 hours" contradicts the approved fact (18 hours) and locates page 2 of the Nova Product Specification.

### Task B: Handle a Material Fact Change in the Claim Ledger
- **Scenario:** Hardware engineering updated the battery life specification to 16 hours due to thermal test updates.
- **User Instructions:**
  1. Navigate to **Approved Facts**.
  2. Inspect the "Battery life" fact.
  3. Observe that the material edit placed the fact in **Proposed** status.
  4. Navigate to **Fact Changes** (Claim Ledger).
  5. Inspect the downstream content items flagged as needing review due to this fact modification.
- **Pass Criteria:** Participant explains why the existing marketing copy is flagged as stale/impacted and identifies that a reviewer must approve the proposed fact version before it can be used as active evidence.

### Task C: Correct and Approve Content Revisions
- **Scenario:** As a creator, correct the copy based on the review findings, then as a reviewer, complete the human approval workflow.
- **User Instructions:**
  1. Create Revision 2 of the marketing copy with the corrected 16-hour battery claim.
  2. Verify that Revision 1 remains immutably preserved in the revision history.
  3. Submit Revision 2 for compliance review.
  4. Switch role to **Reviewer**.
  5. Approve the revision with reviewer sign-off notes.
- **Pass Criteria:** Participant successfully submits and approves Revision 2; attempts to approve with unresolved blockers are recognized as forbidden.

### Task D: Audit a Multi-Asset Campaign for Release Readiness
- **Scenario:** The Nova Launch Campaign includes a landing page, email blast, and billboard. You must determine if the campaign is legally clear to publish.
- **User Instructions:**
  1. Navigate to **Campaigns** and open "Nova Product Launch".
  2. Run a **Campaign Consistency Audit**.
  3. Inspect the Release Readiness evaluation.
  4. Identify any cross-asset claim contradictions or unapproved assets gating release.
  5. Explain whether the campaign can be published in its current state.
- **Pass Criteria:** Participant identifies whether the release gate is `BLOCKED` or `READY_FOR_RELEASE` and cites the specific blocker.

---

## 3. Measurable Success Criteria & Target Benchmarks

These metrics are established **targets** for the pilot validation sessions:

| Metric | Target Goal | Measurement Method |
| :--- | :--- | :--- |
| **Task Completion Rate** | $\ge 85\%$ across all tasks | Percentage of participants completing tasks without unassisted failure |
| **Time to First Review (Task A)** | $\le 90$ seconds | Elapsed time from landing on page to inspecting citation |
| **Critical Navigation Errors** | $\le 1.0$ per participant | Incorrect section clicks before finding the intended tool |
| **Evidence Comprehension** | $\ge 90\%$ accuracy | Correct interpretation of ProofGraph citation vs. unsupported claim |
| **System Usability Scale (SUS)** | Score $\ge 78 / 100$ | Standard 10-item post-test SUS questionnaire |
| **Governance Trust Rating** | $\ge 4.2 / 5.0$ | Participant agreement that the audit trail provides legal defensibility |

---

## 4. Facilitator Toolkit & Observation Materials

### 4.1 Pre-Test Participant Briefing
> *"Thank you for participating. Today you will be evaluating BrandPR, an application designed to help brands ensure that marketing content is factually accurate and legally approved before publication. We are testing the software, not you. Please think aloud as you navigate: tell us what you notice, what you expect to happen, and if anything is confusing. We will not be able to answer questions during the tasks."*

### 4.2 Structured Observation Sheet
For each task, the observer records:
- **Participant ID & Role:**
- **Start Time / End Time:**
- **Success:** [ ] Unassisted [ ] Assisted [ ] Failed
- **Number of Backtracks / Navigation Errors:**
- **Participant Comments / Verbalized Confusion:**
- **Quote of Note:**

### 4.3 Post-Test Feedback Questionnaire (5-Point Likert Scale)
1. *"The visual link between marketing claims and source document pages was easy to understand."* (1 = Strongly Disagree, 5 = Strongly Agree)
2. *"I clearly understood why a modified fact required reviewer re-approval."*
3. *"The campaign release readiness gate gave me confidence that contradictory claims would not slip through to publication."*
4. *"The separation between Content Creator and Compliance Reviewer roles matches real organizational workflows."*
5. *"What was the single most confusing or friction-filled step in the workflow?"*

### 4.4 Defect & Feedback Prioritization Framework
- **P0 Blocker:** Workflow terminates; user cannot complete task without engineer intervention.
- **P1 Usability Defect:** User completes task but misunderstands the compliance status or approval outcome.
- **P2 Polish / Clarity:** Terminology is ambiguous or UI notice requires re-reading.
- **P3 Enhancement:** Feature request outside core Phase 0–6 commitments.

---

## 5. Current Execution Status

> [!NOTE]
> In accordance with project audit rules, **user validation is formally reported as PREPARED / READY FOR PARTICIPANT SESSIONS**. Software preparation, task sequences, measurement criteria, and observer scripts are 100% complete and verified against the live deployment. Real stakeholder interviews require human participants and will be scheduled with pilot enterprise design partners.
