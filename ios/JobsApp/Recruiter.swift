import SwiftUI
import UniformTypeIdentifiers
import MapKit
import QuickLook

struct RecruiterState: Decodable {
    struct Status: Decodable {
        let version: Int
        let stage: String
        let progress: Progress?
        let stopRequested: Bool?
    }

    struct Progress: Decodable, Equatable {
        let stage: String
        let completed, total, issues: Int?
        let source, reason: String?

        var countLabel: String? {
            guard let completed else { return nil }
            if let total, total > 0 { return "\(completed) of \(total) complete" }
            if total == nil { return "\(completed) saved" }
            return nil
        }
    }

    struct Evidence: Decodable { let label, evidence, kind: String }
    struct Role: Decodable { let title, reason, evidence: String }
    struct Strategy: Decodable {
        let summary: String
        let skills: [Evidence]
        let roles, adjacentRoles, cautions: [Role]
        let omittedUnverified: Int?
    }
    struct Match: Decodable, Identifiable {
        let jobId: Int?
        let openingId, postingUrl, workArrangement, discoveredAt: String?
        let title, employer, location, salary, group, reason, resumeEvidence, jobEvidence: String
        let gaps, emphasis, checks: [String]
        let confirmationReasons: [RecruiterConfirmationReason]?
        let marketPayAvailable, marketPayTargetMatch: Bool?
        let publishedPayTargetMatch, publishedPayCeilingMatch: Bool?

        var id: String {
            if let openingId { return "opening:\(openingId)" }
            if let jobId { return "job:\(jobId)" }
            return "unavailable:\(employer):\(title):\(location)"
        }

        fileprivate var opening: RecruiterOpening? {
            guard let openingId, openingId.utf8.count == 64, openingId.utf8.allSatisfy({
                (48...57).contains($0) || (97...102).contains($0)
            }) else { return nil }
            return RecruiterOpening(id: openingId, title: title, employer: employer, location: location,
                                    workArrangement: workArrangement ?? "", salary: salary,
                                    postingUrl: postingUrl ?? "", discoveredAt: discoveredAt ?? "")
        }

        fileprivate var payTarget: RecruiterMarketPayTarget? {
            if let jobId { return .job(jobId) }
            return opening.map { .opening($0.id) }
        }

        fileprivate var resultGroup: RecruiterResultGroup { RecruiterResultGroup(rawValue: group) ?? .avoid }
        var label: String { resultGroup.matchLabel }
    }
    let version: Int
    let stage: String
    let strategy: Strategy?
    let preferences: RecruiterPreferences?
    let matches: [Match]
    let error: String
    let coverage: String?
    let deferred: Int?
    let updated: String?
    var progress: Progress?
    var stopRequested: Bool?
    var busy: Bool { ["analyzing", "discovering", "matching"].contains(stage) }
}

fileprivate enum RecruiterResultGroup: String, CaseIterable {
    case close, adjacent, review, avoid

    var matchLabel: String {
        switch self {
        case .close: "Close match"
        case .adjacent: "Worth considering"
        case .review: "Needs confirmation"
        case .avoid: "Not recommended"
        }
    }

    var title: String { self == .close ? "Close matches" : matchLabel }

    var guidance: String {
        switch self {
        case .close: "Start with roles that closely match your experience."
        case .adjacent: "Compare the duties with the experience you can bring to a related role."
        case .review: "Each opening shows what Jobs couldn’t confirm and what to check."
        case .avoid: "Review the reasons these roles were screened out."
        }
    }

    var emptyTitle: String {
        switch self {
        case .close: "No close matches in this search"
        case .adjacent: "No related roles in this search"
        case .review: "No openings need confirmation"
        case .avoid: "No screened-out openings"
        }
    }
}

struct RecruiterPreferences: Codable {
    var salary = 70000
    var salaryCeiling: Int?
    var currency = "USD"
    var period = "year"
    var flexible = false
    var commute = ""
    var remoteRegion = ""
    var modes = ["remote"]
    var levels: [String]?

    var validPayRange: Bool { salaryCeiling.map { $0 >= salary } ?? true }

    mutating func setPayPeriod(_ period: String) {
        guard self.period != period else { return }
        func converted(_ amount: Int) -> Int {
            let value = period == "hour" ? Double(amount) / 2080 : Double(amount) * 2080
            return min(1_000_000, max(0, Int(value.rounded())))
        }
        salary = converted(salary)
        salaryCeiling = salaryCeiling.map(converted)
        self.period = period
    }
}

private enum RecruiterPositionLevel: String, CaseIterable {
    case entry, mid, senior, management, executive

    var title: String {
        switch self {
        case .entry: "Entry level"
        case .mid: "Mid level"
        case .senior: "Senior"
        case .management: "Management"
        case .executive: "Executive"
        }
    }
}

struct ForYou: View {
    let workspace: Workspace
    let openBrowse: () -> Void
    let openSettings: () -> Void
    let openSearch: () -> Void
    var body: some View {
        if workspace.isSample {
            LegacyForYou(workspace: workspace, openBrowse: openBrowse, openSettings: openSettings, openSearch: openSearch)
        } else {
            RecruiterHome(workspace: workspace)
        }
    }
}

struct RecruiterHome: View {
    private struct PollSchedule: Equatable {
        let address: String
        let searchActive: Bool
    }

    let workspace: Workspace
    @State private var state: RecruiterState?
    @State private var preferences = RecruiterPreferences()
    @State private var importing = false
    @State private var reading = false
    @State private var submissionTitle: String?
    @State private var error: String?
    @State private var selectedGroup: RecruiterResultGroup?
    @State private var editingPreferences = false
    @State private var importedText: String?
    @State private var importedFileName: String?
    @State private var importedFileData: Data?
    @State private var lastVersion = -1
    @State private var showingStrategy = false
    @State private var showingResume = false
    @State private var showingActivity = false
    @State private var researchingPay: RecruiterState.Match?
    @State private var refreshingMarketPay = false
    @State private var latestLoad = UUID()
    @State private var lastStatusCheck: Date?
    @State private var lastRecruiterLoad: Date?
    @State private var statusUnavailable = false
    @State private var stoppingSearch = false

