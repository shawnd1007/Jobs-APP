# Explaining this project

## The problem

Job searches produce scattered links and uncertain evidence. A personal workspace should explain what is current, why it may fit, what still needs checking and what the owner has already done.

## The implementation

Python retrieves public employer feeds, normalizes listing data and applies explicit rules. SQLite stores listings separately from human decisions and application history. HTML/CSS/JavaScript provide the browser workflow. Docker supplies a repeatable local runtime. Optional AI advice runs server-side and is cached independently.

## Decisions worth demonstrating

- Failed sources do not imply closed jobs. Successful complete feeds missing requisitions can mark closure while preserving application notes.
- Removed salary evidence does not silently remain current after refresh.
- Versioned saves prevent one device silently overwriting another's changes.
- Employer URLs rotate by last attempt rather than letting repeated failures monopolize the queue.
- AI advice is not verification or human approval. Keys stay server-side, and paid attempts are explicitly requested and bounded.

## Demonstration

Run the isolated browser tests against fictional data. Explain one adapter, trace a dashboard request, change a matching weight with a regression test, and demonstrate a conflict being rejected. Read the complete guide for six learning sessions.

## Claims and boundaries

This was developed with AI assistance. Its value is demonstrated through understanding, testing, modification and troubleshooting. It is a single-workspace private-network prototype, not a public multi-tenant service, universal crawler or native iOS application. Paid AI and macOS/Xcode execution require their own validation. The provided workflow has not yet run on a published GitHub repository.
