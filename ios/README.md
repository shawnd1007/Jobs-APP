# Jobs for iPhone

The iPhone app is the Jobs workspace. The Mac runs the Python service and keeps the shared SQLite database, so you can do the day-to-day workflow from Xcode’s iPhone simulator or from an iPhone on your private network.

## Try it without a server

Open Jobs and tap **Explore sample jobs** on the welcome screen or under **Settings → Offline Demo**. Browse 16 fictional roles spanning finance, software, healthcare, education, operations, and field work. In **Settings → Edit Search Profile**, choose skills from the searchable catalog and pick a pay target to update **For You**. The sample score is the share of each role’s example skills you selected.

Try Save, Pass and Undo, or open **My Jobs** to explore sample applications and change a stage. Sample profiles and application changes stay on this iPhone between launches. Use **Settings → Reset Sample Progress** to restore the starting examples.

Choose **Connect to your Mac** to use the real workspace. Employer searches, résumé-based matching, saved searches and match alerts use that connection.

## Start on your Mac

1. If the backend is already running at `http://localhost:8084`, go to step 3.
2. Open Terminal in the Jobs App folder. Run `python3 setup_project.py` once to create local settings and an empty seed, then run `JOBS_BIND_HOST=127.0.0.1 python3 app.py`. Leave that Terminal open. The root README also describes running the backend with Docker.
3. Open **Shawn's iPhone Job App.xcodeproj** in Xcode. Select the **JobsApp** scheme and an iPhone simulator, then press **⌘R**.
4. Tap **Connect to your Mac**, enter `http://localhost:8084`, and tap **Connect**. The app checks the new address before switching. Change it later under **Settings → Server Settings**.

## Find and track jobs

- **For You** ranks open listings by role fit and then by match score. Top Matches requires eligible location and usable annual USD base pay. Needs Review contains other open candidates. Use **Save**, **Pass**, and **Undo** directly from a card.
- **Browse** opens the full retained job list, including earlier runs. Search by combining terms across employer, title, location and skills. Use work-setting and open-listing filters directly in Browse. Swipe a row to save it, or open the listing to see how the score breaks down and share the employer link.
- **My Jobs** opens to Saved. The stage picker shows how many roles are in Saved, Applied, Interviews, Offers and Archived. **Follow-ups** separates due and overdue items from upcoming dates. Swipe a job to open its tracking form and change the stage, notes or follow-up date.
- **Settings → Edit Search Profile** contains résumé import, target roles, skills, location and pay. Open a saved search and choose **Preview Profile Changes** to review the proposed values. **Use in Draft** fills the editor for that search, and **Save** applies the changes.
- **Settings → Employer Boards** shows the employer sources and their health.


1. Open **Settings → Edit Search Profile**. Add employer board slugs, review your target roles and salary policy, and save. A board URL such as `https://job-boards.greenhouse.io/example` has the slug `example`. For another employer site, enter the URL of an individual posting.
2. Open **Alerts** and tap **Run Employer Search**. Search history shows the run status, counts, source failures and links when available. **Settings → Employer Boards** shows each employer source’s last check and lets you pause or resume it.
3. In **Browse**, choose a listing view such as **All Listings**. Use search, filters or a quick view to narrow the list. Tap a job to inspect the match, source and posting.
4. Open **Review and Approval** to record your decision. Check the employer listing, confirm location and salary, verify the application is open, and check your history before approving. A job may require a review note or have an approval blocker.
5. Apply on the employer’s site. In **Application Tracking**, set the status, application date, follow-up date and notes. If another device updates a record while you edit, the app keeps your draft and offers to reload the server values.

Daily scheduling is optional and runs on the Mac while the backend is running. Schedule hours are in UTC.

### When the Mac is offline

After the first successful sync, the app can reopen your last connected workspace and show its saved listings, matches and tracking details. The offline banner shows the last sync time. An open edit form keeps your draft when a save fails. Reconnect and retry from the form. The Mac remains the source of truth for saved changes. **Settings → Keep a Copy for Offline Reading** controls the protected copy on the iPhone and removes it when turned off.

