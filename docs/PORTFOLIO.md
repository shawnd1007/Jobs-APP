# Explaining this project

## The problem

Job searches produce scattered links and uncertain evidence. A personal workspace should explain what is current, why it may fit, what still needs checking and what the owner has already done.

## The implementation

Python retrieves public employer feeds, normalizes listing data and applies explicit rules. SQLite stores listings separately from human decisions and application history. The browser dashboard and native SwiftUI app use the same backend. Docker supplies a repeatable local runtime. Optional AI advice runs server-side and is cached independently.

## Decisions worth demonstrating

- Failed sources do not imply closed jobs. Successful complete feeds missing requisitions can mark closure while preserving application notes.
- Removed salary evidence does not silently remain current after refresh.
- Versioned saves prevent one device silently overwriting another's changes.
- Employer URLs rotate by last attempt rather than letting repeated failures monopolize the queue.
- AI advice is not verification or human approval. Keys stay server-side, and paid attempts are explicitly requested and bounded.

## Demonstration

Run the isolated browser tests against fictional data. Explain one adapter, trace a dashboard request, change a matching weight with a regression test, and demonstrate a conflict being rejected. Read the complete guide for six learning sessions.

## Claims and boundaries

Jobs was developed with AI assistance. The current build is a single-workspace prototype for trusted networks. The [approved product vision](PRODUCT-VISION.md) sets the goals for a paid recruiter with isolated accounts. Cite the [verification record](VERIFICATION.md) when describing a tested platform or feature.