    private var busy: Bool { reading || submissionTitle != nil || state?.busy == true }
    private var stageTitle: String {
        if state?.busy == true, let progress = state?.progress { return progress.stage }
        if let submissionTitle { return submissionTitle }
        switch state?.stage {
        case "analyzing": return "Understanding your experience"
        case "discovering": return "Finding and checking openings"
        case "matching": return "Comparing jobs with your experience"
        default: return "Reading your résumé"
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                VStack(alignment: .leading, spacing: 6) {
                    Label("Your personal recruiter", systemImage: "sparkles")
                        .font(.caption.weight(.semibold)).foregroundStyle(JobsTheme.accent)
                    Text("Version 2 preview").font(.caption2).foregroundStyle(.secondary)
                }
                if !workspace.address.isEmpty {
                    NavigationLink {
                        RecruiterOpeningsView(address: workspace.address)
                    } label: {
                        Label("Pulled Openings", systemImage: "tray.full")
                    }
                    .buttonStyle(.bordered)
                }
                if state == nil {
                    if error == nil { ProgressView("Opening your recruiter…") }
                } else if state?.strategy == nil && !busy {
                    welcome
                }
                if busy { progress }
                if let issue = error ?? (state?.error.isEmpty == false ? state?.error : nil) {
                    VStack(alignment: .leading, spacing: 12) {
                        Label("Needs attention", systemImage: "exclamationmark.circle").font(.headline)
                        Text(issue).font(.subheadline)
                        if !busy {
                            Button(state == nil ? "Reconnect" : "Retry") {
                                Task {
                                    if state == nil { await reload() }
                                    else if state?.strategy == nil { await analyze(importedText, fileName: importedFileName, fileData: importedFileData) }
                                    else { await search() }
                                }
                            }.buttonStyle(.bordered)
                        }
                    }.jobCardSurface()
                }
                if state != nil {
                    Button("Search activity", systemImage: "clock.arrow.circlepath") { showingActivity = true }
                        .buttonStyle(.bordered)
                }
                if let strategy = state?.strategy {
                    if state?.stage == "ready" || editingPreferences {
                        strategyCard(strategy)
                    } else {
                        DisclosureGroup("Your career strategy") { strategyCard(strategy) }
                            .font(.headline).padding(.vertical, 8)
                    }
                    if !busy && (state?.stage == "ready" || editingPreferences) {
                        preferenceForm
                    }
                    if state?.stage == "complete" || state?.stage == "failed" || state?.stage == "matching" || state?.stage == "stopped" {
                        results
                    }
                }
            }
            .padding(20)
            .frame(maxWidth: 700)
            .frame(maxWidth: .infinity)
        }
        .safeAreaInset(edge: .bottom) {
            if !busy && state?.strategy != nil && (state?.stage == "ready" || editingPreferences) {
                Button { Task { await search() } } label: {
                    Label("Find my matches", systemImage: "sparkle.magnifyingglass")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent).controlSize(.large)
                .disabled(!preferences.validPayRange)
                .padding(.horizontal, 20).padding(.vertical, 10)
                .background(.regularMaterial)
            }
        }
        .background(JobsTheme.canvas.ignoresSafeArea())
        .navigationTitle("For You")
        .navigationBarTitleDisplayMode(.inline)
        .navigationDestination(for: Int.self) { id in
            let match = state?.matches.first(where: { $0.jobId == id })
            JobDetail(workspace: workspace, jobID: id, recruiterMatch: match,
                      onMarketPayUpdated: { await refreshAfterPayResearch(for: match?.id) })
        }
        .toolbar {
            if state?.strategy != nil {
                Menu {
                    Button("Your search preferences") { editingPreferences = true }
                    Button("View master résumé") { showingResume = true }
                    Button("Replace résumé") { openFilePicker() }
                    Button("Refresh matches") { Task { await search() } }
                } label: { Image(systemName: "slider.horizontal.3") }
                .accessibilityLabel("Recruiter options")
                .disabled(busy)
            }
        }
        .fileImporter(isPresented: $importing, allowedContentTypes: [.pdf, .plainText]) { result in
            workspace.choosingRecruiterFile = false
            switch result {
            case .success(let url):
                Task {
                    reading = true
                    defer { reading = false }
                    do {
                        let (preview, data) = try await Task.detached {
                            let preview = try ResumePreview.read(url)
                            let accessed = url.startAccessingSecurityScopedResource()
                            defer { if accessed { url.stopAccessingSecurityScopedResource() } }
                            return (preview, try Data(contentsOf: url))
                        }.value
                        importedText = preview.text
                        importedFileName = preview.name
                        importedFileData = data
                        await analyze(preview.text, fileName: preview.name, fileData: data)
                    } catch { self.error = error.localizedDescription }
                }
            case .failure(let issue):
                if (issue as? CocoaError)?.code != .userCancelled { error = issue.localizedDescription }
            }
        }
        .onChange(of: importing) { _, presented in
            if !presented { workspace.choosingRecruiterFile = false }
        }
        .onChange(of: workspace.address) { _, _ in selectedGroup = nil }
        .onDisappear { workspace.choosingRecruiterFile = false }
        .sheet(isPresented: $showingResume) { MasterResumeView(workspace: workspace) }
        .sheet(isPresented: $showingActivity) { RecruiterActivityView(address: workspace.address) }
        .sheet(item: $researchingPay) { match in
            if let target = match.payTarget {
                MarketPayView(target: target, address: workspace.address,
                              onResearchUpdated: { await refreshAfterPayResearch(for: match.id) })
            }
        }
        .task(id: PollSchedule(address: workspace.address, searchActive: state?.busy == true)) {
            while !Task.isCancelled {
                if !workspace.choosingRecruiterFile { await reload(polling: true) }
                do { try await Task.sleep(for: .seconds(state?.busy == true ? 3 : 10)) }
                catch { return }
            }
        }
        .refreshable { await reload(); await workspace.refresh() }
    }

    private var welcome: some View {
        VStack(alignment: .leading, spacing: 22) {
            Image(systemName: "doc.text.magnifyingglass").font(.system(size: 44)).foregroundStyle(JobsTheme.accent)
            Text("Your experience.\nYour next chapter.").font(.largeTitle.bold())
            Text("Bring your résumé. We’ll uncover your strengths, suggest roles and find openings worth your time.")
                .font(.title3).foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 16) {
                Label("Upload your résumé", systemImage: "1.circle")
                Label("Tell us your pay and location", systemImage: "2.circle")
                Label("Get matches with clear reasons", systemImage: "3.circle")
            }.font(.subheadline.weight(.medium))
            Button { openFilePicker() } label: {
                Label("Upload résumé", systemImage: "arrow.up.doc").frame(maxWidth: .infinity)
            }.buttonStyle(.borderedProminent).controlSize(.large)
            Text("PDF or text, up to 10 MB. Jobs sends your résumé text to its AI service to build your profile. You can review the evidence and replace your résumé.")
                .font(.footnote).foregroundStyle(.secondary)
        }.jobCardSurface()
    }

    private var progress: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let current = state?.progress, state?.busy == true,
               let completed = current.completed, let total = current.total, total > 0 {
                ProgressView(value: Double(min(completed, total)), total: Double(total)) {
                    Text(current.stage).font(.headline)
                } currentValueLabel: {
                    Text(current.countLabel ?? "")
                }
            } else {
                ProgressView(stageTitle).font(.headline)
                if state?.busy == true, let count = state?.progress?.countLabel {
                    Text(count).font(.subheadline)
                }
            }
            if state?.busy == true, let source = state?.progress?.source {
                Text(source).font(.subheadline).foregroundStyle(.secondary)
            }
            if statusUnavailable {
                Label("Can’t reach Jobs for an update. The search may still be running.",
                      systemImage: "wifi.exclamationmark")
                    .font(.footnote)
            }
            if state?.busy == true, let lastStatusCheck {
                Text("Status checked at \(lastStatusCheck.formatted(date: .omitted, time: .standard))")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Text("You can leave this screen and come back to your results.")
                .font(.subheadline).foregroundStyle(.secondary)
            if ["discovering", "matching"].contains(state?.stage ?? "") {
                Button(state?.stopRequested == true || stoppingSearch ? "Stopping search…" : "Stop search") {
                    Task { await stopSearch() }
                }
                .buttonStyle(.bordered)
                .disabled(stoppingSearch || state?.stopRequested == true)
                .accessibilityIdentifier("stopRecruiterSearch")
            }
        }.jobCardSurface()
    }

    private func strategyCard(_ strategy: RecruiterState.Strategy) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Your search, built around you").font(.title2.bold())
            Text(strategy.summary).font(.subheadline)
            if let omitted = strategy.omittedUnverified, omitted > 0 {
                Text("Jobs left out \(omitted) suggestions because their supporting quotes couldn't be verified. Your résumé remains available to review or replace.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Text("ROLES TO EXPLORE").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            ForEach(strategy.roles, id: \.title) { role in
                Label(role.title, systemImage: "arrow.up.right").font(.headline)
            }
            DisclosureGroup("Your strengths & career direction", isExpanded: $showingStrategy) {
                VStack(alignment: .leading, spacing: 16) {
                    ForEach(strategy.skills, id: \.label) { skill in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(skill.label + (skill.kind == "transferable" ? " · Transferable" : "")).font(.subheadline.bold())
                            Text("“\(skill.evidence)”").font(.footnote).foregroundStyle(.secondary)
                        }
                    }
                    roleSection("Adjacent opportunities", strategy.adjacentRoles)
                    roleSection("Approach with caution", strategy.cautions)
                    Text("These are suggestions, not automatic exclusions. Replace your résumé to correct the evidence used for your search.")
                        .font(.footnote).foregroundStyle(.secondary)
                }.padding(.top, 12)
            }
        }.jobCardSurface()
    }

    private func roleSection(_ title: String, _ roles: [RecruiterState.Role]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if !roles.isEmpty { Text(title).font(.headline) }
            ForEach(roles, id: \.title) { role in
                Text(role.title).font(.subheadline.bold())
                Text(role.reason).font(.subheadline).foregroundStyle(.secondary)
            }
        }
    }

    private var preferenceForm: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("What works for you?").font(.title2.bold())
            positionLevels
            Divider()
            Text("Pay target").font(.headline)
            HStack {
                Picker("Currency", selection: $preferences.currency) {
                    ForEach(["USD", "CAD", "GBP", "EUR"], id: \.self) { Text($0) }
                }
                Picker("Pay period", selection: Binding(get: { preferences.period }, set: { new in
                    preferences.setPayPeriod(new)
                })) {
                    Text("Per year").tag("year")
                    Text("Per hour").tag("hour")
                }
            }
            Picker("Minimum base pay", selection: $preferences.salary) {
                ForEach(salaryOptions, id: \.self) { amount in
                    Text(payOption(amount)).tag(amount)
                }
            }.pickerStyle(.menu)
            Picker("Maximum base pay", selection: $preferences.salaryCeiling) {
                Text("No maximum").tag(nil as Int?)
                ForEach(salaryOptions, id: \.self) { amount in
                    Text(payOption(amount)).tag(Optional(amount))
                }
            }
            .pickerStyle(.menu)
            .accessibilityIdentifier("recruiterSalaryCeiling")
            if !preferences.validPayRange {
                Text("Choose a maximum at or above your minimum, or remove the maximum.")
                    .font(.footnote).foregroundStyle(.red)
                    .accessibilityIdentifier("recruiterPayRangeError")
            }
            Text("Changing the pay period estimates a full-time year of 2,080 hours. Check the converted amounts.")
                .font(.footnote).foregroundStyle(.secondary)
            Toggle("Consider jobs below this target", isOn: $preferences.flexible)
            Divider()
            Text("Where you work").font(.headline)
            mode("Remote", "remote")
            mode("Hybrid", "hybrid")
            mode("On-site", "onsite")
            if preferences.modes.contains("remote") {
                LocationSuggestionField(title: "Remote work state/region, country", value: $preferences.remoteRegion)
                Text("Where you will physically work. Remote employers may only hire in certain regions.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            if preferences.modes.contains("hybrid") || preferences.modes.contains("onsite") {
                LocationSuggestionField(title: "Office city, state/region", value: $preferences.commute)
                Text("An office location you can commute to. Remote hiring eligibility is checked separately.")
                    .font(.footnote).foregroundStyle(.secondary)
            }

        }.jobCardSurface()
    }

    private var positionLevels: some View {
        let selected = RecruiterPositionLevel.allCases.filter { preferences.levels?.contains($0.rawValue) == true }
        return DisclosureGroup {
            VStack(alignment: .leading, spacing: 12) {
                Text("Leave all levels unselected to consider any level.")
                    .font(.footnote).foregroundStyle(.secondary)
                ForEach(RecruiterPositionLevel.allCases, id: \.self) { level in
                    Toggle(level.title, isOn: Binding(get: {
                        preferences.levels?.contains(level.rawValue) == true
                    }, set: { enabled in
                        var updated = (preferences.levels ?? []).filter { $0 != level.rawValue }
                        if enabled { updated.append(level.rawValue) }
                        preferences.levels = updated.isEmpty ? nil : updated
                    }))
                    .accessibilityIdentifier("recruiterLevel-\(level.rawValue)")
                }
            }
            .padding(.top, 8)
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                Text("Position levels").font(.headline)
                Text(selected.isEmpty ? "Any level" : selected.map(\.title).joined(separator: ", "))
                    .font(.subheadline).foregroundStyle(.secondary)
            }
        }
        .accessibilityIdentifier("recruiterPositionLevels")
    }

    private func payOption(_ amount: Int) -> String {
        amount.formatted(.currency(code: preferences.currency).precision(.fractionLength(0)))
            + (preferences.period == "hour" ? " / hour" : " / year")
    }

    private var salaryOptions: [Int] {
        let values = preferences.period == "hour"
            ? Array(stride(from: 0, through: 150, by: 1)) + Array(stride(from: 155, through: 500, by: 5))
            : Array(stride(from: 0, through: 200_000, by: 1_000)) + Array(stride(from: 205_000, through: 300_000, by: 5_000)) + Array(stride(from: 310_000, through: 1_000_000, by: 10_000))
        var options = Set(values + [preferences.salary])
        if let ceiling = preferences.salaryCeiling { options.insert(ceiling) }
        return options.sorted()
    }

    private func mode(_ label: String, _ value: String) -> some View {
        Toggle(label, isOn: Binding(get: { preferences.modes.contains(value) }, set: { enabled in
            preferences.modes.removeAll { $0 == value }
            if enabled { preferences.modes.append(value) }
        }))
    }

    private var results: some View {
        let groups = Dictionary(grouping: state?.matches ?? [], by: \.resultGroup)
        let active = selectedGroup ?? RecruiterResultGroup.allCases.first { groups[$0] != nil } ?? .close
        let matches = groups[active] ?? []
        return VStack(alignment: .leading, spacing: 16) {
            Text("Your shortlist").font(.title.bold()).accessibilityAddTraits(.isHeader)
            if state?.stage == "stopped" {
                Label(groups.isEmpty ? "Search stopped" : "Search stopped. Saved comparisons are still available.",
                      systemImage: "stop.circle")
                    .font(.subheadline).foregroundStyle(.secondary)
            } else if state?.stage == "complete", state?.error.isEmpty == true {
                Label("Search complete", systemImage: "checkmark.circle")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            if let coverage = state?.coverage, coverage != "success" && coverage != "stopped" {
                Label(coverage == "failed" ? "Employer discovery couldn’t finish."
                      : "Some employer sources couldn’t finish. Coverage is partial.",
                      systemImage: "wifi.exclamationmark")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            if let count = state?.deferred, count > 0 {
                Text(count == 1 ? "1 additional opening is awaiting comparison."
                     : "\(count) additional openings are awaiting comparison.")
                    .font(.footnote).foregroundStyle(.secondary)
            }

            VStack(spacing: 8) {
                ForEach(RecruiterResultGroup.allCases, id: \.self) { group in
                    resultGroupButton(group, count: groups[group]?.count ?? 0, selected: group == active)
                }
            }

            if matches.isEmpty && state?.busy != true {
                VStack(alignment: .leading, spacing: 10) {
                    Text(active.emptyTitle).font(.headline)
                    if groups.isEmpty {
                        Text("Review your search preferences or browse Pulled Openings.")
                            .font(.subheadline).foregroundStyle(.secondary)
                        Button("Adjust preferences") { editingPreferences = true }
                    }
                }.jobCardSurface()
            }
            ForEach(matches) { match in
                resultCard(match)
            }
        }
    }

    private func resultGroupButton(_ group: RecruiterResultGroup, count: Int, selected: Bool) -> some View {
        Button { selectedGroup = group } label: {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(group.title).font(.headline)
                    Text(group.guidance).font(.footnote).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)

                Text(count.formatted()).font(.title3.monospacedDigit().weight(.semibold))
                    .foregroundStyle(JobsTheme.accent)
                    .fixedSize()
                Image(systemName: selected ? "checkmark.circle.fill" : "chevron.right")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(selected ? JobsTheme.accent : Color.secondary)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .frame(minHeight: 44)
            .contentShape(.rect(cornerRadius: 12))
            .background(selected ? JobsTheme.accent.opacity(0.10) : JobsTheme.surface,
                        in: .rect(cornerRadius: 12))
            .overlay {
                RoundedRectangle(cornerRadius: 12)
                    .strokeBorder(selected ? JobsTheme.accent : JobsTheme.border)
            }
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(group.title)
        .accessibilityValue(count == 1 ? "1 opening" : "\(count) openings")
        .accessibilityHint(group.guidance)
        .accessibilityAddTraits(selected ? [.isButton, .isSelected] : .isButton)
        .accessibilityIdentifier("shortlistGroup-\(group.rawValue)")
    }

    private func resultCard(_ match: RecruiterState.Match) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(match.label).font(.caption.weight(.semibold)).foregroundStyle(JobsTheme.accent)
            Text(match.title).font(.title3.bold()).accessibilityAddTraits(.isHeader)
            Text(match.employer).font(.subheadline.weight(.medium))
            if match.resultGroup == .review {
                ConfirmationReasonsView(reasons: match.confirmationReasons, fallback: match.reason)
            }
            if !match.location.isEmpty {
                Text(match.location).font(.footnote).foregroundStyle(.secondary)
            }
            LabeledContent("Employer pay", value: match.salary)
                .font(.footnote).foregroundStyle(.secondary)
            if !match.reason.isEmpty && match.resultGroup != .review {
                Text(match.reason).font(.subheadline)
            }
            if match.resultGroup == .review,
               !match.checks.isEmpty || !match.gaps.isEmpty || match.confirmationReasons?.isEmpty == false {
                DisclosureGroup("Full comparison") {
                    if !match.reason.isEmpty && match.confirmationReasons?.isEmpty == false {
                        Text(match.reason).font(.subheadline).padding(.top, 6)
                    }
                    comparisonChecks(match)
                }
            } else {
                comparisonChecks(match)
            }
            if match.marketPayTargetMatch == true {
                Label("Market range reaches your pay target", systemImage: "checkmark.circle")
                    .font(.footnote.weight(.medium))
            } else if match.marketPayTargetMatch == false {
                Label("Market estimate is below your target", systemImage: "info.circle")
                    .font(.footnote.weight(.medium))
            }
            if match.publishedPayTargetMatch == false {
                Label("Employer pay is below your target", systemImage: "info.circle")
                    .font(.footnote.weight(.medium))
            }
            if match.publishedPayCeilingMatch == false {
                Label("Employer pay is above your maximum", systemImage: "info.circle")
                    .font(.footnote.weight(.medium))
            }
            if match.resultGroup != .avoid, match.marketPayAvailable == true, match.payTarget != nil {
                Button("Market pay estimate", systemImage: "magnifyingglass") { researchingPay = match }
                    .buttonStyle(.bordered)
                    .accessibilityIdentifier("shortlistMarketPay")
            }
            if !match.resumeEvidence.isEmpty || !match.jobEvidence.isEmpty || !match.emphasis.isEmpty {
                DisclosureGroup("Supporting evidence") {
                    VStack(alignment: .leading, spacing: 8) {
                        if !match.resumeEvidence.isEmpty {
                            Text("Your experience").font(.subheadline.bold())
                            Text(match.resumeEvidence).font(.footnote)
                        }
                        if !match.jobEvidence.isEmpty {
                            Text("Employer duties").font(.subheadline.bold())
                            Text(match.jobEvidence).font(.footnote)
                        }
                        if !match.emphasis.isEmpty {
                            Text("What to emphasize").font(.subheadline.bold())
                            ForEach(Array(match.emphasis.enumerated()), id: \.offset) { point in
                                Text(point.element).font(.footnote)
                            }
                        }
                    }
                    .padding(.top, 8)
                }
            }
            if let jobID = match.jobId {
                NavigationLink("View job & next steps", value: jobID).buttonStyle(.bordered)
            } else if let opening = match.opening {
                NavigationLink {
                    RecruiterOpeningDetail(opening: opening, address: workspace.address, shortlistMatch: match,
                                           onMarketPayUpdated: { await refreshAfterPayResearch(for: match.id) })
                } label: {
                    Text("View opening")
                }
                .buttonStyle(.bordered)
                .accessibilityIdentifier("shortlistViewOpening")
            }
        }
        .jobCardSurface()
    }

    @ViewBuilder private func comparisonChecks(_ match: RecruiterState.Match) -> some View {
        comparisonItems("What Jobs checked", match.checks)
        comparisonItems("Gaps to review", match.gaps)
    }

    @ViewBuilder private func comparisonItems(_ heading: String, _ items: [String]) -> some View {
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Text(heading).font(.subheadline.bold())
                ForEach(Array(items.enumerated()), id: \.offset) { item in
                    Text(item.element).font(.footnote).foregroundStyle(.secondary)
                }
            }
        }
    }

    @MainActor private func refreshAfterPayResearch(for matchID: String?) async {
        refreshingMarketPay = true
        defer { refreshingMarketPay = false }
        let wasInReview = state?.matches.first(where: { $0.id == matchID })?.resultGroup == .review
        await reload()
        if wasInReview, selectedGroup == .review,
           let group = state?.matches.first(where: { $0.id == matchID })?.resultGroup,
           group == .close || group == .adjacent {
            selectedGroup = group
        }
    }

    @MainActor private func openFilePicker() {
        workspace.choosingRecruiterFile = true
        importing = true
    }

    @MainActor private func reload(polling: Bool = false) async {
        guard !workspace.address.isEmpty, !workspace.choosingRecruiterFile,
              !polling || !refreshingMarketPay else { return }
        let address = workspace.address
        let load = UUID()
        latestLoad = load
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        do {
            if polling, let current = state, let lastRecruiterLoad,
               current.busy || Date.now.timeIntervalSince(lastRecruiterLoad) < 45 {
                let statusData = try await DashboardAPI.request("/api/recruiter", at: address,
                                                               query: [URLQueryItem(name: "status", value: "1")])
                guard latestLoad == load, workspace.address == address,
                      !Task.isCancelled, !workspace.choosingRecruiterFile else { return }
                let status = try decoder.decode(RecruiterState.Status.self, from: statusData)
                // A matching progress change can publish a new comparison, posting check, or estimate.
                let resultsChanged = status.stage == "matching" && current.progress != status.progress
                if current.version == status.version && current.stage == status.stage && !resultsChanged {
                    state?.progress = status.progress
                    state?.stopRequested = status.stopRequested
                    if statusUnavailable { error = nil }
                    statusUnavailable = false
                    lastStatusCheck = .now
                    return
                }
            }
            let data = try await DashboardAPI.request("/api/recruiter", at: address,
                                                      query: [URLQueryItem(name: "openings", value: "1")])
            guard latestLoad == load, workspace.address == address,
                  !Task.isCancelled, !workspace.choosingRecruiterFile else { return }
            let next = try decoder.decode(RecruiterState.self, from: data)
            if lastVersion != next.version {
                if let saved = next.preferences { preferences = saved }
                lastVersion = next.version
            }
            let finished = state?.busy == true && !next.busy
            if state?.version != next.version || state == nil || statusUnavailable { error = nil }
            lastStatusCheck = .now
            lastRecruiterLoad = .now
            statusUnavailable = false
            state = next
            if finished {
                // The polling task restarts when the search leaves its active state.
                Task {
                    guard workspace.address == address else { return }
                    await workspace.refresh()
                }
            }
        } catch is CancellationError { } catch {
            guard latestLoad == load, workspace.address == address,
                  !Task.isCancelled, !workspace.choosingRecruiterFile else { return }
            if state?.busy == true {
                statusUnavailable = true
                self.error = nil
            } else {
                self.error = error.localizedDescription
            }
        }
    }

    @MainActor private func analyze(_ text: String?, fileName: String? = nil, fileData: Data? = nil) async {
        var payload: [String: Any] = ["action": "analyze", "version": state?.version ?? 0]
        if let text { payload["resume"] = text }
        if let fileName, let fileData { payload["file_name"] = fileName; payload["file_data"] = fileData.base64EncodedString() }
        await submit(payload)
    }

    @MainActor private func search() async {
        guard preferences.validPayRange else {
            editingPreferences = true
            return
        }
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        do {
            let value = try JSONSerialization.jsonObject(with: encoder.encode(preferences))
            await submit(["action": "search", "version": state?.version ?? 0, "preferences": value])
        } catch { self.error = error.localizedDescription }
    }

    @MainActor private func stopSearch() async {
        guard let version = state?.version else { return }
        let address = workspace.address
        stoppingSearch = true
        defer { stoppingSearch = false }
        do {
            let body = try JSONSerialization.data(withJSONObject: ["action": "stop", "version": version])
            _ = try await DashboardAPI.request("/api/recruiter", at: address, body: body)
            guard workspace.address == address else { return }
            if state?.version == version, state?.busy == true { state?.stopRequested = true }
            await reload(polling: true)
        } catch {
            guard workspace.address == address else { return }
            await reload(polling: true)
            if state?.version == version, state?.busy == true, state?.stopRequested != true {
                self.error = error.localizedDescription
            }
        }
    }

    @MainActor private func submit(_ payload: [String: Any]) async {
        guard submissionTitle == nil else { return }
        submissionTitle = payload["action"] as? String == "search" ? "Starting your search" : "Sending your résumé"
        defer { submissionTitle = nil }
        error = nil
        do {
            let body = try JSONSerialization.data(withJSONObject: payload)
            _ = try await DashboardAPI.request("/api/recruiter", at: workspace.address, body: body)
            editingPreferences = false
            await reload()
        } catch { self.error = error.localizedDescription }
    }
}

