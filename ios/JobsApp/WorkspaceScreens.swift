import SwiftUI
import PDFKit
import UniformTypeIdentifiers
import UserNotifications

struct SearchScreen: View {
    let workspace: Workspace

    private func searchOutcome(_ run: SearchRun) -> String {
        let found = (run.report.newQualified ?? 0) + (run.report.newReview ?? 0)
        let result = found == 1 ? "1 new listing saved." : "\(found) new listings saved."
        switch run.state {
        case "partial": return "Search finished with incomplete checks. " + result + " Run again to retry."
        case "failed": return "The search couldn’t complete. Previously saved listings are still here. Try again."
        case "interrupted": return "The last search was interrupted. Run it again to continue."
        default: return found == 0 ? "Search finished. No new listings matched." : "Search finished. " + result
        }
    }

    var body: some View {
        List {
            if let dashboard = workspace.dashboard {
                if let searches = dashboard.savedSearches {
                    Section("Your matches") {
                        NavigationLink {
                            MatchInbox(workspace: workspace)
                        } label: {
                            LabeledContent("Match Alerts", value: "\(dashboard.unreadMatchCount ?? 0) unread")
                        }
                        NavigationLink {
                            SavedSearchesScreen(workspace: workspace)
                        } label: {
                            LabeledContent("Saved Searches", value: String(searches.count))
                        }
                    }
                }
                Section {
                    Button("Run Employer Search", systemImage: "magnifyingglass") {
                        Task { await workspace.startSearch() }
                    }
                    .disabled(!workspace.connected || workspace.searchRunning || workspace.startingSearch || workspace.saving)
                    if workspace.searchConnectionLost {
                        Text("Can’t confirm the search status. The Mac may still be searching.")
                            .foregroundStyle(.secondary)
                        Button("Check search status") { Task { await workspace.checkSearchStatus() } }
                    } else if workspace.startingSearch {
                        ProgressView("Starting the search…")
                    } else if workspace.searchRunning {
                        if let progress = workspace.searchStatus?.run?.progress {
                            ProgressView(progress.label)
                            if let source = progress.source {
                                Text(source).font(.caption).foregroundStyle(.secondary)
                            }
                        } else {
                            ProgressView("Checking employer sources…")
                        }
                        Text("You can keep browsing while the Mac searches.")
                            .font(.footnote).foregroundStyle(.secondary)
                    } else if !workspace.connected {
                        Text("Reconnect to your Mac to find new jobs.").foregroundStyle(.secondary)
                    } else if let run = dashboard.runs.first, run.finished != nil {
                        Text(searchOutcome(run)).foregroundStyle(.secondary)
                            .accessibilityIdentifier("searchOutcome")
                    }
                    if let error = workspace.searchError { Text(error).foregroundStyle(.red) }
                } header: {
                    Text("Find New Jobs")
                } footer: {
                    Text("The Mac checks employer sources and updates this workspace. Some checks can take a few minutes.")
                }
                Section("Daily Search") {
                    LabeledContent("Schedule", value: dashboard.preferences.scheduleEnabled
                        ? "\(dashboard.preferences.scheduleHourUtc):00 UTC" : "Off")
                }
                Section("Search History") {
                    if dashboard.runs.isEmpty { Text("No searches yet.").foregroundStyle(.secondary) }
                    ForEach(dashboard.runs) { run in
                        NavigationLink {
                            SearchReport(run: workspace.dashboard?.runs.first { $0.id == run.id } ?? run)
                        } label: {
                            VStack(alignment: .leading, spacing: 5) {
                                Text("\(run.originLabel) · \(displayTimestamp(run.started))").font(.headline)
                                Text("\(run.state.capitalized) · \(run.report.newQualified ?? 0) qualified · \(run.report.newReview ?? 0) for review")
                                    .font(.subheadline).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
        }
        .scrollContentBackground(.hidden)
        .background(JobsTheme.canvas.ignoresSafeArea())
        .navigationTitle("Alerts")
        .refreshable { await workspace.refresh() }
    }
}

private struct SearchReport: View {
    let run: SearchRun

    var body: some View {
        List {
            Section("Results") {
                LabeledContent("Status", value: run.state.capitalized)
                LabeledContent("Run", value: run.originLabel)
                LabeledContent("Started", value: displayTimestamp(run.started))
                if let finished = run.finished, !finished.isEmpty {
                    LabeledContent("Finished", value: displayTimestamp(finished))
                }
                LabeledContent("New Qualified", value: String(run.report.newQualified ?? 0))
                LabeledContent("New for Review", value: String(run.report.newReview ?? 0))
                LabeledContent("Rechecked", value: String(run.report.reverified ?? 0))
                LabeledContent("Newly Closed", value: String(run.report.newlyClosed ?? 0))
                if let review = run.report.manualReview {
                    LabeledContent("Open Listings Needing Review", value: review.formatted())
                }
                if let duplicates = run.report.duplicates {
                    LabeledContent("Duplicates Skipped", value: duplicates.formatted())
                }
                if let deferred = run.report.deferredCandidates, deferred > 0 {
                    LabeledContent("Beyond This Run’s Limit", value: deferred.formatted())
                }
                if let deferred = run.report.deferredSourceDetails, deferred > 0 {
                    LabeledContent("Board Details Deferred", value: deferred.formatted())
                }
                if let checks = run.report.postingChecks {
                    LabeledContent("Direct Posting Checks", value: checks.formatted())
                }
                if let deferred = run.report.postingChecksDeferred, deferred > 0 {
                    LabeledContent("Direct Checks Deferred", value: deferred.formatted())
                }
                if let requests = run.report.firecrawlRequests, requests > 0 {
                    LabeledContent("Firecrawl Requests", value: requests.formatted())
                    if let credits = run.report.firecrawlCreditsReported {
                        LabeledContent("Firecrawl Credits Reported", value: credits.formatted())
                    }
                }
            }
            if let leads = run.report.topNew, !leads.isEmpty {
                Section("Top New Jobs") {
                    ForEach(leads.indices, id: \.self) { index in
                        let lead = leads[index]
                        let label = "\(lead.employer) · \(lead.title)"
                        if let url = DashboardAPI.webURL(lead.url) {
                            Link(label, destination: url)
                        } else { Text(label) }
                    }
                }
            }
            messages("Source Failures", run.report.failures)
            messages("Deferred Employer Pages", run.report.unprocessedEmployerUrls)
            messages("Activity", run.report.log)
        }
        .navigationTitle("Search Report")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func messages(_ title: String, _ items: [String]?) -> some View {
        Group {
            if let items, !items.isEmpty {
                Section(title) {
                    ForEach(items.indices, id: \.self) { Text(items[$0]) }
                }
            }
        }
    }
}

struct EmployerBoards: View {
    let workspace: Workspace
    @State private var message: String?

    var body: some View {
        List {
            if let message { Text(message).foregroundStyle(.secondary) }
            if let dashboard = workspace.dashboard {
                if dashboard.sources.isEmpty {
                    ContentUnavailableView("No Employer Sources", systemImage: "building.2",
                                           description: Text("Add a board or posting URL in Preferences."))
                }
                ForEach(dashboard.sources) { source in
                    Section {
                        Text(source.source).font(.headline)
                        LabeledContent("Status", value: source.disabled ? "Paused" : source.state.capitalized)
                        Text("\(source.kind) · \(source.count) postings at last check")
                            .font(.subheadline).foregroundStyle(.secondary)
                        if !source.checked.isEmpty { Text(displayTimestamp(source.checked)).font(.footnote) }
                        if !source.error.isEmpty { Text(source.error).foregroundStyle(.secondary) }
                        Button(source.disabled ? "Resume Source" : "Pause Source") {
                            Task { await toggle(source, dashboard: dashboard) }
                        }
                        .disabled(workspace.saving || dashboard.running)
                    }
                }
            }
        }
        .navigationTitle("Employer Boards")
        .refreshable { await workspace.refresh() }
    }

    private func toggle(_ source: EmployerSource, dashboard: Dashboard) async {
        var disabled = Set(dashboard.preferences.disabledSources)
        if source.disabled { disabled.remove(source.source) } else { disabled.insert(source.source) }
        message = nil
        do {
            let patch = ["disabled_sources": disabled.sorted()]
            try await workspace.save("/api/preferences",
                                     PreferenceUpdate(revision: dashboard.preferencesRevision, preferences: patch))
        } catch {
            message = error.localizedDescription
            if (error as? DashboardAPI.ServerError)?.status == 409 { await workspace.refresh() }
        }
    }
}

struct PreferencesScreen: View {
    let workspace: Workspace
    @Binding var keepOfflineCopy: Bool
    let editServer: () -> Void
    let openSample: () -> Void
    @State private var editingPreferences = false
    @State private var editingAdministration = false

    var body: some View {
        List {
            if let dashboard = workspace.dashboard {
                Section("Search Profile") {
                    Button("Edit Search Profile", systemImage: "slider.horizontal.3") {
                        editingPreferences = true
                    }
                    LabeledContent("Role Phrases", value: String(dashboard.preferences.categories.count))
                    LabeledContent("Selected Skills", value: String(dashboard.preferences.preferredSkills?.count ?? 0))
                    LabeledContent("Salary Target", value: dashboard.preferences.salaryFloor.formatted(.currency(code: "USD").precision(.fractionLength(0))))
                    NavigationLink("Saved Searches") { SavedSearchesScreen(workspace: workspace) }
                }
                Section("Career Advice") {
                    LabeledContent("AI Career Reviews", value: dashboard.preferences.aiEnabled ? "On" : "Off")
                    LabeledContent("Server AI Key", value: dashboard.aiConfigured ? "Configured" : "Missing")
                    LabeledContent("AI Attempts Today",
                                   value: "\(dashboard.aiAttemptsToday)/\(dashboard.preferences.aiDailyLimit)")
                }
            }
            Section("Employer Sources") {
                Button("Workspace Administration", systemImage: "gearshape") { editingAdministration = true }
                NavigationLink("Employer Boards") { EmployerBoards(workspace: workspace) }
            }
            Section("Connection") {
                Button("Server Settings", systemImage: "desktopcomputer", action: editServer)
                Text(workspace.address).font(.footnote).foregroundStyle(.secondary)
                Toggle("Keep a Copy for Offline Reading", isOn: $keepOfflineCopy)
                Text("Jobs and tracking details are stored on this iPhone for the last connected workspace. Saving changes requires a connection.")
                    .font(.footnote).foregroundStyle(.secondary)
                if let error = workspace.cacheError { Text(error).font(.footnote).foregroundStyle(.secondary) }
            }
            Section("Offline Demo") {
                Button("Explore sample jobs", systemImage: "eye", action: openSample)
            }
        }
        .scrollContentBackground(.hidden)
        .background(JobsTheme.canvas.ignoresSafeArea())
        .navigationTitle("Settings")
        .refreshable { await workspace.refresh() }
        .sheet(isPresented: $editingAdministration) {
            if let dashboard = workspace.dashboard {
                PreferencesEditor(workspace: workspace, dashboard: dashboard, administration: true)
            }
        }
        .sheet(isPresented: $editingPreferences) {
            if let dashboard = workspace.dashboard {
                PreferencesEditor(workspace: workspace, dashboard: dashboard)
            }
        }
    }
}

private struct PreferenceUpdate<Value: Encodable>: Encodable {
    let revision: String
    let preferences: Value
}

private struct PreferencesDraft {
    var preferences: Preferences
    var locations: String
    var remoteLocations: String
    var separateLocations: Bool
    var categories: String
    var exclusions: String
    var employerURLs: String
    var boards: [String: String]
    var skills: String
    var salaryFloor: String
    var aiLimit: String
    let revision: String

    init(_ dashboard: Dashboard) {
        let values = dashboard.preferences
        preferences = values
        remoteLocations = (values.remoteHiringLocations ?? []).joined(separator: "\n")
        separateLocations = values.remoteHiringLocations != nil
        locations = (values.targetLocations ?? []).joined(separator: "\n")
        categories = values.categories.joined(separator: "\n")
        exclusions = values.excludedTitleTerms.joined(separator: "\n")
        employerURLs = values.additionalEmployerUrls.joined(separator: "\n")
        boards = values.additionalBoards.mapValues { $0.joined(separator: "\n") }
        skills = values.skillGroups.map {
            "\($0.label) | \($0.points) | \($0.terms.joined(separator: ", "))"
        }.joined(separator: "\n")
        salaryFloor = String(values.salaryFloor)
        aiLimit = String(values.aiDailyLimit)
        revision = dashboard.preferencesRevision
    }

    func payload() throws -> PreferenceUpdate<Preferences> {
        guard let salary = Int(salaryFloor), (0...1_000_000).contains(salary) else {
            throw Validation("Enter a salary target between 0 and 1,000,000 USD.")
        }
        guard let limit = Int(aiLimit), (1...100).contains(limit) else {
            throw Validation("Enter a daily AI attempt limit from 1 to 100.")
        }
        guard (1...12_000).contains(preferences.profile.trimmingCharacters(in: .whitespacesAndNewlines).unicodeScalars.count) else {
            throw Validation("Enter a candidate profile between 1 and 12,000 characters.")
        }
        var result = preferences
        result.salaryFloor = salary
        result.aiDailyLimit = limit
        result.targetLocations = lines(locations)
        if separateLocations {
            result.remoteHiringLocations = lines(remoteLocations)
            result.legacyGeography = false
        }
        result.categories = lines(categories)
        result.excludedTitleTerms = lines(exclusions)
        result.additionalEmployerUrls = lines(employerURLs)
        result.additionalBoards = boards.mapValues(lines)
        result.skillGroups = try lines(skills).map { line in
            let parts = line.split(separator: "|", omittingEmptySubsequences: false)
                .map { $0.trimmingCharacters(in: .whitespaces) }
            guard parts.count == 3, let points = Int(parts[1]), (0...25).contains(points),
                  !parts[0].isEmpty else {
                throw Validation("Use Name | Weight (0–25) | comma-separated terms for each skill group.")
            }
            let terms = parts[2].split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }
                .filter { !$0.isEmpty }
            guard !terms.isEmpty else { throw Validation("Enter at least one term for each skill group.") }
            return SkillGroup(label: parts[0], points: points, terms: terms)
        }
        return PreferenceUpdate(revision: revision, preferences: result)
    }

    private func lines(_ text: String) -> [String] {
        text.split(whereSeparator: \.isNewline)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    private struct Validation: LocalizedError {
        let errorDescription: String?
        init(_ message: String) { errorDescription = message }
    }
}

struct PreferencesEditor: View {
    @Environment(\.dismiss) private var dismiss
    let workspace: Workspace
    @State private var draft: PreferencesDraft
    @State private var resume: ResumePreview?
    @State private var savedResume: ResumePreview?
    @State private var importingResume = false
    @State private var pickedResumeURL: URL?
    @State private var readingResume = false
    @State private var importError: String?

    let administration: Bool
    var onSaved: () -> Void

    init(workspace: Workspace, dashboard: Dashboard, administration: Bool = false, onSaved: @escaping () -> Void = {}) {
        self.workspace = workspace
        self.administration = administration
        self.onSaved = onSaved
        _draft = State(initialValue: PreferencesDraft(dashboard))
    }

    var body: some View {
        SaveForm(title: administration ? "Workspace Administration" : "Search Profile", workspace: workspace) {
            if !administration {
                Section("Résumé") {
                    Button(savedResume == nil ? "Import Résumé" : "Replace Résumé",
                           systemImage: "doc.badge.plus") { importingResume = true }
                        .disabled(readingResume)
                    if readingResume { ProgressView("Reading résumé…") }
                    if let savedResume {
                        Button(savedResume.name, systemImage: "doc.text") { resume = savedResume }
                        Button("Remove Résumé", role: .destructive) {
                            do {
                                try ResumePreview.remove()
                                self.savedResume = nil
                                importError = nil
                            } catch { importError = error.localizedDescription }
                        }
                    }
                    Text("Your file preview stays on this iPhone. Choose the skills and experience you want to save to your Mac’s search profile.")
                        .font(.footnote).foregroundStyle(.secondary)
                    if let importError { Text(importError).foregroundStyle(.red) }
                }
                Section("Candidate Profile") {
                    TextField("Experience and preferences", text: $draft.preferences.profile, axis: .vertical)
                        .lineLimit(4...10)
                }
                Section("Job Preferences") {
                    ProfileTermsLink(title: "Target Roles", prompt: "Add a job title", terms: $draft.categories)
                    ProfileTermsLink(title: "Titles to Avoid", prompt: "Add a title or phrase", terms: $draft.exclusions)
                    SkillPickerLink(selection: Binding(
                        get: { draft.preferences.preferredSkills ?? [] },
                        set: { draft.preferences.preferredSkills = $0 }
                    ))
                }
                Section("Where you want to work") {
                    if draft.preferences.remoteHiringLocations == nil {
                        Toggle("Separate commute and remote locations", isOn: $draft.separateLocations)
                    }
                    if draft.separateLocations {
                        ProfileTermsLink(title: "Commute Locations", prompt: "City, state or region", terms: $draft.locations)
                        ProfileTermsLink(title: "Remote Hiring Regions", prompt: "State or country", terms: $draft.remoteLocations)
                    } else {
                        ProfileTermsLink(title: "Locations", prompt: "City, state, or country",
                                         terms: $draft.locations, emptySummary: "Workspace defaults")
                    }
                    NavigationLink {
                        Form {
                            Section("Work arrangements you’d consider") {
                                workplace("Remote", "remote")
                                workplace("Hybrid", "hybrid")
                                workplace("On-site", "onsite")
                            }
                        }
                        .scrollContentBackground(.hidden)
                        .background(JobsTheme.canvas.ignoresSafeArea())
                        .navigationTitle("Work Arrangement")
                    } label: {
                        LabeledContent("Work Arrangement", value: workArrangementSummary)
                    }
                }
                Section("Salary") {
                    Menu("Choose a Salary Target") {
                        ForEach([50_000, 70_000, 85_000, 100_000, 125_000, 150_000], id: \.self) { salary in
                            Button {
                                draft.salaryFloor = String(salary)
                            } label: {
                                Text(salary, format: .currency(code: "USD").precision(.fractionLength(0)))
                            }
                        }
                    }
                    TextField("Annual Target in USD", text: $draft.salaryFloor).keyboardType(.numberPad)
                    Picker("Policy", selection: $draft.preferences.salaryPolicy) {
                        Text("Range Reaches Target").tag("overlap")
                        Text("Entire Range Meets Target").tag("minimum")
                    }
                }
            } else {
                Section("Matching Rules") {
                    multiline("Excluded title terms, one per line", $draft.exclusions)
                    multiline("Skill groups: Name | Weight | term, term", $draft.skills)
                }
                Section("Employer Sources") {
                    boardField("Ashby", "ashby")
                    boardField("Greenhouse", "greenhouse")
                    boardField("Lever", "lever")
                    boardField("SmartRecruiters", "smartrecruiters")
                    boardField("Personio", "personio")
                    boardField("Recruitee", "recruitee")
                    multiline("Employer posting URLs, one per line", $draft.employerURLs)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                }
                Section("Schedule") {
                    Toggle("Daily Employer Search", isOn: $draft.preferences.scheduleEnabled)
                    Picker("UTC Hour", selection: $draft.preferences.scheduleHourUtc) {
                        ForEach(0..<24) { Text("\($0):00").tag($0) }
                    }
                }
                Section {
                    Toggle("Enable Requested Career Reviews", isOn: $draft.preferences.aiEnabled)
                    TextField("OpenAI Model", text: $draft.preferences.aiModel)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                    TextField("Daily Attempt Limit", text: $draft.aiLimit).keyboardType(.numberPad)
                } header: {
                    Text("AI Career Advice")
                } footer: {
                    Text("Store the API key on the Mac. Reviews are requested individually from a job’s detail screen.")
                }
            }
        } save: {
            try await workspace.save("/api/preferences", draft.payload())
            dismiss()
            onSaved()
        } reload: {
            if let dashboard = workspace.dashboard { draft = PreferencesDraft(dashboard) }
        }
        .task { savedResume = try? ResumePreview.load() }
        .fileImporter(isPresented: $importingResume, allowedContentTypes: [.pdf, .plainText]) { result in
            switch result {
            case .success(let url):
                importError = nil
                pickedResumeURL = url
            case .failure(let error as CocoaError) where error.code == .userCancelled:
                break
            case .failure(let error):
                importError = error.localizedDescription
            }
        }
        .task(id: pickedResumeURL) {
            if let url = pickedResumeURL { await importResume(url) }
        }
        .sheet(item: $resume) { preview in
            ResumeReview(preview: preview, currentProfile: draft.preferences.profile) { skills, profile in
                for skill in skills { setSkill(skill, enabled: true) }
                draft.preferences.profile = profile
            }
        }
    }

    private func importResume(_ url: URL) async {
        readingResume = true
        defer {
            readingResume = false
            pickedResumeURL = nil
        }
        do {
            let imported = try await Task.detached(priority: .userInitiated) { try ResumePreview.read(url) }.value
            try Task.checkCancellation()
            try imported.save()
            savedResume = imported
            resume = imported
        } catch is CancellationError {
            return
        } catch {
            importError = error.localizedDescription
        }
    }

    private func setSkill(_ skill: String, enabled: Bool) {
        var skills = draft.preferences.preferredSkills ?? []
        skills.removeAll { $0.caseInsensitiveCompare(skill) == .orderedSame }
        if enabled && skills.count < 150 { skills.append(skill) }
        draft.preferences.preferredSkills = skills
    }

    private var workArrangementSummary: String {
        let modes = draft.preferences.workplaceTypes ?? []
        let labels = [("remote", "Remote"), ("hybrid", "Hybrid"), ("onsite", "On-site")]
            .filter { modes.contains($0.0) }
            .map { $0.1 }
        return labels.isEmpty ? "Workspace defaults" : labels.joined(separator: ", ")
    }

    private func workplace(_ title: String, _ key: String) -> some View {
        Toggle(title, isOn: Binding(
            get: { (draft.preferences.workplaceTypes ?? []).contains(key) },
            set: { enabled in
                var modes = Set(draft.preferences.workplaceTypes ?? [])
                if enabled { modes.insert(key) } else { modes.remove(key) }
                draft.preferences.workplaceTypes = modes.sorted()
            }
        ))
    }

    private func boardField(_ name: String, _ platform: String) -> some View {
        multiline("\(name) board slugs, one per line", Binding(
            get: { draft.boards[platform, default: ""] },
            set: { draft.boards[platform] = $0 }
        ))
        .textInputAutocapitalization(.never).autocorrectionDisabled()
    }

    private func multiline(_ label: String, _ value: Binding<String>) -> some View {
        VStack(alignment: .leading) {
            Text(label).font(.footnote).foregroundStyle(.secondary)
            TextField(label, text: value, axis: .vertical).lineLimit(2...7)
        }
    }
}

private struct ResumePreview: Identifiable, Codable {
    var id: String { name }
    let name: String
    let text: String
    let skills: [String]

    private static func storageURL() throws -> URL {
        var folder = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                                appropriateFor: nil, create: true)
            .appendingPathComponent("LocalResume", isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try folder.setResourceValues(values)
        return folder.appendingPathComponent("resume.json")
    }

    static func load() throws -> Self {
        try JSONDecoder().decode(Self.self, from: Data(contentsOf: storageURL()))
    }

    func save() throws {
        try JSONEncoder().encode(self).write(to: Self.storageURL(), options: [.atomic, .completeFileProtection])
    }

    static func remove() throws {
        try FileManager.default.removeItem(at: storageURL())
    }

    static func read(_ url: URL) throws -> Self {
        let accessed = url.startAccessingSecurityScopedResource()
        defer { if accessed { url.stopAccessingSecurityScopedResource() } }
        let properties = try url.resourceValues(forKeys: [.fileSizeKey, .contentTypeKey])
        guard let size = properties.fileSize, size <= 10_000_000 else { throw ImportError("Choose a file smaller than 10 MB.") }
        let text: String
        if properties.contentType?.conforms(to: .pdf) == true || url.pathExtension.lowercased() == "pdf" {
            text = PDFDocument(url: url)?.string ?? ""
        } else {
            text = try String(contentsOf: url, encoding: .utf8)
        }
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw ImportError("No selectable text was found. Export a text-based PDF or a plain text résumé.")
        }
        let searchable = text.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
        let skills = SkillCatalog.all.filter { skill in
            let phrase = NSRegularExpression.escapedPattern(for: skill)
            return searchable.range(of: #"(?<![\p{L}\p{N}+#])"# + phrase + #"(?![\p{L}\p{N}+#])"#,
                                    options: [.regularExpression, .caseInsensitive]) != nil
        }
        return Self(name: url.lastPathComponent, text: String(text.prefix(16_000)), skills: skills)
    }

    private struct ImportError: LocalizedError {
        let errorDescription: String?
        init(_ message: String) { errorDescription = message }
    }
}

private struct ResumeReview: View {
    @Environment(\.dismiss) private var dismiss
    let preview: ResumePreview
    let currentProfile: String
    let add: ([String], String) -> Void
    @State private var selected: Set<String> = []
    @State private var experience = ""

    private var combinedProfile: String {
        let addition = experience.trimmingCharacters(in: .whitespacesAndNewlines)
        let current = currentProfile.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !addition.isEmpty, !current.contains(addition) else { return currentProfile }
        return [current, addition].filter { !$0.isEmpty }.joined(separator: "\n\n")
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Suggested Skills") {
                    if preview.skills.isEmpty {
                        Text("No skills from the built-in list were found. You can add custom skills in Preferences.")
                    }
                    ForEach(preview.skills, id: \.self) { skill in
                        Button {
                            if selected.remove(skill) == nil { selected.insert(skill) }
                        } label: {
                            HStack {
                                Text(skill)
                                Spacer()
                                Image(systemName: selected.contains(skill) ? "checkmark.circle.fill" : "circle")
                                    .foregroundStyle(selected.contains(skill) ? JobsTheme.accent : .secondary)
                                    .accessibilityHidden(true)
                            }
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityAddTraits(selected.contains(skill) ? .isSelected : [])
                    }
                }
                Section {
                    TextField("Experience to add", text: $experience, axis: .vertical)
                        .lineLimit(3...8)
                    if combinedProfile.unicodeScalars.count > 12_000 {
                        Text("Shorten the experience to fit your 12,000-character profile.").foregroundStyle(.red)
                    }
                } header: {
                    Text("Experience for Matching")
                } footer: {
                    Text("Copy a relevant passage from the preview or describe work you’ve done. This text is added to your profile draft. Save the profile to use it for matching.")
                }
                Section(preview.name) {
                    Text(preview.text).textSelection(.enabled)
                }
            }
            .navigationTitle("Review Résumé")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Use in Profile") {
                        add(preview.skills.filter { selected.contains($0) }, combinedProfile)
                        dismiss()
                    }
                    .disabled((selected.isEmpty && combinedProfile == currentProfile) || combinedProfile.unicodeScalars.count > 12_000)
                }
            }
        }
    }
}

