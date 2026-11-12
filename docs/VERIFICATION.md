# Verification record

The [approved vision](PRODUCT-VISION.md) describes the intended product. This record covers checks that were actually observed. See the [Build 9 checklist](STAGE-TWO.md) for the shipped changes and [roadmap](NEXT-STEPS.md) for open work.

## Build 9

| Target | Observed result |
| --- | --- |
| Backend | 49 Python tests passed with fictional fixtures and temporary data. |
| Browser | Both sequential browser suites passed on macOS. Hosted Linux also ran the unit and browser suites. |
| GitHub | The pull request and push workflows passed for [commit `5ad2cbd`](https://github.com/shawnd1007/Jobs-APP/commit/5ad2cbdf4b9ad6488ecb80386afb9e9f715c19a8). [Pull request run](https://github.com/shawnd1007/Jobs-APP/actions/runs/43238381405) · [Push run](https://github.com/shawnd1007/Jobs-APP/actions/runs/43238367416) |
| Xcode | An unsigned device release built on macOS. An isolated iPhone 17 simulator exercised sample browsing, tracking, a failed server change, offline reopening, and saving a follow-up after reconnecting. |
| Résumé | The simulator supplied a fictional PDF directly to the import handler. Skill selection and experience saved to the profile, relevant duties appeared in the match, and repeating the same passage preserved one copy. |

Selecting a document through the system Files picker and receiving alerts on a signed physical iPhone still need end-to-end checks. macOS Docker remains unverified. Build 9 verification used mocked paid providers. Provider cost, product effectiveness, and account isolation need their own evidence before wider access.

## Earlier observations

- Build 8 checked 29 watched employer boards on the Mac and rechecked 153 listings with zero feed errors. That run produced zero new saved-search alerts. The [source guide](EMPLOYER-BOARDS.md) explains how to inspect the live board list and outcomes.
- The November 10, 2026 source package passed 34 unit tests on Windows and Python 3.13 Alpine Docker, and passed both browser suites with Edge on Windows. Those counts describe that earlier snapshot.