private struct RecruiterOpeningsView: View {
    let address: String
    @State private var query = ""
    @State private var displayedQuery: String?
    @State private var openings: [RecruiterOpening] = []
    @State private var nextBefore: String?
    @State private var latestRequest = UUID()
    @State private var loading = true
    @State private var error: String?

    var body: some View {
        let filter = query.trimmingCharacters(in: .whitespacesAndNewlines)
        List {
            if let error {
                Text(error).foregroundStyle(.secondary)
                if openings.isEmpty && !loading {
                    Button("Retry") { Task { await load(query: filter) } }
                }
            }
            if openings.isEmpty {
                if loading {
                    ProgressView("Loading openings…")
                } else if error == nil {
                    if filter.isEmpty {
                        ContentUnavailableView("No openings yet", systemImage: "tray",
                                               description: Text("Openings will appear here as your recruiter finds them."))
                    } else {
                        ContentUnavailableView.search(text: filter)
                    }
                }
            }
            ForEach(openings) { opening in
                NavigationLink {
                    RecruiterOpeningDetail(opening: opening, address: address)
                } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(opening.title).font(.headline)
                        if !opening.employer.isEmpty { Text(opening.employer).font(.subheadline) }
                        if !opening.location.isEmpty {
                            Text(opening.location).font(.footnote).foregroundStyle(.secondary)
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
            if let nextBefore {
                if loading {
                    ProgressView("Loading more openings…")
                } else {
                    Button("Load more openings") {
                        Task { await load(query: filter, before: nextBefore) }
                    }
                }
            }
        }
        .navigationTitle("Pulled Openings")
        .navigationBarTitleDisplayMode(.inline)
        .searchable(text: $query, prompt: "Search titles or employers")
        .task(id: filter) { await load(query: filter, debounce: !filter.isEmpty) }
        .refreshable { await load(query: filter) }
    }

    @MainActor private func load(query filter: String, before: String? = nil, debounce: Bool = false) async {
        guard before == nil || (!loading && displayedQuery == filter) else { return }
        let request = UUID()
        latestRequest = request
        loading = true
        error = nil
        if displayedQuery != filter {
            displayedQuery = filter
            openings = []
            nextBefore = nil
        }
        defer {
            if latestRequest == request { loading = false }
        }
        do {
            if debounce { try await Task.sleep(for: .milliseconds(300)) }
            let page = try await DashboardAPI.recruiterOpenings(at: address, before: before, filter: filter)
            guard latestRequest == request, !Task.isCancelled else { return }
            if before == nil {
                openings = page.openings
            } else {
                var seen = Set(openings.map(\.id))
                openings.append(contentsOf: page.openings.filter { seen.insert($0.id).inserted })
            }
            nextBefore = page.nextBefore
        } catch {
            guard latestRequest == request, !Task.isCancelled else { return }
            self.error = DashboardAPI.connectionMessage(for: error)
        }
    }
}

struct ConfirmationReasonsView: View {
    let reasons: [RecruiterConfirmationReason]?
    let fallback: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Why this needs confirmation", systemImage: "exclamationmark.circle")
                .font(.subheadline.bold())
                .accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier("shortlistConfirmationHeading")
            if let reasons, !reasons.isEmpty {
                ForEach(Array(reasons.enumerated()), id: \.offset) { reason in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(reason.element.reason).font(.subheadline.weight(.medium))
                        Text(reason.element.whatToCheck).font(.footnote).foregroundStyle(.secondary)
                    }
                }
            } else {
                Text(fallback.isEmpty ? "Review the employer’s requirements and the evidence in the comparison." : fallback)
                    .font(.subheadline)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(Color.orange.opacity(0.12), in: .rect(cornerRadius: 10))
    }
}

private struct RecruiterOpeningDetail: View {
    let opening: RecruiterOpening
    let address: String
    var shortlistMatch: RecruiterState.Match? = nil
    var onMarketPayUpdated: (@MainActor () async -> Void)? = nil
    @State private var comparison: RecruiterOpeningMatch?
    @State private var comparing = false
    @State private var error: String?
    @State private var showingMarketPay = false

