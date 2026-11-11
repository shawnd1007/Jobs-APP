import SwiftUI

enum JobsTheme {
    static let accent = Color(uiColor: UIColor { traits in
        traits.userInterfaceStyle == .dark
            ? UIColor(red: 0.49, green: 0.87, blue: 0.75, alpha: 1)
            : UIColor(red: 0.02, green: 0.35, blue: 0.31, alpha: 1)
    })
    static let canvas = Color(uiColor: UIColor { traits in
        traits.userInterfaceStyle == .dark
            ? UIColor(red: 0.07, green: 0.11, blue: 0.11, alpha: 1)
            : UIColor(red: 0.95, green: 0.96, blue: 0.94, alpha: 1)
    })
    static let surface = Color(uiColor: .secondarySystemGroupedBackground)
    static let pine = Color(red: 0.04, green: 0.19, blue: 0.18)
    static let mint = Color(red: 0.75, green: 0.95, blue: 0.83)
}

struct EditorialPanel: View {
    let label: String
    let title: String
    let detail: String
    var compact = false
    @ScaledMetric(relativeTo: .largeTitle) private var titleSize = 35

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 8 : 13) {
            Label(label, systemImage: "sparkles")
                .font(.caption.weight(.semibold))
                .foregroundStyle(JobsTheme.mint)
            Text(title)
                .font(.system(size: compact ? titleSize * 0.9 : titleSize, weight: .semibold, design: .serif))
                .foregroundStyle(.white)
                .accessibilityAddTraits(.isHeader)
            Text(detail)
                .font(.subheadline)
                .foregroundStyle(.white.opacity(0.84))
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(compact ? 19 : 24)
        .background(alignment: .trailing) {
            ZStack(alignment: .topTrailing) {
                LinearGradient(colors: [JobsTheme.pine, Color(red: 0.08, green: 0.32, blue: 0.27)],
                               startPoint: .topLeading, endPoint: .bottomTrailing)
                ForEach([112.0, 155, 198], id: \.self) { size in
                    RoundedRectangle(cornerRadius: size / 3)
                        .strokeBorder(JobsTheme.mint.opacity(0.19), lineWidth: 1)
                        .frame(width: size, height: size)
                        .rotationEffect(.degrees(35))
                        .offset(x: size / 3, y: -size / 2.5)
                }
            }
            .accessibilityHidden(true)
        }
        .clipShape(.rect(cornerRadius: 26))
    }
}

struct WorkspaceWelcome: View {
    let hasAddress: Bool
    let loading: Bool
    let error: String?
    let openSample: () -> Void
    let connect: () -> Void
    let retry: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                EditorialPanel(label: "Jobs", title: "Find work that fits.",
                               detail: "Explore roles, see why they match, and keep every application in one place.")
                VStack(alignment: .leading, spacing: 16) {
                    Button(action: openSample) {
                        Label("Explore sample jobs", systemImage: "arrow.right")
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 5)
                    }
                    .buttonStyle(.borderedProminent)
                    .buttonBorderShape(.roundedRectangle(radius: 14))
                    Text("Try fictional listings and application tracking right on this iPhone.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Divider()
                    Button("Connect to your Mac", systemImage: "desktopcomputer", action: connect)
                        .font(.body.weight(.semibold))
                    if loading {
                        ProgressView("Connecting…")
                    } else if hasAddress, let error {
                        Label("Your workspace is unavailable", systemImage: "wifi.exclamationmark")
                            .font(.subheadline.weight(.semibold))
                        Text(error).font(.footnote).foregroundStyle(.secondary)
                        Button("Try Again", action: retry)
                    }
                }
                .padding(20)
                .background(JobsTheme.surface, in: .rect(cornerRadius: 22))
            }
            .padding(20)
            .frame(maxWidth: 580)
            .frame(maxWidth: .infinity)
        }
        .background(JobsTheme.canvas.ignoresSafeArea())
        .navigationTitle("Jobs")
        .navigationBarTitleDisplayMode(.inline)
    }
}