private struct SearchChange: Encodable {
    let action: String
    var id: Int?
    var version: Int?
    var criteria: SearchCriteria?
    var through: Int?
}

private struct SearchCriteria: Encodable {
    var name: String
    var skills: [String]
    var titleTerms: [String]
    var locations: [String]
    var workplaceTypes: [String]
    var salaryMin: Int
    var salaryMax: Int?
    var enabled: Bool
}

private struct SavedSearchesScreen: View {
    let workspace: Workspace
    @State private var creating = false
    @State private var editing: SavedSearch?

    var body: some View {
        List {
            Section {
                Button("New Saved Search", systemImage: "plus") { creating = true }
                ForEach(workspace.dashboard?.savedSearches ?? []) { search in
                    Button {
                        editing = search
                    } label: {
                        VStack(alignment: .leading, spacing: 5) {
                            Text(search.name).font(.headline).foregroundStyle(.primary)
                            Text(search.locations.joined(separator: ", ")).foregroundStyle(.primary)
                            Text(search.enabled ? "Alerts on" : "Alerts paused").foregroundStyle(.secondary)
                        }
                    }
                }
            } footer: {
                Text("New listings can match more than one saved search. Run a search now or enable daily searches in Preferences.")
            }
        }
        .navigationTitle("Saved Searches")
        .sheet(isPresented: $creating) {
            SavedSearchEditor(workspace: workspace, search: nil)
        }
        .sheet(item: $editing) { search in
            SavedSearchEditor(workspace: workspace, search: search)
        }
    }
}

