import SwiftUI
import UniformTypeIdentifiers

struct RecruiterState: Decodable {
    struct Evidence: Decodable { let label, evidence, kind: String }
    struct Role: Decodable { let title, reason, evidence: String }
    struct Strategy: Decodable {
        let summary: String
        let skills: [Evidence]
        let roles, adjacentRoles, cautions: [Role]
    }
    struct Match: Decodable, Identifiable {
        var id: Int { jobId }
        let jobId: Int
        let title, employer, location, salary, group, reason, resumeEvidence, jobEvidence: String
        let gaps, emphasis, checks: [String]
        var label: String {
            switch group {
            case "close": "Close match"
            case "adjacent": "Worth considering"
            case "review": "Needs confirmation"
            default: "Not recommended"
            }
        }
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
    var busy: Bool { ["analyzing", "discovering", "matching"].contains(stage) }
}

struct RecruiterPreferences: Codable {
    var salary = 70000
    var currency = "USD"
    var period = "year"
    var flexible = false
    var commute = ""
    var remoteRegion = ""
    var modes = ["remote"]
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
    @Environment(\.dynamicTypeSize) private var textSize
    let workspace: Workspace
    @State private var state: RecruiterState?
    @State private var preferences = RecruiterPreferences()
    @State private var importing = false
    @State private var reading = false
    @State private var sending = false
    @State private var error: String?
    @State private var selectedGroup = "recommended"
    @State private var editingPreferences = false
    @State private var importedText: String?
    @State private var lastVersion = -1
    @State private var showingStrategy = false