    var body: some View {
        let displayed = comparison ?? shortlistMatch.map { match in
            RecruiterOpeningMatch(group: match.group, reason: match.reason, resumeEvidence: match.resumeEvidence,
                                  jobEvidence: match.jobEvidence, checks: match.checks, gaps: match.gaps,
                                  confirmationReasons: match.confirmationReasons)
        }
        List {
            Section {
                Text(opening.title).font(.title2.bold())
                if !opening.employer.isEmpty { LabeledContent("Employer", value: opening.employer) }
                if let displayed, displayed.group == RecruiterResultGroup.review.rawValue {
                    ConfirmationReasonsView(reasons: displayed.confirmationReasons, fallback: displayed.reason)
                }
                if !opening.location.isEmpty { LabeledContent("Location", value: opening.location) }
                if !opening.workArrangement.isEmpty {
                    LabeledContent("Work arrangement", value: opening.workArrangement.capitalized)
                }
                LabeledContent("Employer pay", value: opening.salary.isEmpty ? "Not disclosed" : opening.salary)
                if let shortlistMatch, shortlistMatch.resultGroup != .avoid,
                   shortlistMatch.marketPayAvailable == true {
                    Button("Market pay estimate", systemImage: "magnifyingglass") { showingMarketPay = true }
                }
                if !opening.discoveredAt.isEmpty {
                    LabeledContent("Found", value: displayTimestamp(opening.discoveredAt))
                }
                if let url = DashboardAPI.webURL(opening.postingUrl), url.scheme?.lowercased() == "https" {
                    Link(destination: url) {
                        Label("Open employer posting", systemImage: "arrow.up.right")
                    }
                }
            }
            Section("Fit comparison") {
                if comparing {
                    ProgressView("Comparing with your experience…")
                } else if let displayed {
                    Text((RecruiterResultGroup(rawValue: displayed.group) ?? .avoid).matchLabel).font(.headline)
                    if !displayed.reason.isEmpty,
                       displayed.group != RecruiterResultGroup.review.rawValue || displayed.confirmationReasons?.isEmpty == false {
                        Text(displayed.reason)
                    }
                } else {
                    Text("Awaiting comparison").foregroundStyle(.secondary)
                }
                if !comparing && (displayed == nil || shortlistMatch != nil) {
                    Button("Compare with my experience") { Task { await compare() } }
                }
                if let error { Text(error).foregroundStyle(.secondary) }
            }
            if let displayed {
                if !displayed.resumeEvidence.isEmpty || !displayed.jobEvidence.isEmpty {
                    Section("Evidence") {
                        if !displayed.resumeEvidence.isEmpty {
                            LabeledContent("Your experience", value: displayed.resumeEvidence)
                        }
                        if !displayed.jobEvidence.isEmpty {
                            LabeledContent("Employer duties", value: displayed.jobEvidence)
                        }
                    }
                }
                let issues = displayed.checks + displayed.gaps
                if !issues.isEmpty {
                    Section("Fit checks and gaps") {
                        ForEach(Array(issues.enumerated()), id: \.offset) { issue in
                            Text(issue.element)
                        }
                    }
                }
            }
        }
        .navigationTitle("Opening")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(isPresented: $showingMarketPay) {
            MarketPayView(target: .opening(opening.id), address: address, onResearchUpdated: onMarketPayUpdated)
        }
    }