private struct SavedSearchEditor: View {
    @Environment(\.dismiss) private var dismiss
    let workspace: Workspace
    @State private var search: SavedSearch?
    @State private var criteria: SearchCriteria
    @State private var skills: String
    @State private var titleTerms: String
    @State private var locations: String
    @State private var minimum: String
    @State private var maximum: String
    @State private var showingProfilePreview = false
    @State private var confirmingDelete = false
    @State private var deleteError: String?

    init(workspace: Workspace, search: SavedSearch?) {
        self.workspace = workspace
        let preferences = workspace.dashboard?.preferences
        let criteria = SearchCriteria(
            name: search?.name ?? "",
            skills: search?.skills ?? preferences?.preferredSkills ?? [],
            titleTerms: search?.titleTerms ?? [],
            locations: search?.locations ?? preferences?.targetLocations ?? [],
            workplaceTypes: search?.workplaceTypes ?? preferences?.workplaceTypes ?? [],
            salaryMin: search?.salaryMin ?? preferences?.salaryFloor ?? 0,
            salaryMax: search?.salaryMax,
            enabled: search?.enabled ?? true
        )
        _search = State(initialValue: search)
        _criteria = State(initialValue: criteria)
        _skills = State(initialValue: criteria.skills.joined(separator: "\n"))
        _titleTerms = State(initialValue: criteria.titleTerms.joined(separator: "\n"))
        _locations = State(initialValue: criteria.locations.joined(separator: "\n"))
        _minimum = State(initialValue: String(criteria.salaryMin))
        _maximum = State(initialValue: criteria.salaryMax.map(String.init) ?? "")
    }

