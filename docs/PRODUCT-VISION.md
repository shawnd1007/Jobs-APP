# Jobs: Product Vision and Goals

**Status:** Product-owner-approved goals. These describe the intended product, not a claim that every capability is implemented.  
**Approved:** November 11, 2026 (Eastern time)  
**Product owner:** Shawn Delegal

## The product

Jobs is a simple, secure, ad-free, personalized AI job recruiter. Its purpose is to save job seekers the hours they spend searching multiple sites, filtering junk, hunting for the real employer posting, tailoring applications, and maintaining spreadsheets.

A person should be able to say: “Here’s my experience, what I want, where I want to work, and what I need to earn.” The app does the legwork and presents real opportunities worth their attention.

## 1. Understand each job seeker

- Each user has their own private account and profile.
- Let them upload a résumé and add or correct information about their experience, education, skills, and goals.
- Use AI to identify both stated and transferable skills and suggest relevant roles the person might not have considered.
- Let the user review and correct AI assumptions. The résumé is the evidence, not an excuse to invent qualifications.

## 2. Understand what they actually want

- Let users define target roles, locations, remote/hybrid/on-site preferences, salary, industries, schedule, and other requirements.
- Separate non-negotiable requirements from preferences, so the app doesn’t dismiss a great opportunity over a minor preference.
- Make it easy to change goals as the search evolves. Don’t build the product around Shawn’s résumé or location.

## 3. Search broadly on their behalf

- Search across many job boards, employer career pages, and other legitimate sources. LinkedIn, Indeed, and Monster illustrate the fragmented experience we want to improve; their inclusion depends on available, permitted access.
- Automate searches and refresh results so users aren’t repeating the same work every day.
- Expand the number of sources over time, but show which sources actually work. Fifty is a long-term ambition, not a number to fake with placeholders.
- Combine duplicate listings for the same role and avoid cluttering the feed with repeated jobs.

## 4. Find the real employer posting

- Use a board listing as a lead, then locate the matching job on the employer’s own careers site or its official application platform.
- Match the company, title, location, and requisition details where available. A plausible-looking link isn’t enough.
- Take users directly to the verified employer application, not back through an endless chain of job-board links.
- If the direct posting cannot be verified, say so clearly. Don’t pretend it was found, and don’t substitute a different job.
- Identify closed, stale, or unavailable listings when possible and show when a job or link was last checked.

## 5. Present opportunities worth their time

- Give each user a personalized shortlist, not a giant unfiltered list.
- Show the employer, title, location, work arrangement, pay when disclosed, key responsibilities, requirements, and the source.
- Explain why each role matches the user’s actual background. Distinguish proven experience, reasonable AI inferences, gaps, and unknowns.
- Make fit understandable and useful. Don’t imply a score is a guaranteed chance of an interview or offer.
- Clearly say when salary, location, or another important detail is missing instead of making it up.

## 6. Help them put their best foot forward

- Show which genuine skills and experience to emphasize for a particular job.
- Suggest truthful résumé adjustments and help prepare application materials based on the role.
- Explain gaps and possible paths to address them, including relevant skills or certifications where useful.
- Let the user review and approve their materials and decide when to apply. No fabricated experience, credentials, or metrics.

## 7. Replace the application spreadsheet

- Let users save and organize jobs, record when they apply, and track progress through stages such as applied, interview, declined, and offer.
- Include notes, key dates, and follow-ups without turning basic tracking into a complicated project-management system.
- Make it easy to tell what needs attention and what has already happened.
- Preserve the user’s information and prevent duplicate or conflicting records.
- Recommended extension included in the approved vision: let users bring in applications they found elsewhere too.

## 8. Make it genuinely useful every day

- Show what’s new, what changed, and which follow-ups are due.
- Let users give feedback on matches, such as “not interested” or “wrong fit,” and use that feedback to improve future results. Be clear about how it’s used.
- Send useful alerts only when the user wants them. No spam, fake urgency, or engagement tricks.
- Make the experience fast, accessible, and understandable for people who aren’t technical. If a search or connection fails, explain what happened and how current the displayed information is.

## 9. Protect the people paying us

- Secure individual accounts and keep each person’s résumé, preferences, and application history separate.
- Be transparent about what AI does with their information. Give users control over correcting and deleting their data.
- Don’t expose private résumés, credentials, or application details. Build and test security before opening the service to the public.
- No advertisements. No selling a user’s attention as the product.

## 10. Make it worth the money

- The app should save substantial search time and surface relevant, current opportunities that are genuinely easier to pursue than on fragmented job boards.
- Roughly **$10/month** is an idea to investigate, not a committed price. Understand AI, search, hosting, and support costs, then test whether customers see enough value.
- An OpenAI-powered backend is the intended AI direction discussed by the product owner. Its operating costs and implementation must be validated.
- Be clear about what users receive and any limits. Don’t promise an interview, offer, or job.

## 11. Build a real business, not just a demo

- Shawn uses it first and helps test whether it solves a real daily problem; other job seekers remain the intended customers.
- Start with a dependable end-to-end experience and expand sources and capabilities as they can be supported reliably.
- Measure things that matter: relevance, correct employer links, duplicate and stale listings, time saved, and whether users find the product worth returning to and paying for.
- Keep the product honest about what is live, what is experimental, and what is planned.

## The development compass

Every major feature must strengthen at least one part of this journey:

**Understand the person → find and verify real jobs → explain the fit → help them apply → track the outcome.**

This keeps the project pointed at the approved vision instead of drifting into another generic job board or tracker. Tracking is a core part of the complete experience, alongside personalized discovery and direct employer applications.

Read this vision when planning new work. Inspect the current implementation separately, preserve working features, and distinguish completed capabilities from goals. Do not rewrite the product purpose to match only what happens to be easiest to build.