## Connect from an iPhone

For physical iPhone testing, select your development team under **Signing & Capabilities** and run the app on the phone from Xcode. Put the Mac and iPhone on the same trusted network. For native Python, stop the loopback server first and restart with `JOBS_BIND_HOST` set to the Mac’s private LAN IP. For Docker, change the host IP in the Compose port mapping from `127.0.0.1` to that LAN IP and recreate the service. Allow local network access if iOS asks. Enter the Mac’s local hostname, for example `http://your-mac.local:8084`. macOS shows the local hostname under **System Settings → General → Sharing**. The backend has no sign-in. Keep the port off public networks and avoid router port forwarding.

## Search and AI

The backend checks Greenhouse, Ashby, Lever and SmartRecruiters feeds. It can also extract structured job data from individual employer pages. Some pages need manual review. Job details show evidence from posting duties when they match skills described in the search profile.

To request AI career advice, put your key in `secrets/openai.key` on the Mac, enable AI in **Preferences**, and request advice from a job’s details. The backend sends your profile and the posting to OpenAI when you confirm a request. The daily limit counts attempts. Saved advice can be viewed in the app alongside the employer evidence and your decision.

## Where to edit in Xcode

- `JobsApp.swift` starts the app, holds shared workspace state and shows the tab bar and connection settings.
- `JobsViews.swift` contains the job list, filters, details, review and tracking forms.
- `WorkspaceScreens.swift` contains Alerts, Employer Boards and Settings.
- `ProductDesign.swift` contains the theme, welcome screen and fictional sample workspace.
- `DashboardAPI.swift` defines the data exchanged with the Mac and sends requests.
- `FormSupport.swift` contains the shared save form, conflict handling and date fields.
- `Info.plist` declares local-network access.

## Personalize matching

In **Settings → Edit Search Profile**, import a text-based PDF or UTF-8 text résumé from Files. The app keeps a removable preview on this device and suggests skills from the catalog. In **Review Résumé**, select the skills you want to use and optionally add a passage describing your experience. Tap **Use in Profile**, review the draft, and tap **Save** to update matching on the Mac. **Choose skills** lets you search the catalog and add custom skills. The imported file and its preview stay on the iPhone.

Enter city or region phrases and choose Remote, Hybrid, or On-site. For example, use `Austin, TX` to match that published office location, or `United States` with Remote for US-remote listings. Ambiguous remote hiring restrictions require review. Pick a salary preset or enter a custom annual USD base-pay target. Choose whether the published range only needs to reach your target or whether its minimum must meet it. Existing workspaces keep their original geography rules until you set locations or work arrangements.

See the [job board research](../docs/PERSONALIZED-JOB-BOARD.md) for the comparison and roadmap.

## Saved searches and match alerts

Open **Alerts → Saved Searches → New Saved Search**. Give the search a name, add skills and locations, choose work settings, and enter a minimum and optional maximum annual USD base salary. A listing must match at least one skill and one location, respect the selected work settings, and have published pay that overlaps the saved range. Unknown pay and uncertain remote eligibility stay out of alerts.

Use **Run Employer Search** to check configured sources now, or enable **Daily Employer Search** in Preferences to check while the Mac service runs. A new listing can match several searches. Each search receives one alert per new listing. Pausing a saved search stops future alerts for it. Editing and resuming apply to future discoveries.

Open **Alerts → Match Alerts** to view the latest 200 matches and mark them read. You can enable iPhone notifications there. The Mac records matches during a search even when the app is closed. The app displays a local notification when it next connects and sees unread matches. Delivery while the app is closed would require push or another delivery channel.

### macOS certificate trust

If the native Python service reports `CERTIFICATE_VERIFY_FAILED` for public employer feeds, check `python3 -c 'import ssl; print(ssl.get_default_verify_paths())'`. When the Python installation has no default CA bundle and `/etc/ssl/cert.pem` is available, start the local service with `SSL_CERT_FILE=/etc/ssl/cert.pem JOBS_BIND_HOST=127.0.0.1 python3 app.py`. The Mac's local launch job uses this bundle with TLS verification enabled.