    var body: some View {
        SaveForm(title: search == nil ? "New Saved Search" : "Edit Saved Search", workspace: workspace) {
            if search != nil, let profile = workspace.dashboard?.preferences {
                Section("Search Profile") {
                    Button("Preview Profile Changes", systemImage: "person.crop.circle") {
                        showingProfilePreview = true
                    }
                    .sheet(isPresented: $showingProfilePreview) {
                        NavigationStack {
                            List {
                                profileChange("Title phrases", from: titleTerms, to: profile.categories.prefix(30).joined(separator: ", "))
                                if let values = profile.preferredSkills, !values.isEmpty {
                                    profileChange("Skills", from: skills, to: values.prefix(30).joined(separator: ", "))
                                }
                                if let values = profile.targetLocations, !values.isEmpty {
                                    profileChange("Locations", from: locations, to: values.joined(separator: ", "))
                                }
                                if let values = profile.workplaceTypes, !values.isEmpty {
                                    profileChange("Work settings", from: criteria.workplaceTypes.joined(separator: ", "), to: values.joined(separator: ", "))
                                }
                                profileChange("Minimum annual USD", from: minimum, to: String(profile.salaryFloor))
                            }
                            .navigationTitle("Profile Changes")
                            .toolbar {
                                ToolbarItem(placement: .cancellationAction) {
                                    Button("Cancel") { showingProfilePreview = false }
                                }
                                ToolbarItem(placement: .confirmationAction) {
                                    Button("Use in Draft") {
                                        titleTerms = profile.categories.prefix(30).joined(separator: "\n")
                                        if let values = profile.preferredSkills, !values.isEmpty {
                                            skills = values.prefix(30).joined(separator: "\n")
                                        }
                                        if let values = profile.targetLocations, !values.isEmpty {
                                            locations = values.joined(separator: "\n")
                                        }
                                        if let values = profile.workplaceTypes, !values.isEmpty {
                                            criteria.workplaceTypes = values
                                        }
                                        minimum = String(profile.salaryFloor)
                                        showingProfilePreview = false
                                    }
                                }
                            }
                        }
                    }
                }
            }
            Section("Search") {
                TextField("Name", text: $criteria.name)
                TextField("Required title phrases, one per line (optional)", text: $titleTerms, axis: .vertical).lineLimit(2...6)
                SkillPickerLink(selection: Binding(
                    get: { skills.components(separatedBy: .newlines).filter { !$0.isEmpty } },
                    set: { skills = $0.joined(separator: "\n") }
                ), limit: 30)
                TextField("Locations, one per line", text: $locations, axis: .vertical).lineLimit(2...6)
                mode("Remote", "remote")
                mode("Hybrid", "hybrid")
                mode("On-site", "onsite")
            }
            Section {
                TextField("Minimum USD", text: $minimum).keyboardType(.numberPad)
                TextField("Maximum USD (optional)", text: $maximum).keyboardType(.numberPad)
            } header: {
                Text("Annual Base Salary")
            } footer: {
                Text("A new job must match at least one skill and location, and its published annual USD base pay must overlap your range.")
            }
            Section("Alerts") {
                Toggle("Alert Me About New Matches", isOn: $criteria.enabled)
                if search != nil {
                    Button("Delete Saved Search", role: .destructive) { confirmingDelete = true }
                }
                if let deleteError { Text(deleteError).foregroundStyle(.red) }
            }
            .confirmationDialog("Delete Search and Its Alerts?", isPresented: $confirmingDelete) {
                Button("Delete", role: .destructive) { Task { await deleteSearch() } }
            }
        } save: {
            guard let low = Int(minimum), maximum.isEmpty || Int(maximum) != nil else {
                throw DashboardAPI.ServerError(status: 400, message: "Enter salary amounts as whole numbers.")
            }
            var payload = criteria
            payload.salaryMin = low
            payload.salaryMax = Int(maximum)
            payload.skills = searchLines(skills)
            payload.titleTerms = searchLines(titleTerms)
            payload.locations = searchLines(locations)
            try await workspace.save("/api/saved-searches", SearchChange(action: "save", id: search?.id,
                                                                        version: search?.version, criteria: payload))
            dismiss()
        } reload: {
            guard let id = search?.id else { return }
            guard let current = workspace.dashboard?.savedSearches?.first(where: { $0.id == id }) else {
                dismiss()
                return
            }
            search = current
            criteria.name = current.name
            criteria.workplaceTypes = current.workplaceTypes
            criteria.enabled = current.enabled
            titleTerms = (current.titleTerms ?? []).joined(separator: "\n")
            skills = current.skills.joined(separator: "\n")
            locations = current.locations.joined(separator: "\n")
            minimum = String(current.salaryMin)
            maximum = current.salaryMax.map(String.init) ?? ""
        }
    }