    private var busy: Bool { reading || sending || state?.busy == true }
    private var stageTitle: String {
        switch state?.stage {
        case "analyzing": "Understanding your experience"
        case "discovering": "Finding and checking openings"
        case "matching": "Comparing jobs with your experience"
        default: "Reading your résumé"
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
                                    else if state?.strategy == nil { await analyze(importedText) }
                                    else { await search() }
                                }
                            }.buttonStyle(.bordered)
                        }
                    }.jobCardSurface()
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
                    if state?.stage == "complete" || state?.stage == "failed" || state?.stage == "matching" {
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
                .padding(.horizontal, 20).padding(.vertical, 10)
                .background(.regularMaterial)
            }
        }
        .background(JobsTheme.canvas.ignoresSafeArea())
        .navigationTitle("For You")
        .navigationBarTitleDisplayMode(.inline)
        .navigationDestination(for: Int.self) { id in
            JobDetail(workspace: workspace, jobID: id, recruiterMatch: state?.matches.first(where: { $0.jobId == id }))
        }
        .toolbar {
            if state?.strategy != nil {
                Menu {
                    Button("Your search preferences") { editingPreferences = true }
                    Button("Replace résumé") { importing = true }
                    Button("Refresh matches") { Task { await search() } }
                } label: { Image(systemName: "slider.horizontal.3") }
                .accessibilityLabel("Recruiter options")
                .disabled(busy)
            }
        }
        .fileImporter(isPresented: $importing, allowedContentTypes: [.pdf, .plainText]) { result in
            switch result {
            case .success(let url):
                Task {
                    reading = true
                    defer { reading = false }
                    do {
                        let preview = try await Task.detached { try ResumePreview.read(url) }.value
                        importedText = preview.text
                        await analyze(preview.text)
                    } catch { self.error = error.localizedDescription }
                }
            case .failure(let issue):
                if (issue as? CocoaError)?.code != .userCancelled { error = issue.localizedDescription }
            }
        }
        .task(id: workspace.address) {
            while !Task.isCancelled {
                await reload()
                do { try await Task.sleep(for: .seconds(state?.busy == true ? 1 : 5)) }
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
            Button { importing = true } label: {
                Label("Upload résumé", systemImage: "arrow.up.doc").frame(maxWidth: .infinity)
            }.buttonStyle(.borderedProminent).controlSize(.large)
            Text("PDF or text, up to 10 MB. Jobs sends your résumé text to its AI service to build your profile. You can review the evidence and replace your résumé.")
                .font(.footnote).foregroundStyle(.secondary)
        }.jobCardSurface()
    }

    private var progress: some View {
        VStack(alignment: .leading, spacing: 14) {
            ProgressView(stageTitle).font(.headline)
            Text("You can leave this screen. Your progress is saved, and your matches will be here when you return.")
                .font(.subheadline).foregroundStyle(.secondary)
        }.jobCardSurface()
    }

    private func strategyCard(_ strategy: RecruiterState.Strategy) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Your search, built around you").font(.title2.bold())
            Text(strategy.summary).font(.subheadline)
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
            Text("Your roles and skills are ready. Just tell us what you need to earn and where you can work.")
                .font(.subheadline).foregroundStyle(.secondary)
            Text("Pay target").font(.headline)
            TextField("Minimum base pay", value: $preferences.salary, format: .number)
                .keyboardType(.numberPad).textFieldStyle(.roundedBorder).accessibilityLabel("Minimum base pay")
            HStack {
                Picker("Currency", selection: $preferences.currency) {
                    ForEach(["USD", "CAD", "GBP", "EUR"], id: \.self) { Text($0) }
                }
                Picker("Pay period", selection: $preferences.period) {
                    Text("Per year").tag("year")
                    Text("Per hour").tag("hour")
                }
            }
            Toggle("My pay target is flexible", isOn: $preferences.flexible)
            Divider()
            Text("Where you work").font(.headline)
            mode("Remote", "remote")
            mode("Hybrid", "hybrid")
            mode("On-site", "onsite")
            if preferences.modes.contains("remote") {
                TextField("Remote work state/region, country", text: $preferences.remoteRegion)
                    .textFieldStyle(.roundedBorder)
                Text("Where you will physically work. Remote employers may only hire in certain regions.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            if preferences.modes.contains("hybrid") || preferences.modes.contains("onsite") {
                TextField("Office city, state/region", text: $preferences.commute).textFieldStyle(.roundedBorder)
                Text("An office location you can commute to. Remote hiring eligibility is checked separately.")
                    .font(.footnote).foregroundStyle(.secondary)
            }

        }.jobCardSurface()
    }

    private func mode(_ label: String, _ value: String) -> some View {
        Toggle(label, isOn: Binding(get: { preferences.modes.contains(value) }, set: { enabled in
            preferences.modes.removeAll { $0 == value }
            if enabled { preferences.modes.append(value) }
        }))
    }

    private var matchPicker: some View {
        Picker("Show matches", selection: $selectedGroup) {
            Text("Recommended").tag("recommended")
            Text("To confirm").tag("review")
            Text("Other").tag("avoid")
        }
    }

    private var results: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Your shortlist").font(.title.bold())
            if state?.coverage != nil && state?.coverage != "success" {
                Label("Some sources couldn’t finish. Coverage is partial.", systemImage: "wifi.exclamationmark")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            if let count = state?.deferred, count > 0 {
                Text("\(count) additional openings are awaiting analysis.").font(.footnote).foregroundStyle(.secondary)
            }
            if textSize.isAccessibilitySize {
                matchPicker.pickerStyle(.menu)
            } else {
                matchPicker.pickerStyle(.segmented)
            }
            let matches = (state?.matches ?? []).filter {
                selectedGroup == "recommended" ? ["close", "adjacent"].contains($0.group) : $0.group == selectedGroup
            }
            if matches.isEmpty && state?.busy != true {
                VStack(alignment: .leading, spacing: 10) {
                    Text(selectedGroup == "recommended" ? "No close matches yet" : "Nothing in this group").font(.headline)
                    Text("We won’t relax your requirements to fill this list. Check roles needing confirmation or adjust your preferences.")
                        .font(.subheadline).foregroundStyle(.secondary)
                    Button("Adjust preferences") { editingPreferences = true }
                }.jobCardSurface()
            }
            ForEach(matches) { match in
                VStack(alignment: .leading, spacing: 12) {
                    Text(match.label.uppercased()).font(.caption.weight(.bold)).foregroundStyle(JobsTheme.accent)
                    Text(match.title).font(.title3.bold())
                    Text(match.employer).font(.subheadline.weight(.medium))
                    Text(match.location + " · " + match.salary).font(.footnote).foregroundStyle(.secondary)
                    if match.group != "close" {
                        ForEach(match.checks, id: \.self) { check in
                            Text(check).font(.subheadline.weight(.medium))
                        }
                    }
                    Text(match.reason).font(.subheadline)
                    DisclosureGroup("Why this match?") {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Your experience").font(.subheadline.bold())
                            Text(match.resumeEvidence).font(.footnote)
                            Text("Employer duties").font(.subheadline.bold())
                            Text(match.jobEvidence).font(.footnote)
                            ForEach(match.checks + match.gaps, id: \.self) { Text($0).font(.footnote).foregroundStyle(.secondary) }
                            if !match.emphasis.isEmpty {
                                Text("What to emphasize").font(.subheadline.bold())
                                ForEach(match.emphasis, id: \.self) { Text($0).font(.footnote) }
                            }
                        }.padding(.top, 8)
                    }
                    NavigationLink("View job & next steps", value: match.jobId).buttonStyle(.bordered)
                }.jobCardSurface()
            }
        }
    }

    @MainActor private func reload() async {
        guard !workspace.address.isEmpty else { return }
        do {
            let data = try await DashboardAPI.request("/api/recruiter", at: workspace.address)
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            let next = try decoder.decode(RecruiterState.self, from: data)
            if lastVersion != next.version {
                if let saved = next.preferences { preferences = saved }
                lastVersion = next.version
            }
            let finished = state?.busy == true && !next.busy
            if state?.version != next.version || state == nil { error = nil }
            state = next
            if finished { await workspace.refresh() }
        } catch is CancellationError { } catch { self.error = error.localizedDescription }
    }

    @MainActor private func analyze(_ text: String?) async {
        var payload: [String: Any] = ["action": "analyze", "version": state?.version ?? 0]
        if let text { payload["resume"] = text }
        await submit(payload)
    }

    @MainActor private func search() async {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        do {
            let value = try JSONSerialization.jsonObject(with: encoder.encode(preferences))
            await submit(["action": "search", "version": state?.version ?? 0, "preferences": value])
        } catch { self.error = error.localizedDescription }
    }

    @MainActor private func submit(_ payload: [String: Any]) async {
        guard !sending else { return }
        sending = true
        defer { sending = false }
        error = nil
        do {
            let body = try JSONSerialization.data(withJSONObject: payload)
            _ = try await DashboardAPI.request("/api/recruiter", at: workspace.address, body: body)
            editingPreferences = false
            await reload()
        } catch { self.error = error.localizedDescription }
    }
}
