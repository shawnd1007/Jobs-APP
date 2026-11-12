# Master employer board list

The live workspace is the source of truth for enabled feeds, last check and errors. In the browser, use **Employer Boards** for health and pause controls and **Preferences** to add slugs. On iPhone, open **Settings → Employer Boards** or edit the **Search Profile**. The app also revisits sources associated with retained listings.

This reference lists 26 employer boards configured during development. The Build 8 live check reached 29 watched boards, including sources discovered separately. A clean checkout starts with an empty board list. See the [verification record](VERIFICATION.md) for the observed run.

| Platform | Employer | Board slug |
| --- | --- | --- |
| Ashby | Amplify | `amplify` |
| Ashby | TRM Labs | `trm-labs` |
| Ashby | Instructure | `instructure` |
| Ashby | Intellistack | `intellistack` |
| Ashby | Viz.ai | `viz.ai` |
| Ashby | Passport | `passport` |
| Ashby | Transfr | `transfr` |
| Ashby | Revecore | `revecore` |
| Ashby | Abby Care | `abby-care` |
| Ashby | Expressable | `expressable` |
| Greenhouse | First Due | `localitymediallcdbafirstdue` |
| Greenhouse | Twilio | `twilio` |
| Greenhouse | AssetWatch | `assetwatch` |
| Greenhouse | Defense Unicorns | `defenseunicorns` |
| Greenhouse | BetterHelp | `betterhelpcom` |
| Greenhouse | Karbon | `karbon` |
| Greenhouse | Canonical | `canonical` |
| Lever | Sonar | `sonarsource` |
| Lever | PointClickCare | `pointclickcare` |
| Lever | Veeva | `veeva` |
| SmartRecruiters | ServiceNow | `servicenow` |
| SmartRecruiters | Experian | `experian` |
| SmartRecruiters | Eurofins | `eurofins` |
| SmartRecruiters | Western Digital | `westerndigital` |
| SmartRecruiters | SIXT | `sixt` |
| SmartRecruiters | Sutherland | `sutherland` |

Personio can be added by entering an employer’s career-site slug after confirming its XML feed is enabled. For adapter validation, the public `and-e` feed returned 17 listings and one tested exact posting page opened. The `personio` feed returned two listings, but the exact page tested returned 404 and was flagged for verification. These checks did not add either board to the configured list above.

Recruitee can be added using a hosted career-site slug. A public check of the [LLEVERAGE XML feed](https://lleverage.recruitee.com/api/feeds/offers.xml) returned six postings. Jobs checked the exact [Forward Deployed AI Engineer](https://lleverage.recruitee.com/o/forward-deployed-ai-engineer-1) and [(Senior) Account Executive](https://lleverage.recruitee.com/o/senior-account-executive) pages and found application form evidence on both. This was a coverage check. The board was not added to the owner’s preferences.

Board coverage can include related finance and operations roles. Saved-search alerts apply each search’s title, skill, location, workplace and published salary criteria.

For provider support, pagination and closure behavior, read [how discovery works](COMPLETE-GUIDE.md#6-how-employer-discovery-works). Source coverage expands as employer feeds can be checked reliably. [Product vision](PRODUCT-VISION.md)