    @MainActor private func compare() async {
        guard !comparing else { return }
        comparing = true
        error = nil
        defer { comparing = false }
        do {
            comparison = try await DashboardAPI.compareRecruiterOpening(opening.id, at: address)
        } catch {
            self.error = DashboardAPI.connectionMessage(for: error)
        }
    }
}

private struct RecruiterActivityView: View {
    struct Entry: Decodable, Identifiable {
        let id, operation: Int
        let recordedAt: Date
        let progress: RecruiterState.Progress
    }

    struct Page: Decodable {
        let entries: [Entry]
        let nextBefore: Int?
    }

    @Environment(\.dismiss) private var dismiss
    let address: String
    @State private var entries: [Entry] = []
    @State private var nextBefore: Int?
    @State private var loading = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            List {
                if let error { Text(error).foregroundStyle(.secondary) }
                if loading && entries.isEmpty {
                    ProgressView("Loading search activity")
                } else if entries.isEmpty && error == nil {
                    Text("No search activity has been recorded yet.").foregroundStyle(.secondary)
                }
                ForEach(Set(entries.map(\.operation)).sorted(by: >), id: \.self) { attempt in
                    Section("Attempt \(attempt)") {
                        ForEach(entries.filter { $0.operation == attempt }) { entry in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(entry.progress.stage).font(.headline)
                                if let count = entry.progress.countLabel { Text(count).font(.subheadline) }
                                if let source = entry.progress.source { Text(source).font(.subheadline) }
                                if let issues = entry.progress.issues, issues > 0 {
                                    Text(issues == 1 ? "1 issue recorded" : "\(issues) issues recorded").font(.subheadline)
                                }
                                if let reason = entry.progress.reason {
                                    Text("Status: \(reason)").font(.caption).foregroundStyle(.secondary)
                                }
                                Text(entry.recordedAt.formatted(date: .abbreviated, time: .standard))
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                if let nextBefore {
                    Button("Load earlier activity") { Task { await load(before: nextBefore) } }
                        .disabled(loading)
                }
            }
            .navigationTitle("Search activity")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() } }
                ToolbarItem(placement: .primaryAction) {
                    Button("Refresh activity", systemImage: "arrow.clockwise") { Task { await load() } }
                        .disabled(loading)
                }
            }
            .task { await load() }
            .refreshable { await load() }
        }
    }

    @MainActor private func load(before: Int? = nil) async {
        guard !loading else { return }
        loading = true
        defer { loading = false }
        do {
            let query = before.map { [URLQueryItem(name: "before", value: String($0))] }
            let data = try await DashboardAPI.request("/api/recruiter/activity", at: address, query: query)
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            decoder.dateDecodingStrategy = .iso8601
            let page = try decoder.decode(Page.self, from: data)
            if before == nil { entries = page.entries }
            else { entries.append(contentsOf: page.entries) }
            nextBefore = page.nextBefore
            error = nil
        } catch is CancellationError { } catch {
            if (error as? DashboardAPI.ServerError)?.status == 404 {
                self.error = "Search activity needs a newer Jobs server."
            } else {
                self.error = DashboardAPI.connectionMessage(for: error)
            }
        }
    }
}

