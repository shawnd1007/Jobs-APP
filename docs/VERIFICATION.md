# Verification record

The [approved vision](PRODUCT-VISION.md) describes the intended product. This record covers checks that were actually observed. See the [Build 9 checklist](STAGE-TWO.md) for the shipped changes and [roadmap](NEXT-STEPS.md) for open work.

## Personal iPhone and Azure test — November 18, 2026

A physical iPhone was signed and installed using Xcode Personal Team. After the MSAL framework runpath and browser sign-in changes, the phone signed in and connected to the Azure workspace. With Wi-Fi turned off, a fresh Connect succeeded while the phone displayed 5G. This is a personal workspace test, not proof of multi-user isolation. Free Personal Team provisioning expires and needs renewal.

Azure App Service authentication requires Microsoft sign-in and is configured with an allowed identity. The main app is reachable from public networks for mobile use; the advanced deployment endpoint has separate deny-all network restrictions. Rejection of a different signed-in identity and a backup restore remain untested. Database settings survived an earlier restart; recovery still needs verification.

A previous Azure search checked 29 configured boards and saved 35 listings; the match run stopped on unverifiable evidence. The matching correction flags such evidence for review and continues, and passed fictional local tests. Publishing this source does not by itself prove Azure deployment or a successful new matching run. The 27 comparison calls recorded in that prior run had an estimated known AI cost of roughly $0.085, not a complete search cost or bill.

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

## Search profile and shortlist

For You opens the Search Profile directly. Import a résumé or enter experience manually, review the skills, choose target roles and pay, and save to refresh the shortlist. Workspace Administration contains employer sources, matching weights, schedule, and provider settings.

Fresh installations use separate commute and remote hiring locations. Existing configurations with local areas retain their prior rules when their location and arrangement fields are blank. Existing combined location preferences also retain their behavior until the user opts into separate fields. Unknown or restricted remote eligibility goes to review. Saved searches continue to use their own criteria.

The iPhone 17 simulator in Device Hub displayed the fictional shortlist, opened the profile from For You, enabled separate location fields, and returned to an updated shortlist after saving. Backend regression cases cover Portland hybrid listings, an ambiguous city, remote hiring restrictions, and the legacy geography. The system Files picker, VoiceOver, signed-device behavior, and customer account isolation require further validation.