enum SampleWorkspace {
    static func dashboard() -> Dashboard {
        Dashboard(
            jobs: [
                job(1, "Senior Billing Operations Analyst", "Alderline Health",
                    location: "Remote · United States", pay: 84_000...106_000, score: 94,
                    skills: ["Billing operations", "Reconciliation", "Excel"],
                    description: "Own invoice quality and month-end billing controls. Investigate payment exceptions, reconcile transaction records, and partner with finance to improve the close."),
                job(2, "Payments Reconciliation Analyst", "Harbor Wren Payments",
                    location: "Remote · United States", pay: 78_000...99_000, score: 89,
                    skills: ["Reconciliation", "Variance analysis", "Reporting"],
                    description: "Reconcile daily payment and settlement files. Resolve breaks with banking partners and report recurring exceptions to the payments team."),
                job(3, "Revenue Operations Specialist", "Larkfield Systems",
                    location: "Remote · United States", pay: 90_000...115_000, score: 82,
                    skills: ["Revenue operations", "Reporting"],
                    description: "Support the quote-to-cash workflow, maintain recurring revenue reports, and investigate discrepancies between contracts, invoices, and the CRM."),
                job(4, "Revenue Cycle Coordinator", "Cedar Finch Medical",
                    location: "Remote · Hiring region unclear", pay: nil, score: 76,
                    skills: ["Billing operations", "Reporting"],
                    description: "Monitor claims and follow up on payment exceptions. The sample posting leaves compensation and remote hiring states unspecified.")
            ],
            savedSearches: nil, matchAlerts: nil, unreadMatchCount: nil,
            runs: [], statuses: ["Not Applied", "Planning to Apply", "Applied", "Interview Scheduled", "Offer Received", "Withdrawn"],
            running: false,
            preferences: Preferences(preferredSkills: [], targetLocations: [], workplaceTypes: [],
                profile: "", categories: [], salaryFloor: 0, salaryPolicy: "",
                excludedTitleTerms: [], skillGroups: [], additionalBoards: [:],
                additionalEmployerUrls: [], disabledSources: [], aiEnabled: false, aiModel: "",
                aiDailyLimit: 0, scheduleEnabled: false, scheduleHourUtc: 0),
            preferencesRevision: "", sources: [], aiConfigured: false, aiAttemptsToday: 0
        )
    }

    private static func job(_ id: Int, _ title: String, _ employer: String, location: String,
                            pay: ClosedRange<Double>?, score: Int, skills: [String], description: String) -> Job {
        let eligible = pay != nil
        let timestamp = Date.now.addingTimeInterval(Double(-id) * 86_400).ISO8601Format()
        let gaps = eligible ? [] : ["Published pay and hiring region need review"]
        return Job(
            interest: nil, matchedSkills: skills, matchedGroups: nil, matchGaps: gaps,
            salaryMin: pay?.lowerBound, salaryCurrency: eligible ? "USD" : nil,
            salaryPeriod: eligible ? "year" : nil, salaryType: eligible ? "base" : nil, stale: false,
            id: id, title: title, employer: employer, location: location,
            locationEligibility: eligible ? "Eligible" : "Review", locationReason: gaps.first,
            area: "Remote", category: "Finance Operations", salaryText: nil, salaryMax: pay?.upperBound,
            availability: "Open", description: description, explanation: nil, applicationEvidence: nil,
            source: "Fictional sample listing", posted: timestamp, lastVerified: nil, created: timestamp,
            updated: timestamp, url: nil, score: score, matchLabel: "Example match",
            queue: eligible ? "Confirmed" : "Review", reviewDecision: "Pending",
            reviewBlockers: gaps, reviewChecks: [:], reviewNote: "", reviewReviewer: "", reviewVersion: 0,
            status: "Not Applied", applicationDate: "", followUp: "", notes: "", version: 0, aiAdvice: nil
        )
    }
}