@MainActor
private final class LocationSuggestions: NSObject, ObservableObject, MKLocalSearchCompleterDelegate {
    @Published var results: [MKLocalSearchCompletion] = []
    private let completer = MKLocalSearchCompleter()
    override init() {
        super.init()
        completer.delegate = self
        completer.resultTypes = .address
    }
    func search(_ text: String) {
        guard text.trimmingCharacters(in: .whitespacesAndNewlines).count >= 2 else {
            completer.cancel(); results = []; return
        }
        completer.queryFragment = text
    }
    func clear() { completer.cancel(); results = [] }
    func completerDidUpdateResults(_ completer: MKLocalSearchCompleter) {
        results = Array(completer.results.prefix(5))
    }
    func completer(_ completer: MKLocalSearchCompleter, didFailWithError error: Error) { results = [] }
}

private struct LocationSuggestionField: View {
    let title: String
    @Binding var value: String
    @StateObject private var suggestions = LocationSuggestions()
    @FocusState private var focused: Bool
    @State private var selected = false
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            TextField(title, text: $value).textFieldStyle(.roundedBorder).focused($focused)
                .onChange(of: value) { _, text in
                    if selected { selected = false; return }
                    if focused { suggestions.search(text) }
                }
                .onChange(of: focused) { _, isFocused in if !isFocused { suggestions.clear() } }
            if focused {
                ForEach(suggestions.results, id: \.self) { result in
                    Button {
                        selected = true
                        value = [result.title, result.subtitle].filter { !$0.isEmpty }.joined(separator: ", ")
                        suggestions.clear(); focused = false
                    } label: {
                        VStack(alignment: .leading) {
                            Text(result.title)
                            if !result.subtitle.isEmpty { Text(result.subtitle).font(.caption).foregroundStyle(.secondary) }
                        }.frame(maxWidth: .infinity, alignment: .leading)
                    }.buttonStyle(.plain).padding(.vertical, 4)
                }
                Text("Suggestions use Apple Maps. You can also type or correct a location yourself.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }
}

private struct MasterResume: Decodable { let text, name, file: String }

struct MasterResumeView: View {
    @Environment(\.dismiss) private var dismiss
    let workspace: Workspace
    @State private var master: MasterResume?
    @State private var fileURL: URL?
    @State private var previewURL: URL?
    @State private var error: String?
    var body: some View {
        NavigationStack {
            List {
                if let master {
                    Section("Master résumé") {
                        if !master.name.isEmpty { Text(master.name) }
                        if let fileURL {
                            Button("View original file") { previewURL = fileURL }
                            ShareLink("Share original file", item: fileURL)
                        }
                        if master.file.isEmpty && !master.text.isEmpty { Text("The extracted text is saved. Upload the original again to keep a copy of the file.").font(.footnote) }
                        Text(master.text.isEmpty ? "No résumé has been uploaded yet." : master.text).textSelection(.enabled)
                    }
                } else if let error { Text(error).foregroundStyle(.red) }
                else { ProgressView("Loading résumé…") }
            }
            .navigationTitle("Master Résumé")
            .toolbar { Button("Close") { dismiss() } }
            .task { await load() }
            .quickLookPreview($previewURL)
            .onDisappear { if let fileURL { try? FileManager.default.removeItem(at: fileURL.deletingLastPathComponent()) } }
        }
    }
    private func load() async {
        do {
            let data = try await DashboardAPI.request("/api/recruiter/resume", at: workspace.address)
            let result = try JSONDecoder().decode(MasterResume.self, from: data)
            if !result.file.isEmpty, let bytes = Data(base64Encoded: result.file) {
                let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
                try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
                let url = folder.appendingPathComponent(URL(fileURLWithPath: result.name).lastPathComponent)
                try bytes.write(to: url, options: [.atomic, .completeFileProtection]); fileURL = url
            }
            master = result
        } catch { self.error = DashboardAPI.connectionMessage(for: error) }
    }
}

fileprivate enum RecruiterMarketPayTarget {
    case job(Int)
    case opening(String)

    var path: String {
        switch self {
        case .job(let id): "/api/jobs/\(id)/market-pay"
        case .opening(let id): "/api/recruiter/openings/\(id)/market-pay"
        }
    }
}

struct MarketPayView: View {
    @Environment(\.dismiss) private var dismiss
    private let target: RecruiterMarketPayTarget
    let address: String
    private let onResearchUpdated: (@MainActor () async -> Void)?

    @State private var report: Report?
    @State private var loading = false
    @State private var error: String?

    init(jobID: Int, address: String, onResearchUpdated: (@MainActor () async -> Void)? = nil) {
        self.init(target: .job(jobID), address: address, onResearchUpdated: onResearchUpdated)
    }

    fileprivate init(target: RecruiterMarketPayTarget, address: String,
                     onResearchUpdated: (@MainActor () async -> Void)? = nil) {
        self.target = target
        self.address = address
        self.onResearchUpdated = onResearchUpdated
    }

    private struct Report: Decodable {
        struct Citation: Decodable {
            let url: URL
            let title: String
            let end: Int
        }
        let summary: String?
        let citations: [Citation]
        let researchedAt: String
        let geography, dataPeriod: String?
        let stale, targetMatch: Bool?
    }

    private struct Response: Decodable {
        let research: Report?
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    if let report {
                        if let summary = report.summary {
                            if report.geography == nil || report.dataPeriod == nil {
                                Text("Earlier research").font(.subheadline.bold())
                            }
                            Text(citedText(summary, citations: report.citations))
                                .accessibilityIdentifier("marketPayEstimate")
                            if let reachesTarget = report.targetMatch {
                                Text(reachesTarget ? "Market range reaches your pay target" : "Market range is below your pay target")
                                    .font(.subheadline.weight(.medium))
                            }
                        } else {
                            Text("The research didn’t find enough reliable pay data for this role.")
                        }
                        Text("Researched \(displayTimestamp(report.researchedAt))")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                    if !loading && (report == nil || report?.stale == true) {
                        Button(report == nil ? "Research market pay" : "Refresh market pay", systemImage: "magnifyingglass") {
                            Task { await load(research: true) }
                        }
                    }
                    if loading { ProgressView("Looking up market pay…") }
                    if let error { Text(error).font(.footnote).foregroundStyle(.secondary) }
                }
                if let citations = report?.citations, !citations.isEmpty {
                    Section("Sources") {
                        ForEach(Array(citations.enumerated()), id: \.offset) { index, citation in
                            Link("[\(index + 1)] \(citation.title)", destination: citation.url)
                        }
                    }
                }
            }
            .navigationTitle("Market pay estimate")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() } } }
            .task { await load(research: false) }
        }
    }

    private func citedText(_ summary: String, citations: [Report.Citation]) -> AttributedString {
        let scalars = summary.unicodeScalars
        var result = AttributedString()
        var cursor = scalars.startIndex
        for (index, citation) in citations.enumerated().sorted(by: { $0.element.end < $1.element.end }) {
            guard citation.url.scheme == "https", citation.end >= 0,
                  let end = scalars.index(scalars.startIndex, offsetBy: citation.end, limitedBy: scalars.endIndex),
                  end >= cursor else { continue }
            result.append(AttributedString(String(scalars[cursor..<end])))
            var link = AttributedString(" [\(index + 1)]")
            link.link = citation.url
            result.append(link)
            cursor = end
        }
        result.append(AttributedString(String(scalars[cursor...])))
        return result
    }

    @MainActor private func load(research: Bool) async {
        guard !loading else { return }
        loading = true
        error = nil
        defer { loading = false }
        do {
            let data = try await DashboardAPI.request(target.path, at: address,
                                                      body: research ? Data("{}".utf8) : nil)
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            report = try decoder.decode(Response.self, from: data).research
            if research { await onResearchUpdated?() }
        } catch is CancellationError {
        } catch {
            self.error = error.localizedDescription
        }
    }
}

