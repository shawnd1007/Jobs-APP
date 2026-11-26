# Personalized job board research and design

This research informed the original job-board design. Use the [approved vision](PRODUCT-VISION.md) for product requirements and the [roadmap](NEXT-STEPS.md) for current priorities.

## What established products do

| Reference | Observed behavior | Design implication for Jobs |
| --- | --- | --- |
| Indeed search and profile | Uses résumé and saved preferences to inform relevance. Search filters include pay, location and distance, with suggested refinements for skills and other fields. | Make onboarding useful with just role, location and pay. Let users improve ranking by choosing which résumé skills they want to use. Keep result filters separate from durable preferences. [Indeed search guidance](https://www.indeed.com/career-advice/finding-a-job/tips-on-how-to-get-better-search-results-on-indeed.com) |
| Indeed résumé upload | Supports text-based documents and notes that scanned PDFs can fail to parse. | Preview extracted content, give clear recovery steps, and let the user replace or remove it. Support text PDFs and UTF-8 text in the first version. [Indeed résumé formats](https://support.indeed.com/hc/en-ca/articles/204288994-Can-I-use-my-Resumes-original-formatting-style-and-chronology-Why-did-my-Resumes-format-change) |
| LinkedIn recommendations | Separates job-title, location, workplace and employment-type preferences from experience-based recommendations. Preferences are editable and private by default. | Store work setting separately from geography. Explain why each listing surfaced. Treat résumé phrases as suggestions, since a phrase alone cannot establish a qualification or a career goal. [LinkedIn recommendations](https://www.linkedin.com/help/linkedin/answer/a512279/) |
| O*NET occupation search | Provides occupation and software-skill entry points. | Add occupation and skill synonyms over time, retaining custom terms for niche roles. Evaluate a catalog against several job families before expanding the starter list. [O*NET advanced search](https://www.onetonline.org/help/online/adv_search) |
| Google JobPosting | Models physical locations, remote eligibility and employer-reported salary in separate fields. It also supports expiration and employer application information. | Keep employer data distinct from user preferences and derived matches. Surface published pay and its basis, residence restrictions, source and freshness. Preserve unknowns for review. [Google JobPosting documentation](https://developers.google.com/search/docs/appearance/structured-data/job-posting) |
| Indeed job alerts and My Jobs | Alerts retain editable search criteria and frequency. My Jobs organizes jobs the seeker is considering or has acted on, with limited visibility into off-site applications. | Make a saved search a reusable object once users need multiple goals. Retain explicit user tracking for applications made on employer sites. [Indeed job alerts](https://support.indeed.com/hc/en-in/articles/204488890-Starting-Stopping-and-Managing-Job-Alerts), [Indeed My Jobs](https://support.indeed.com/hc/en-us/articles/205332490-What-is-My-Jobs) |

## Search journey and first release

1. **Set preferences.** Import a résumé or begin with a role. Pick skills to use and add custom skills. Set the locations, work arrangements and annual USD base-pay target. Make the effect of each choice visible when editing.
2. **Find and refine.** Run a search against configured employer sources. Show title, employer, location, pay, verification and match reasoning. The existing list filters provide temporary refinement. The saved preferences drive ranking and eligibility.
3. **Review exceptions.** Keep remote listings with ambiguous residence rules in review. Leave missing pay visible for human follow-up. Show the employer’s listing and preserve a separate record of what the user verified.
4. **Act and track.** Send the user to the employer posting. Save the user’s decision, application status and follow-up in the workspace.

Build 9 imports PDF or UTF-8 text and keeps a removable, device-local preview. Users can save selected skills and explicitly added experience to the Mac profile. An explicitly requested AI review can use that saved profile. The full imported preview stays on the device. Location matching uses published place phrases and work-setting signals, with uncertain cases held for review.

## Original research recommendations

| Priority | Work | Acceptance evidence |
| --- | --- | --- |
| 1 | Improve location and pay evidence with structured regions, multiple worksites, hiring jurisdictions, pay currency and period. | Test remote exclusions, ambiguous cities, multiple locations, hourly pay and missing salary. Show the employer’s published values and provenance on the card. |
| 2 | Support named saved searches for different role and salary goals. Build 9 includes saved searches and a match inbox. Delivery options remain on the roadmap. | Switching searches restores all relevant settings. A repeated employer listing generates one alert per relevant search, with pause and deletion controls. |
| 3 | Broaden job supply with employer-source coverage and freshness tracking. | Report last successful check per source and distinguish source failures from confirmed closure. Measure duplicate and stale listing rates against a labeled sample. |
| 4 | Add accounts before sharing a deployment across people. | Separate résumé data, preferences, review decisions and application histories by authenticated account. Verify read and write isolation, deletion and backup handling. |

Evaluate with fictional résumés and labeled postings across several occupations and locations. Track time to first useful result, the share of the first ten results people consider relevant, false exclusions from location and pay rules, and the proportion of listings with actionable employer evidence. Measure account isolation separately from search quality.
