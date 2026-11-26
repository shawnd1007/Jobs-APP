import SwiftUI

enum JobsTheme {
    static let accent = adaptive(light: 0x2454D6, dark: 0x9CB7FF)
    static let canvas = adaptive(light: 0xF6F8FC, dark: 0x111827)
    static let surface = adaptive(light: 0xFFFFFF, dark: 0x1C2636)
    static let border = adaptive(light: 0xDCE3ED, dark: 0x364359)

    private static func adaptive(light: UInt32, dark: UInt32) -> Color {
        Color(uiColor: UIColor { traits in
            let value = traits.userInterfaceStyle == .dark ? dark : light
            return UIColor(
                red: CGFloat((value >> 16) & 255) / 255,
                green: CGFloat((value >> 8) & 255) / 255,
                blue: CGFloat(value & 255) / 255,
                alpha: 1
            )
        })
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
                VStack(alignment: .leading, spacing: 8) {
                    Text("Find work that fits")
                        .font(.largeTitle.bold())
                        .accessibilityAddTraits(.isHeader)
                    Text("See why roles match your experience and keep track of the ones you pursue.")
                        .font(.body)
                        .foregroundStyle(.secondary)
                }
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
    private static let storageKey = "jobs.sample.progress.v1"

    private static let profileKey = "jobs.sample.profile.v1"

    private struct Profile: Codable {
        let skills: [String]
        let salaryFloor: Int
    }

    private struct Progress: Codable {
        let interest: Job.Interest?
        let tracking: TrackingDraft
    }

    static func restore() -> Dashboard {
        var snapshot = dashboard()
        score(&snapshot, skills: snapshot.preferences.preferredSkills ?? [], salaryFloor: 0)
        if let data = UserDefaults.standard.data(forKey: profileKey),
           let profile = try? JSONDecoder().decode(Profile.self, from: data) {
            score(&snapshot, skills: profile.skills, salaryFloor: profile.salaryFloor)
        }
        guard let data = UserDefaults.standard.data(forKey: storageKey),
              let progress = try? JSONDecoder().decode([Int: Progress].self, from: data)
        else { return snapshot }
        for index in snapshot.jobs.indices {
            guard let saved = progress[snapshot.jobs[index].id] else { continue }
            snapshot.jobs[index].interest = saved.interest
            snapshot.jobs[index].status = saved.tracking.status
            snapshot.jobs[index].applicationDate = saved.tracking.applicationDate
            snapshot.jobs[index].followUp = saved.tracking.followUp
            snapshot.jobs[index].notes = saved.tracking.notes
            snapshot.jobs[index].version = saved.tracking.version
        }
        return snapshot
    }

    static func save(_ jobs: [Job]) throws {
        let progress = Dictionary(uniqueKeysWithValues: jobs.map {
            ($0.id, Progress(interest: $0.interest, tracking: TrackingDraft($0)))
        })
        UserDefaults.standard.set(try JSONEncoder().encode(progress), forKey: storageKey)
    }

    static func updateProfile(_ snapshot: inout Dashboard, skills: [String], salaryFloor: Int) throws {
        let profile = Profile(skills: skills, salaryFloor: salaryFloor)
        UserDefaults.standard.set(try JSONEncoder().encode(profile), forKey: profileKey)
        score(&snapshot, skills: skills, salaryFloor: salaryFloor)
    }

    private static func score(_ snapshot: inout Dashboard, skills: [String], salaryFloor: Int) {
        let selected = Set(skills.map { $0.lowercased() })
        let examples = Dictionary(uniqueKeysWithValues: dashboard().jobs.map { ($0.id, $0.matchedSkills ?? []) })
        snapshot.preferences.preferredSkills = skills
        snapshot.preferences.salaryFloor = salaryFloor
        for index in snapshot.jobs.indices {
            let required = examples[snapshot.jobs[index].id] ?? []
            let overlap = required.filter { selected.contains($0.lowercased()) }
            snapshot.jobs[index].matchedSkills = overlap
            snapshot.jobs[index].score = required.isEmpty ? 0 : (100 * overlap.count) / required.count
            snapshot.jobs[index].explanation = "Your sample profile covers \(overlap.count) of \(required.count) skills for this role. Example skills: \(required.joined(separator: ", "))."
        }
    }

    static func reset() -> Dashboard {
        UserDefaults.standard.removeObject(forKey: storageKey)
        UserDefaults.standard.removeObject(forKey: profileKey)
        return restore()
    }

    private static func dashboard() -> Dashboard {
        Dashboard(
            jobs: [
                job(1, "Senior Billing Operations Analyst", "Alderline Health",
                    location: "Remote · United States", pay: 84_000...106_000,
                    skills: ["Billing operations", "Reconciliation", "Excel"],
                    description: "Own invoice quality and month-end billing controls. Investigate payment exceptions, reconcile transaction records, and partner with finance to improve the close."),
                job(2, "Payments Reconciliation Analyst", "Harbor Wren Payments",
                    location: "Remote · United States", pay: 78_000...99_000,
                    skills: ["Reconciliation", "Variance analysis", "Reporting"],
                    description: "Reconcile daily payment and settlement files. Resolve breaks with banking partners and report recurring exceptions to the payments team."),
                job(3, "Revenue Operations Specialist", "Larkfield Systems",
                    location: "Remote · United States", pay: 90_000...115_000,
                    skills: ["Revenue operations", "Reporting"],
                    description: "Support the quote-to-cash workflow, maintain recurring revenue reports, and investigate discrepancies between contracts, invoices, and the CRM."),
                job(4, "Revenue Cycle Coordinator", "Cedar Finch Medical",
                    location: "Remote · Hiring region unclear", pay: nil,
                    skills: ["Billing operations", "Reporting"],
                    description: "Monitor claims and follow up on payment exceptions. The sample posting leaves compensation and remote hiring states unspecified."),
                job(5, "Accounts Receivable Specialist", "Cinder Harbor Supply",
                    location: "Hybrid · Jacksonville, FL", pay: 64_000...81_000,
                    skills: ["Invoicing", "Accounts Receivable", "Reconciliation"],
                    description: "Own invoices, investigate short payments, and reconcile the receivables ledger."),
                job(6, "Sales Operations Analyst", "Kestrel Grove Software",
                    location: "Remote · United States", pay: 86_000...112_000,
                    skills: ["Salesforce", "Reporting", "Forecasting"],
                    description: "Maintain pipeline dashboards, review forecast changes, and improve CRM data quality."),
                job(7, "Data Analyst", "Copper Iris Research",
                    location: "Hybrid · Atlanta, GA", pay: 82_000...108_000,
                    skills: ["SQL", "Tableau", "Data Analysis"],
                    description: "Build SQL datasets and Tableau dashboards for an operations team."),
                job(8, "iOS Engineer", "Juniper Lantern Studio",
                    location: "Remote · United States", pay: 118_000...156_000,
                    skills: ["Swift", "SwiftUI", "iOS"],
                    description: "Ship accessible SwiftUI features and investigate performance issues in an iOS app."),
                job(9, "Implementation Specialist", "Glasswater Systems",
                    location: "Remote · United States", pay: 72_000...94_000,
                    skills: ["Client Onboarding", "Project Management", "Workflow Documentation"],
                    description: "Guide new customers through configuration, migration, training, and launch."),
                job(10, "UX Designer", "Osprey Thread Studio",
                    location: "Hybrid · Raleigh, NC", pay: 91_000...122_000,
                    skills: ["Figma", "User Research", "Accessibility"],
                    description: "Interview customers, prototype workflows, and test designs for accessibility."),
                job(11, "Laboratory Technician", "Willow Gauge Labs",
                    location: "On-site · Tampa, FL", pay: 51_000...69_000,
                    skills: ["Sample Preparation", "Microscopy", "Laboratory Safety"],
                    description: "Prepare and log samples, operate microscopes, and maintain lab safety records."),
                job(12, "Supply Chain Coordinator", "Bracken Pier Logistics",
                    location: "On-site · Savannah, GA", pay: 62_000...82_000,
                    skills: ["Inventory Management", "Logistics", "Vendor Management"],
                    description: "Coordinate supplier orders, investigate stock discrepancies, and monitor shipments.", status: "Applied"),
                job(13, "Customer Success Manager", "Amber Row Learning",
                    location: "Remote · United States", pay: 84_000...110_000,
                    skills: ["Customer Success", "Account Management", "Salesforce"],
                    description: "Help a portfolio of customers adopt the product and plan renewals.", status: "Interview Scheduled"),
                job(14, "Field Maintenance Technician", "Maple Beacon Facilities",
                    location: "On-site · Orlando, FL", pay: 58_000...78_000,
                    skills: ["HVAC", "Preventive Maintenance", "Safety Inspections"],
                    description: "Perform scheduled inspections and diagnose faults in commercial equipment."),
                job(15, "Instructional Designer", "Slate Robin Education",
                    location: "Remote · United States", pay: 73_000...97_000,
                    skills: ["Instructional Design", "Curriculum Development", "Facilitation"],
                    description: "Build training courses, test learning materials, and facilitate pilot sessions."),
                job(16, "Marketing Operations Specialist", "Westmere Orchard",
                    location: "Hybrid · Austin, TX", pay: 76_000...102_000,
                    skills: ["HubSpot", "Email Marketing", "Google Analytics"],
                    description: "Build email campaigns, maintain reporting, and improve lead routing.")
            ],
            savedSearches: nil, matchAlerts: nil, unreadMatchCount: nil,
            runs: [], statuses: ["Not Applied", "Planning to Apply", "Applied", "Interview Scheduled", "Offer Received", "Withdrawn"],
            running: false,
            preferences: Preferences(preferredSkills: ["Billing Operations", "Reconciliation", "Excel", "Reporting", "Revenue Operations"], targetLocations: [], workplaceTypes: [],
                profile: "", categories: [], salaryFloor: 0, salaryPolicy: "",
                excludedTitleTerms: [], skillGroups: [], additionalBoards: [:],
                additionalEmployerUrls: [], disabledSources: [], aiEnabled: false, aiModel: "",
                aiDailyLimit: 0, scheduleEnabled: false, scheduleHourUtc: 0),
            preferencesRevision: "", sources: [], aiConfigured: false, aiAttemptsToday: 0
        )
    }

    private static func job(_ id: Int, _ title: String, _ employer: String, location: String,
                            pay: ClosedRange<Double>?, skills: [String], description: String,
                            status: String = "Not Applied") -> Job {
        let eligible = pay != nil
        let timestamp = Date.now.addingTimeInterval(Double(-id) * 86_400).ISO8601Format()
        let gaps = eligible ? [] : ["Published pay and hiring region need review"]
        return Job(
            interest: nil, matchedSkills: skills, matchedGroups: nil, matchGaps: gaps,
            salaryMin: pay?.lowerBound, salaryCurrency: eligible ? "USD" : nil,
            salaryPeriod: eligible ? "year" : nil, salaryType: eligible ? "base" : nil, stale: false,
            id: id, title: title, employer: employer, location: location,
            locationEligibility: eligible ? "Eligible" : "Review", locationReason: gaps.first,
            area: location.components(separatedBy: " · ").first, category: "Sample roles", salaryText: nil, salaryMax: pay?.upperBound,
            availability: "Open", description: description, explanation: nil, applicationEvidence: nil,
            source: "Fictional sample listing", posted: timestamp, lastVerified: nil, created: timestamp,
            updated: timestamp, url: nil, score: 0, matchLabel: "Example match",
            queue: eligible ? "Confirmed" : "Review", reviewDecision: "Pending",
            reviewBlockers: gaps, reviewChecks: [:], reviewNote: "", reviewReviewer: "", reviewVersion: 0,
            status: status, applicationDate: status == "Not Applied" ? "" : dateString(.now.addingTimeInterval(-86_400)),
            followUp: "", notes: "", version: 0, aiAdvice: nil
        )
    }
}