private struct TailoredState: Decodable {
    let draft: String
    let version: Int
    let hasResume, hasDescription, stale: Bool
    let resumeHash, postingHash: String
}
private struct TailoredResponse: Decodable { let draft: String?; let version: Int }

struct TailoredResumeView: View {
    @Environment(\.dismiss) private var dismiss
    let jobID: Int
    let address: String
    @State private var state: TailoredState?
    @State private var draft = ""
    @State private var savedDraft = ""
    @State private var version = 0
    @State private var busy = false
    @State private var error: String?
    @State private var confirmingGenerate = false
    @State private var confirmingClose = false
    private var dirty: Bool { draft != savedDraft }
    private var path: String { "/api/jobs/\(jobID)/tailored-resume" }
    var body: some View {
        NavigationStack {
            List {
                if let state {
                    Section {
                        Text("Create a job-specific draft from your saved master résumé and this employer's description. Your master stays unchanged. Review every detail for accuracy.")
                        if state.stale { Text("Your master résumé or the posting has changed since this draft was saved. Review the draft again.").foregroundStyle(.orange) }
                        if !state.hasResume || !state.hasDescription { Text("A master résumé and an employer description are required.") }
                        Button("Generate with AI", systemImage: "sparkles") { confirmingGenerate = true }
                            .disabled(busy || !state.hasResume || !state.hasDescription)
                    }
                    Section("Your editable draft") {
                        TextEditor(text: $draft).frame(minHeight: 300).disabled(busy)
                        if !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                            ShareLink("Share draft text", item: draft)
                        }
                        Text("No experience, dates, credentials or numbers should be invented. Check the draft before using it.").font(.footnote).foregroundStyle(.secondary)
                    }
                } else if error == nil { ProgressView("Loading résumé draft…") }
                if busy { ProgressView("Working…") }
                if let error { Text(error).foregroundStyle(.red) }
            }
            .navigationTitle("Tailored Résumé")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Close") { if dirty { confirmingClose = true } else { dismiss() } }.disabled(busy) }
                ToolbarItem(placement: .confirmationAction) { Button("Save") { Task { await send("save") } }.disabled(busy || state == nil || !dirty || draft.count > 30000) }
            }
            .confirmationDialog("Generate a new draft?", isPresented: $confirmingGenerate) {
                Button("Send to AI") { Task { await send("generate") } }
            } message: { Text("Your master résumé and this job description will be sent to OpenAI. This can incur charges and replaces the draft currently on screen, but not the saved draft until you save.") }
            .confirmationDialog("Close without saving?", isPresented: $confirmingClose) {
                Button("Discard edits", role: .destructive) { dismiss() }
            }
            .interactiveDismissDisabled(dirty || busy)
            .task { await load() }
        }
    }
    private func load() async {
        do {
            let data = try await DashboardAPI.request(path, at: address)
            let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
            let value = try decoder.decode(TailoredState.self, from: data)
            state = value; draft = value.draft; savedDraft = value.draft; version = value.version
        } catch { self.error = DashboardAPI.connectionMessage(for: error) }
    }
    private func send(_ action: String) async {
        guard let state else { return }
        busy = true; error = nil
        defer { busy = false }
        do {
            let payload: [String: Any] = ["action": action, "version": version, "draft": draft,
                "resume_hash": state.resumeHash, "posting_hash": state.postingHash]
            let body = try JSONSerialization.data(withJSONObject: payload)
            let data = try await DashboardAPI.request(path, at: address, body: body)
            let response = try JSONDecoder().decode(TailoredResponse.self, from: data)
            if let generated = response.draft { draft = generated }
            else { savedDraft = draft; version = response.version }
        } catch { self.error = DashboardAPI.connectionMessage(for: error) }
    }
}