    private func profileChange(_ title: String, from current: String, to proposed: String) -> some View {
        Section(title) {
            LabeledContent("Current", value: current.replacingOccurrences(of: "\n", with: ", "))
            LabeledContent("Proposed", value: proposed)
        }
    }

    private func deleteSearch() async {
        guard let search else { return }
        do {
            try await workspace.save("/api/saved-searches",
                                     SearchChange(action: "delete", id: search.id, version: search.version))
            dismiss()
        } catch {
            deleteError = error.localizedDescription
        }
    }

    private func searchLines(_ text: String) -> [String] {
        text.split(whereSeparator: \.isNewline).map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
    }

    private func mode(_ title: String, _ key: String) -> some View {
        Toggle(title, isOn: Binding(
            get: { criteria.workplaceTypes.contains(key) },
            set: { enabled in
                if enabled { criteria.workplaceTypes.append(key) }
                else { criteria.workplaceTypes.removeAll { $0 == key } }
            }
        ))
    }
}

private struct MatchInbox: View {
    let workspace: Workspace
    @State private var message: String?

    var body: some View {
        let alerts = workspace.dashboard?.matchAlerts ?? []
        let jobs = Dictionary(uniqueKeysWithValues: (workspace.dashboard?.jobs ?? []).map { ($0.id, $0) })
        List {
            Section {
                Button("Enable iPhone Notifications", systemImage: "bell") {
                    Task {
                        do {
                            let granted = try await UNUserNotificationCenter.current()
                                .requestAuthorization(options: [.alert, .badge, .sound])
                            message = granted ? "Notifications enabled." : "Allow notifications in iPhone Settings."
                            if granted { await workspace.refresh() }
                        } catch { message = error.localizedDescription }
                    }
                }
                if let message { Text(message).foregroundStyle(.secondary) }
            } footer: {
                Text("The Mac records matches while the app is closed. The iPhone can notify you after syncing when a match is still current.")
            }
            Section("Recent Matches") {
                if alerts.isEmpty { Text("No matching jobs yet.").foregroundStyle(.secondary) }
                ForEach(alerts) { alert in
                    NavigationLink {
                        JobDetail(workspace: workspace, jobID: alert.jobId)
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(alert.searchName).font(.subheadline).foregroundStyle(.tint)
                            Text(jobs[alert.jobId]?.title ?? "Job unavailable")
                                .fontWeight(alert.unread ? .bold : .regular)
                            Text(alert.state(for: jobs[alert.jobId]).label)
                                .font(.caption).foregroundStyle(.secondary)
                            Text(displayTimestamp(alert.created)).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .navigationTitle("Match Alerts")
        .toolbar {
            if let latest = alerts.first, workspace.dashboard?.unreadMatchCount ?? 0 > 0 {
                Button("Mark All Read") {
                    Task {
                        do {
                            try await workspace.save("/api/saved-searches",
                                                     SearchChange(action: "read", through: latest.id))
                        } catch { message = error.localizedDescription }
                    }
                }
                .disabled(workspace.saving)
            }
        }
        .refreshable { await workspace.refresh() }
    }
}

@MainActor
enum MatchNotifications {
    static func deliver(for workspace: Workspace) async {
        guard workspace.dashboard?.matchAlerts?.isEmpty == false else { return }
        let server = workspace.address
        let center = UNUserNotificationCenter.current()
        let status = await center.notificationSettings().authorizationStatus
        guard status == .authorized || status == .provisional else { return }
        guard workspace.connected, workspace.address == server, let dashboard = workspace.dashboard,
              let alerts = dashboard.matchAlerts, let oldestID = alerts.map(\.id).min()
        else { return }

        let defaults = UserDefaults.standard
        let key = "notifiedMatchAlerts:" + server
        let legacyCursor = defaults.integer(forKey: "lastMatchAlert:" + server)
        let claimed = Set((defaults.array(forKey: key) as? [Int] ?? []).filter { $0 >= oldestID })
        let jobs = Dictionary(uniqueKeysWithValues: dashboard.jobs.map { ($0.id, $0) })
        let fresh = alerts.filter {
            $0.unread && $0.id > legacyCursor && !claimed.contains($0.id)
                && $0.state(for: jobs[$0.jobId]) == .current
        }
        guard let newest = fresh.max(by: { $0.id < $1.id }) else { return }
        let ids = Set(fresh.map(\.id))
        let content = UNMutableNotificationContent()
        content.title = fresh.count == 1 ? "New match for \(newest.searchName)" : "New job matches"
        content.body = fresh.count == 1 ? "Open Match Alerts to review the listing."
            : "\(fresh.count) new matches for your saved searches."
        content.sound = .default
        let request = UNNotificationRequest(identifier: key + ":\(newest.id)", content: content, trigger: nil)
        defaults.set(Array(claimed.union(ids)), forKey: key)
        do { try await center.add(request) }
        catch {
            let latest = Set(defaults.array(forKey: key) as? [Int] ?? [])
            defaults.set(Array(latest.subtracting(ids)), forKey: key)
        }
    }
}

final class NotificationsDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                willPresent notification: UNNotification) async -> UNNotificationPresentationOptions {
        [.banner, .list, .sound]
    }
}

enum SkillCatalog {
    static let groups: [(name: String, skills: [String])] = [
        ("Finance and accounting", "Accounting|Accounts Payable|Accounts Receivable|Audit|Billing Operations|Bookkeeping|Budgeting|Cash Applications|Cash Flow Forecasting|Collections|Cost Accounting|Credit Analysis|Expense Management|Financial Modeling|Financial Reporting|Financial Planning and Analysis|General Ledger|Internal Controls|Invoicing|Month-End Close|NetSuite|Payroll|QuickBooks|Reconciliation|Revenue Operations|Revenue Recognition|SOX Compliance|Tax Preparation|Variance Analysis"),
        ("Data and analytics", "A/B Testing|Data Analysis|Data Engineering|Data Governance|Data Modeling|Data Quality|Data Visualization|dbt|Excel|Forecasting|Google Analytics|Google Sheets|Looker|Machine Learning|Power BI|Power Query|Python|R|Reporting|SAS|Snowflake|SQL|Statistics|Tableau"),
        ("Software and IT", "Accessibility|Android|Angular|API Integration|AWS|Azure|Bash|C|C#|C++|CI/CD|Cloud Computing|Cybersecurity|Docker|Git|Go|HTML|iOS|Java|JavaScript|Kotlin|Kubernetes|Linux|Network Administration|Node.js|PHP|PostgreSQL|React|Ruby|Rust|Software Testing|Swift|SwiftUI|Technical Support|Terraform|TypeScript|Windows Administration"),
        ("Sales and customer service", "Account Management|Business Development|Client Onboarding|CRM|Customer Service|Customer Success|Dispute Resolution|Escalation Management|HubSpot|Lead Generation|Negotiation|Point of Sale|Prospecting|Sales Operations|Salesforce|Solution Selling|Stripe|Zendesk|Zuora"),
        ("Operations and management", "Agile|Business Analysis|Change Management|Contract Management|Cross-Functional Collaboration|Inventory Management|Jira|Leadership|Lean|Logistics|Operations Management|Process Improvement|Procurement|Project Management|Quality Assurance|Risk Management|Scrum|Six Sigma|Supply Chain Management|Vendor Management|Workflow Documentation"),
        ("Design and marketing", "Adobe Illustrator|Adobe Photoshop|Brand Strategy|Content Strategy|Copywriting|Email Marketing|Figma|Graphic Design|Market Research|Paid Search|Product Design|SEO|Social Media Marketing|Typography|UI Design|User Research|UX Design|Video Editing|WordPress"),
        ("Healthcare and science", "Clinical Documentation|Clinical Research|Data Collection|Electronic Health Records|HIPAA Compliance|Laboratory Safety|Medical Billing|Medical Coding|Microscopy|Patient Scheduling|Phlebotomy|Public Health|Quality Control|Research Methods|Sample Preparation|Sterile Technique"),
        ("Education and people", "Career Coaching|Conflict Resolution|Curriculum Development|Employee Relations|Facilitation|Human Resources|Instructional Design|Interviewing|Learning Management Systems|Onboarding|Performance Management|Recruiting|Teaching|Training and Development|Workforce Planning"),
        ("Product and delivery", "Acceptance Criteria|Backlog Management|Competitive Analysis|Customer Discovery|Feature Prioritization|Go-to-Market Strategy|Kanban|Product Analytics|Product Management|Product Roadmaps|Release Management|Requirements Gathering|Service Design|Stakeholder Management|Technical Writing|User Stories|Usability Testing"),
        ("Manufacturing and engineering", "AutoCAD|CAD|Calibration|CNC Machining|Control Systems|Design for Manufacturing|Failure Analysis|GD&T|Industrial Engineering|Lean Manufacturing|Material Handling|MATLAB|Mechanical Design|PLC Programming|Root Cause Analysis|SolidWorks|Statistical Process Control|Troubleshooting"),
        ("Legal and public service", "Case Management|Compliance Monitoring|Contract Drafting|Document Review|E-Discovery|Grant Administration|Legal Research|Legislative Research|Paralegal Support|Policy Analysis|Program Evaluation|Public Administration|Records Management|Regulatory Reporting|Technical Compliance"),
        ("Hospitality and retail", "Cash Handling|Catering|Event Planning|Food Preparation|Food Safety|Front Desk Operations|Guest Relations|Housekeeping|Loss Prevention|Merchandising|Reservations|Retail Operations|Shift Scheduling|Visual Merchandising|Wine Service"),
        ("Media and communications", "Broadcast Production|Community Management|Editing|Internal Communications|Interview Production|Journalism|Media Relations|Motion Graphics|Photography|Podcast Production|Presentation Design|Proofreading|Public Relations|Speechwriting|Storyboarding|Translation"),
        ("Transportation and facilities", "Building Automation|Commercial Driving|Dispatching|Fleet Management|Freight Forwarding|Hazardous Materials Handling|Janitorial Services|Landscape Maintenance|Route Planning|Shipping and Receiving|Warehouse Operations|Work Order Management"),
        ("Research and sustainability", "Environmental Compliance|Environmental Impact Assessment|Field Research|GIS|Grant Writing|Literature Review|Monitoring and Evaluation|Qualitative Research|Quantitative Research|Sampling|Scientific Writing|Sustainability Reporting|Survey Design"),
        ("Trades and field work", "Blueprint Reading|Carpentry|Construction Management|Electrical Troubleshooting|Equipment Maintenance|Forklift Operation|HVAC|OSHA Compliance|Plumbing|Preventive Maintenance|Safety Inspections|Site Supervision|Technical Drawing|Welding")
    ].map { (name: $0.0, skills: $0.1.components(separatedBy: "|").sorted()) }

    static var all: [String] { groups.flatMap(\.skills) }
}

struct SkillPickerLink: View {
    @Binding var selection: [String]
    var limit = 150

    var body: some View {
        NavigationLink {
            SkillPicker(selection: $selection, limit: limit)
        } label: {
            LabeledContent("Choose skills", value: "\(selection.count) selected")
        }
    }
}

private struct SkillPicker: View {
    @Binding var selection: [String]
    let limit: Int
    @State private var query = ""
    @State private var category: String?
    @State private var custom = ""
    @State private var showingCustom = false

    private var term: String { query.trimmingCharacters(in: .whitespacesAndNewlines) }

    var body: some View {
        List {
            if selection.count >= limit {
                Text("You’ve selected the maximum of \(limit) skills. Remove one to add another.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            if term.isEmpty && category == nil {
                if !selection.isEmpty {
                    Section("Selected") { ForEach(selection, id: \.self) { skillRow($0) } }
                }
                Section("Browse categories") {
                    ForEach(SkillCatalog.groups, id: \.name) { group in
                        Button { category = group.name } label: {
                            LabeledContent(group.name, value: String(group.skills.count))
                        }
                    }
                }
            } else {
                if category != nil {
                    Button("All categories", systemImage: "arrow.uturn.backward") { self.category = nil }
                }
                let matches = (category == nil ? SkillCatalog.all
                    : SkillCatalog.groups.first { $0.name == category }?.skills ?? [])
                    .filter { term.isEmpty || $0.localizedCaseInsensitiveContains(term) }
                if matches.isEmpty {
                    ContentUnavailableView.search(text: term)
                } else {
                    Section(category ?? "Search results") {
                        ForEach(matches, id: \.self) { skillRow($0) }
                    }
                }
            }
        }
        .navigationTitle("Skills")
        .searchable(text: $query, prompt: "Search skills")
        .toolbar {
            Button("Add custom skill", systemImage: "plus") {
                custom = term
                showingCustom = true
            }
            .disabled(selection.count >= limit)
        }
        .alert("Add custom skill", isPresented: $showingCustom) {
            TextField("Skill name", text: $custom)
            Button("Cancel", role: .cancel) {}
            Button("Add") {
                let name = String(custom.trimmingCharacters(in: .whitespacesAndNewlines).prefix(80))
                if !name.isEmpty && !contains(name) && selection.count < limit { selection.append(name) }
            }
        }
    }

    private func contains(_ skill: String) -> Bool {
        selection.contains { $0.caseInsensitiveCompare(skill) == .orderedSame }
    }

    private func skillRow(_ skill: String) -> some View {
        let selected = contains(skill)
        return Button {
            if selected {
                selection.removeAll { $0.caseInsensitiveCompare(skill) == .orderedSame }
            } else if selection.count < limit {
                selection.append(skill)
            }
        } label: {
            HStack {
                Text(skill).foregroundStyle(.primary)
                Spacer()
                if selected { Image(systemName: "checkmark.circle.fill").foregroundStyle(JobsTheme.accent) }
            }
            .contentShape(Rectangle())
        }
        .disabled(!selected && selection.count >= limit)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

struct SampleProfileEditor: View {
    @Environment(\.dismiss) private var dismiss
    let workspace: Workspace
    @State private var skills: [String]
    @State private var salaryFloor: Int

    init(workspace: Workspace) {
        self.workspace = workspace
        _skills = State(initialValue: workspace.dashboard?.preferences.preferredSkills ?? [])
        _salaryFloor = State(initialValue: workspace.dashboard?.preferences.salaryFloor ?? 0)
    }

    var body: some View {
        SaveForm(title: "Sample Search Profile", workspace: workspace) {
            Section {
                SkillPickerLink(selection: $skills)
                Picker("Annual base pay", selection: $salaryFloor) {
                    Text("Any salary").tag(0)
                    ForEach([50_000, 70_000, 90_000, 110_000, 130_000], id: \.self) { floor in
                        Text(floor, format: .currency(code: "USD").precision(.fractionLength(0))).tag(floor)
                    }
                }
            } header: {
                Text("What you want to match")
            } footer: {
                Text("For You uses your selected skills and pay target. Browse shows every fictional listing.")
            }
        } save: {
            try workspace.updateSampleProfile(skills: skills, salaryFloor: salaryFloor)
            dismiss()
        } reload: {
            skills = workspace.dashboard?.preferences.preferredSkills ?? []
            salaryFloor = workspace.dashboard?.preferences.salaryFloor ?? 0
        }
    }
}


struct ApplicationPrepSheet: View {
    @Environment(\.dismiss) private var dismiss
    let job: Job
    let address: String

    @State private var prep: ApplicationPrep?
    @State private var draft = ""
    @State private var savedDraft = ""
    @State private var version = 0
    @State private var updated: String?
    @State private var loading = false
    @State private var saving = false
    @State private var error: String?
    @State private var conflict = false
    @State private var confirmingReload = false
    @State private var confirmingClose = false

    private var dirty: Bool { draft != savedDraft }

    var body: some View {
        NavigationStack {
            Form {
                if let error {
                    Section {
                        Text(error).foregroundStyle(.secondary)
                        if prep == nil {
                            Button("Try Again") { Task { await load() } }.disabled(loading)
                        } else if conflict {
                            Button("Reload Saved Draft") { confirmingReload = true }.disabled(loading || saving)
                        }
                    }
                }
                if let prep {
                    Section {
                        Text(job.title).font(.headline)
                        Text(job.employer).foregroundStyle(.secondary)
                    }
                    Section("Examples from Your Profile") {
                        if prep.examples.isEmpty {
                            Text(emptyExamples(prep)).foregroundStyle(.secondary)
                        }
                        ForEach(prep.examples, id: \.skill) { example in
                            VStack(alignment: .leading, spacing: 6) {
                                Text(example.skill).font(.headline)
                                Text("Employer duty").font(.caption).foregroundStyle(.secondary)
                                Text(example.duty).textSelection(.enabled)
                                Text("Your profile excerpt").font(.caption).foregroundStyle(.secondary)
                                Text(example.profileExcerpt).textSelection(.enabled)
                                Button("Add \(example.skill) excerpt", systemImage: "plus") {
                                    if !draft.split(separator: "\n").contains(Substring(example.profileExcerpt)) {
                                        draft += (draft.isEmpty || draft.hasSuffix("\n") ? "" : "\n") + example.profileExcerpt
                                    }
                                }
                                .buttonStyle(.borderless)
                                .disabled(saving || loading)
                            }
                        }
                    }
                    if !prep.skillsToDocument.isEmpty || !prep.qualificationChecks.isEmpty {
                        Section("What to Check") {
                            ForEach(prep.skillsToDocument, id: \.self) { skill in
                                Text("Add an example of \(skill) if you’ve used it in your work.")
                            }
                            ForEach(prep.qualificationChecks, id: \.self) { Text($0) }
                        }
                    }
                    Section {
                        TextEditor(text: $draft)
                            .frame(minHeight: 140)
                            .accessibilityLabel("Your draft")
                            .accessibilityIdentifier("applicationPrepDraft")
                            .disabled(saving || loading)
                        if draft.unicodeScalars.count > 8000 {
                            Text("Keep the draft within 8,000 characters.").foregroundStyle(.red)
                        }
                        if let updated {
                            Text("Saved \(displayTimestamp(updated))")
                                .font(.footnote).foregroundStyle(.secondary)
                                .accessibilityIdentifier("applicationDraftSaved")
                        }
                    } header: {
                        Text("Your Draft")
                    } footer: {
                        Text("Edit the excerpts and add your own examples before using this draft.")
                    }
                } else if loading || error == nil {
                    ProgressView("Loading application prep…")
                }
            }
            .navigationTitle("Application Prep")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") {
                        if dirty { confirmingClose = true } else { dismiss() }
                    }
                    .disabled(saving || loading)
                }
                ToolbarItem(placement: .confirmationAction) {
                    if saving { ProgressView() }
                    else {
                        Button("Save Draft") { Task { await save() } }
                            .disabled(prep == nil || !dirty || conflict || loading || draft.unicodeScalars.count > 8000)
                    }
                }
            }
            .confirmationDialog("Replace Your Edits With the Saved Draft?", isPresented: $confirmingReload) {
                Button("Reload Saved Draft", role: .destructive) { Task { await load() } }
            }
            .confirmationDialog("Close Without Saving?", isPresented: $confirmingClose) {
                Button("Discard Edits", role: .destructive) { dismiss() }
            }
            .interactiveDismissDisabled(dirty || saving)
            .task { await load() }
        }
    }

    private func emptyExamples(_ prep: ApplicationPrep) -> String {
        if !prep.hasProfile { return "Add examples of your work to Search Profile to compare them with this posting." }
        if !prep.hasDescription { return "Jobs has no employer description for this listing. Check the posting before drafting." }
        return "Jobs found no matching work examples in your profile. You can still write a draft."
    }

    private func load() async {
        guard !loading else { return }
        loading = true
        error = nil
        defer { loading = false }
        do {
            let loaded = try await DashboardAPI.applicationPrep(jobID: job.id, at: address)
            prep = loaded
            draft = loaded.draft
            savedDraft = loaded.draft
            version = loaded.version
            updated = loaded.updated
            conflict = false
        } catch {
            self.error = DashboardAPI.connectionMessage(for: error)
        }
    }

    private func save() async {
        guard !saving, !conflict else { return }
        saving = true
        error = nil
        defer { saving = false }
        do {
            let saved = try await DashboardAPI.saveApplicationDraft(jobID: job.id, draft: draft,
                                                                    version: version, at: address)
            savedDraft = saved.draft
            version = saved.version
            updated = saved.updated
        } catch {
            conflict = (error as? DashboardAPI.ServerError)?.status == 409
            self.error = error is URLError
                ? "Couldn’t confirm the save. Your draft is still here. Try again."
                : DashboardAPI.connectionMessage(for: error)
        }
    }
}

private struct ProfileTermsLink: View {
    let title: String
    let prompt: String
    @Binding var terms: String
    var emptySummary = "None"
    @State private var newTerm = ""

    private var entries: [String] {
        terms.split(whereSeparator: \.isNewline).map(String.init)
    }

    var body: some View {
        NavigationLink {
            List {
                Section {
                    TextField(prompt, text: $newTerm)
                        .submitLabel(.done)
                        .onSubmit(addTerm)
                    Button("Add", systemImage: "plus", action: addTerm)
                        .disabled(trimmedTerm.isEmpty)
                }
                Section {
                    ForEach(Array(entries.enumerated()), id: \.offset) { entry in
                        Text(entry.element)
                    }
                    .onDelete { offsets in
                        var updated = entries
                        updated.remove(atOffsets: offsets)
                        terms = updated.joined(separator: "\n")
                    }
                } footer: {
                    if !entries.isEmpty { Text("Swipe left on an entry to remove it.") }
                }
            }
            .scrollContentBackground(.hidden)
            .background(JobsTheme.canvas.ignoresSafeArea())
            .navigationTitle(title)
        } label: {
            LabeledContent(title, value: entries.isEmpty ? emptySummary : entries.count == 1 ? entries[0] : "\(entries.count) selected")
        }
    }

    private var trimmedTerm: String {
        newTerm.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func addTerm() {
        guard !trimmedTerm.isEmpty else { return }
        if !entries.contains(where: { $0.caseInsensitiveCompare(trimmedTerm) == .orderedSame }) {
            terms = (entries + [trimmedTerm]).joined(separator: "\n")
        }
        newTerm = ""
    }
}
