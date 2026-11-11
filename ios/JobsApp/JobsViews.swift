import SwiftUI

private struct InterestUpdate: Encodable {
    let state: String
    let version: Int
}

struct ForYou: View {
    let workspace: Workspace
    @State private var showingReview = false
    @State private var undo: (id: Int, state: String, version: Int)?
    @State private var message: String?

    var body: some View {
        let jobs = workspace.dashboard?.jobs ?? []
        let candidates = jobs.filter {
            $0.availability == "Open" && $0.interest?.state != "passed"
                && ($0.bucket == .review || $0.bucket == .ready)
        }
        let ranked = candidates.sorted { first, second in
            let firstPriority = priority(first)
            let secondPriority = priority(second)
            if firstPriority != secondPriority { return firstPriority > secondPriority }
            if first.score != second.score { return first.score > second.score }
            return first.id > second.id
        }
        let ready = ranked.filter { priority($0) > 0 && $0.locationEligibility == "Eligible"
            && $0.salaryCurrency == "USD" && $0.salaryPeriod == "year"
            && $0.salaryType == "base" && $0.salaryMax != nil && $0.reviewBlockers.isEmpty }
        let readyIDs = Set(ready.map(\.id))
        let review = ranked.filter { !readyIDs.contains($0.id) }
        let visible = showingReview ? review : ready
        List {
            Picker("Feed", selection: $showingReview) {
                Text("Top Matches").tag(false)
                Text("Needs Review").tag(true)
            }
            .pickerStyle(.segmented)
            if visible.isEmpty {
                ContentUnavailableView(
                    showingReview ? "Nothing to Review" : "No Strong Matches Yet",
                    systemImage: "briefcase",
                    description: Text("Check Browse for more listings or update your Search Profile.")
                )
            }
            ForEach(visible) { job in
                VStack(alignment: .leading, spacing: 10) {
                    NavigationLink(value: job.id) {
                        JobCard(job: job, showScore: true)
                    }
                    HStack {
                        Button(job.interest?.state == "saved" ? "Saved" : "Save", systemImage: "bookmark") {
                            Task { await change(job, to: job.interest?.state == "saved" ? "none" : "saved") }
                        }
                        Button("Pass", systemImage: "xmark") { Task { await change(job, to: "passed") } }
                    }
                    .buttonStyle(.bordered)
                    .disabled(workspace.saving)
                }
                .padding(.vertical, 6)
            }
        }
        .navigationTitle("For You")
        .navigationDestination(for: Int.self) { JobDetail(workspace: workspace, jobID: $0) }
        .refreshable { await workspace.refresh() }
        .safeAreaInset(edge: .bottom) {
            if let message {
                HStack {
                    Text(message)
                    Spacer()
                    if let undo {
                        Button("Undo") { Task { await restore(undo) } }
                            .disabled(workspace.saving)
                    }
                    Button("Dismiss", systemImage: "xmark") {
                        self.message = nil
                        self.undo = nil
                    }
                    .labelStyle(.iconOnly)
                }
                .padding()
                .background(.regularMaterial)
            }
        }
    }

    private func priority(_ job: Job) -> Int {
        let searches = workspace.dashboard?.savedSearches ?? []
        let phrases = searches.filter(\.enabled).flatMap { $0.titleTerms ?? [] }
        let normalizedTitle = " " + job.title.lowercased().split(whereSeparator: { !$0.isLetter && !$0.isNumber }).joined(separator: " ") + " "
        if phrases.contains(where: { phrase in
            let words = phrase.lowercased().split(whereSeparator: { !$0.isLetter && !$0.isNumber })
            return !words.isEmpty && normalizedTitle.contains(" " + words.joined(separator: " ") + " ")
        }) { return 2 }
        return job.category != nil && job.category != "Other / Review" ? 1 : 0
    }

    private func change(_ job: Job, to state: String) async {
        let version = job.interest?.version ?? 0
        do {
            try await workspace.save("/api/jobs/\(job.id)/interest", InterestUpdate(state: state, version: version))
            undo = (job.id, job.interest?.state ?? "none", version + 1)
            message = state == "saved" ? "Saved to My Jobs" : state == "passed" ? "Moved to Archived" : "Removed from Saved"
        } catch {
            undo = nil
            message = error.localizedDescription
            await workspace.refresh()
        }
    }

    private func restore(_ previous: (id: Int, state: String, version: Int)) async {
        do {
            try await workspace.save("/api/jobs/\(previous.id)/interest",
                                     InterestUpdate(state: previous.state, version: previous.version))
            message = "Action undone"
        } catch {
            message = error.localizedDescription
            await workspace.refresh()
        }
        undo = nil
    }
}

private struct JobCard: View {
    let job: Job
    let showScore: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(job.title).font(.headline)
            Text(job.employer).font(.subheadline).foregroundStyle(.tint)
            if let location = job.location, !location.isEmpty {
                Text(location).font(.subheadline).foregroundStyle(.secondary)
            }
            Text(job.concisePay).font(.subheadline.weight(.semibold))
            if let posted = job.posted, !posted.isEmpty {
                Text("Posted \(displayTimestamp(posted))").font(.caption).foregroundStyle(.secondary)
            }
            if showScore {
                Text("Match \(job.score)/100").font(.subheadline.weight(.semibold))
                if let skills = job.matchedSkills, !skills.isEmpty {
                    Text("Skills: \(skills.joined(separator: ", "))").font(.caption)
                } else if let group = job.matchedGroups?.first {
                    Text(group).font(.caption)
                }
                if let gap = job.matchGaps?.first {
                    Text("Check: \(gap)").font(.caption).foregroundStyle(.secondary)
                }
                if job.locationEligibility != "Eligible" {
                    Text("Check location eligibility").font(.caption).foregroundStyle(.secondary)
                }
                if job.stale == true {
                    Text("Verification needs a refresh").font(.caption).foregroundStyle(.secondary)
                }
            }
            if !job.followUp.isEmpty {
                Text("Follow-up \(job.followUp)").font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}

struct JobList: View {
    let workspace: Workspace
    var trackingOnly = false
    @State private var bucket: JobBucket = .all
    @State private var query = ""
    @State private var filters = JobFilters()
    @State private var showingFilters = false

    var body: some View {
        let jobs = workspace.dashboard?.jobs ?? []
        let visible = jobs.filter {
            let inBucket: Bool
            if trackingOnly && filters.followUps {
                inBucket = $0.interest?.state != "passed" && $0.bucket != .archive
            } else if trackingOnly && bucket == .all {
                inBucket = $0.interest?.state == "saved" || $0.bucket == .ready || $0.bucket == .hold
            } else if trackingOnly && bucket == .archive {
                inBucket = $0.bucket == .archive || $0.interest?.state == "passed"
            } else {
                inBucket = bucket == .all || $0.bucket == bucket
            }
            return inBucket && filters.includes($0, query: query)
        }.sorted(by: filters.sort.precedes)

        List {
            Section {
                Picker("View", selection: $bucket) {
                    ForEach(trackingOnly ? [.all, .applied, .interviews, .offers, .archive] : JobBucket.allCases) { item in
                        Text(label(for: item))
                            .tag(item)
                    }
                }
                Menu("Quick Views", systemImage: "line.3.horizontal.decrease") {
                    Button("All Roles") { filters = JobFilters(); query = "" }
                    Button("Support") { filters = JobFilters(); query = "support" }
                    Button("Implementation") { filters = JobFilters(); query = "implementation" }
                    Button("Follow-ups Due") {
                        filters = JobFilters()
                        filters.followUps = true
                        bucket = .all
                        query = ""
                    }
                }
            }
            Section("\(filters.followUps ? "Follow-ups Due" : label(for: bucket)) · \(visible.count)") {
                if visible.isEmpty {
                    ContentUnavailableView(
                        "No Jobs in This View",
                        systemImage: "briefcase",
                        description: Text(jobs.isEmpty
                            ? "Add an employer board in Preferences, then run a search."
                            : "Choose another bucket or change your filters.")
                    )
                }
                ForEach(visible) { job in
                    NavigationLink(value: job.id) {
                        JobCard(job: job, showScore: false)
                    }
                }
            }
        }
        .navigationTitle(trackingOnly ? "My Jobs" : "Browse")
        .navigationDestination(for: Int.self) { JobDetail(workspace: workspace, jobID: $0) }
        .searchable(text: $query, prompt: "Roles, employers, and notes")
        .refreshable { await workspace.refresh() }
        .toolbar {
            Button("Filters", systemImage: "slider.horizontal.3") { showingFilters = true }
        }
        .sheet(isPresented: $showingFilters) {
            NavigationStack {
                JobFilterForm(filters: $filters, dashboard: workspace.dashboard)
                    .toolbar {
                        ToolbarItem(placement: .cancellationAction) {
                            Button("Reset") { filters = JobFilters() }
                        }
                        ToolbarItem(placement: .confirmationAction) {
                            Button("Done") { showingFilters = false }
                        }
                    }
            }
        }
    }

    private func label(for item: JobBucket) -> String {
        if item == .all { return trackingOnly ? "Saved" : "All Listings" }
        return item.rawValue
    }

}

private struct JobFilters {
    var employer = ""
    var status = ""
    var category = ""
    var area = ""
    var queue = ""
    var minScore = 0
    var minPay = 0
    var posted = ""
    var verified = ""
    var followUps = false
    var sort = Sort.newest

    enum Sort: String, CaseIterable {
        case newest = "Newest discovered"
        case score = "Best match"
        case pay = "Highest salary"
        case status = "Application status"
        case updated = "Recently updated"
        case posted = "Newest posted"

        func precedes(_ first: Job, _ second: Job) -> Bool {
            switch self {
            case .newest:
                if first.created != second.created { return first.created > second.created }
            case .score:
                if first.score != second.score { return first.score > second.score }
            case .pay:
                if first.salaryMax != second.salaryMax {
                    return (first.salaryMax ?? -1) > (second.salaryMax ?? -1)
                }
            case .status:
                if first.status != second.status { return first.status < second.status }
            case .updated:
                if first.updated != second.updated { return first.updated > second.updated }
            case .posted:
                if first.posted != second.posted { return (first.posted ?? "") > (second.posted ?? "") }
            }
            return first.id > second.id
        }
    }

    func includes(_ job: Job, query: String) -> Bool {
        if followUps && (job.followUp.isEmpty || job.followUp > dateString(.now)
            || ["Rejected", "Withdrawn", "Position Closed"].contains(job.status)) { return false }
        let words = [job.employer, job.title, job.description ?? "", job.notes, job.reviewNote]
        return (query.isEmpty || words.contains { $0.localizedCaseInsensitiveContains(query) })
            && (employer.isEmpty || job.employer == employer)
            && (status.isEmpty || job.status == status)
            && (category.isEmpty || (job.category ?? "Imported") == category)
            && (area.isEmpty || job.area == area)
            && (queue.isEmpty || job.queue == queue)
            && job.score >= minScore
            && (job.salaryMax ?? 0) >= Double(minPay)
            && (posted.isEmpty || String((job.posted ?? "").prefix(10)) >= posted)
            && (verified.isEmpty || String((job.lastVerified ?? "").prefix(10)) >= verified)
    }
}

private struct JobFilterForm: View {
    @Binding var filters: JobFilters
    let dashboard: Dashboard?

    var body: some View {
        let jobs = dashboard?.jobs ?? []
        Form {
            Picker("Sort", selection: $filters.sort) {
                ForEach(JobFilters.Sort.allCases, id: \.self) { Text($0.rawValue).tag($0) }
            }
            Toggle("Follow-ups Due", isOn: $filters.followUps)
            choice("Employer", $filters.employer, Array(Set(jobs.map(\.employer))).sorted())
            choice("Application Status", $filters.status, dashboard?.statuses ?? [])
            choice("Category", $filters.category, Array(Set(jobs.map { $0.category ?? "Imported" })).sorted())
            choice("Area", $filters.area, Array(Set(jobs.compactMap(\.area))).sorted())
            choice("Verification", $filters.queue, ["Confirmed", "Review", "Location Review", "Excluded"])
            Picker("Minimum Match", selection: $filters.minScore) {
                Text("Any").tag(0)
                ForEach([55, 70, 85], id: \.self) { Text("\($0)/100").tag($0) }
            }
            Picker("Published Maximum Base", selection: $filters.minPay) {
                Text("Any").tag(0)
                ForEach([70000, 85000, 100000], id: \.self) {
                    Text($0, format: .currency(code: "USD").precision(.fractionLength(0))).tag($0)
                }
            }
            OptionalDateField(label: "Posted On or After", value: $filters.posted)
            OptionalDateField(label: "Verified On or After", value: $filters.verified)
        }
        .navigationTitle("Filters")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func choice(_ title: String, _ selection: Binding<String>, _ options: [String]) -> some View {
        Picker(title, selection: selection) {
            Text("Any").tag("")
            ForEach(options, id: \.self) { Text($0).tag($0) }
        }
    }
}

struct JobDetail: View {
    let workspace: Workspace
    let jobID: Int
    @State private var editor: Editor?
    @State private var interestError: String?
    @State private var requestingAdvice = false
    @State private var confirmingAdvice = false
    @State private var adviceError: String?

    private enum Editor: String, Identifiable {
        case review, tracking
        var id: Self { self }
    }

    var body: some View {
        Group {
            if let job = workspace.dashboard?.jobs.first(where: { $0.id == jobID }) {
                List {
                    Section {
                        Text(job.employer).foregroundStyle(.tint)
                        Text(job.title).font(.title2.bold())
                        if let location = job.location, !location.isEmpty {
                            LabeledContent("Location", value: location)
                        }
                        LabeledContent("Published Pay", value: job.publishedPay)
                        if let availability = job.availability, !availability.isEmpty {
                            LabeledContent("Listing Status", value: availability)
                        }
                        if let url = job.postingURL {
                            Link("Open Employer Posting", destination: url)
                        }
                    }
                    Section("Match and Verification") {
                        LabeledContent(job.matchLabel, value: "\(job.score)/100")
                        LabeledContent("Automatic Checks", value: job.queue ?? "Pending")
                        if let explanation = job.explanation, !explanation.isEmpty { Text(explanation) }
                        if let reason = job.locationReason, !reason.isEmpty { Text(reason) }
                        if let evidence = job.applicationEvidence, !evidence.isEmpty { Text(evidence) }
                        if let source = job.source, !source.isEmpty { LabeledContent("Source", value: source) }
                        if let posted = job.posted, !posted.isEmpty { LabeledContent("Posted", value: posted) }
                        if let verified = job.lastVerified, !verified.isEmpty {
                            LabeledContent("Last Verified", value: displayTimestamp(verified))
                        }
                    }
                    Section("Your Workflow") {
                        let saved = job.interest?.state == "saved"
                        Button(saved ? "Remove from Saved" : "Save to My Jobs", systemImage: saved ? "bookmark.fill" : "bookmark") {
                            Task {
                                do {
                                    try await workspace.save("/api/jobs/\(job.id)/interest",
                                        InterestUpdate(state: saved ? "none" : "saved", version: job.interest?.version ?? 0))
                                    interestError = nil
                                } catch {
                                    interestError = error.localizedDescription
                                    await workspace.refresh()
                                }
                            }
                        }
                        .disabled(workspace.saving)
                        if let interestError { Text(interestError).foregroundStyle(.secondary) }
                        if let action = job.interest {
                            LabeledContent("Last List Action", value: displayTimestamp(action.updated))
                        }
                        Button { editor = .review } label: {
                            LabeledContent("Review and Approval", value: job.reviewDecision)
                        }
                        Button { editor = .tracking } label: {
                            LabeledContent("Application Tracking", value: job.status)
                        }
                    }
                    if let description = job.description, !description.isEmpty {
                        Section("Employer Description") { Text(description).textSelection(.enabled) }
                    }
                    adviceSection(job)
                }
                .refreshable { await workspace.refresh() }
                .sheet(item: $editor) { item in
                    switch item {
                    case .review: ReviewEditor(workspace: workspace, job: job)
                    case .tracking: TrackingEditor(workspace: workspace, job: job)
                    }
                }
                .confirmationDialog("Request AI Career Advice?", isPresented: $confirmingAdvice) {
                    Button("Send Request") { Task { await requestAdvice() } }
                } message: {
                    Text("Your profile and posting details will be sent to OpenAI. A new request may incur charges.")
                }
            } else {
                ContentUnavailableView("Job Unavailable", systemImage: "briefcase")
            }
        }
        .navigationTitle("Job Details")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func adviceSection(_ job: Job) -> some View {
        Section("AI Career Advice") {
            if let saved = job.aiAdvice {
                Text(saved.advice.summary)
                adviceGroup("Strengths", saved.advice.strengths)
                adviceGroup("Gaps", saved.advice.gaps)
                adviceGroup("Questions", saved.advice.questions)
                adviceGroup("Next Steps", saved.advice.nextSteps)
                Text("\(saved.model) · \(displayTimestamp(saved.created))").font(.footnote)
                if saved.stale {
                    Text("The posting or preferences changed since this review.").foregroundStyle(.secondary)
                }
            }
            if let dashboard = workspace.dashboard, dashboard.preferences.aiEnabled, dashboard.aiConfigured {
                if job.aiAdvice?.stale != false {
                    Button("Request AI Review") { confirmingAdvice = true }
                        .disabled(requestingAdvice || workspace.saving)
                }
            } else {
                Text("Enable AI in Preferences and configure the key on the Mac to request advice.")
                    .foregroundStyle(.secondary)
            }
            if requestingAdvice { ProgressView("Requesting advice…") }
            if let adviceError { Text(adviceError).foregroundStyle(.red) }
        }
    }

    private func adviceGroup(_ title: String, _ items: [String]) -> some View {
        Group {
            if !items.isEmpty {
                Text(title).font(.headline)
                ForEach(items.indices, id: \.self) { Text(items[$0]) }
            }
        }
    }

    private func requestAdvice() async {
        requestingAdvice = true
        adviceError = nil
        defer { requestingAdvice = false }
        do { try await workspace.save("/api/jobs/\(jobID)/ai-review", [String: String]()) }
        catch { adviceError = error.localizedDescription }
    }
}

private struct ReviewDraft: Encodable {
    var decision: String
    let version: Int
    let trackingVersion: Int
    var checks: [String: Bool]
    var note: String
    var reviewer: String

    init(_ job: Job) {
        decision = job.reviewDecision
        version = job.reviewVersion
        trackingVersion = job.version
        checks = job.reviewChecks
        note = job.reviewNote
        reviewer = job.reviewReviewer
    }
}

private struct ReviewEditor: View {
    @Environment(\.dismiss) private var dismiss
    let workspace: Workspace
    @State private var job: Job
    @State private var draft: ReviewDraft

    init(workspace: Workspace, job: Job) {
        self.workspace = workspace
        _job = State(initialValue: job)
        _draft = State(initialValue: ReviewDraft(job))
    }

    var body: some View {
        SaveForm(title: "Review and Approval", workspace: workspace) {
            Section("Decision") {
                Picker("Decision", selection: $draft.decision) {
                    Text("Return to Review Inbox").tag("Pending")
                    Text("Approve for Application").tag("Approved")
                    Text("Hold for More Information").tag("Hold")
                    Text("Dismiss").tag("Dismissed")
                }
                ForEach(job.reviewBlockers.indices, id: \.self) { index in
                    Text(job.reviewBlockers[index]).foregroundStyle(.secondary)
                }
            }
            Section("Approval Checklist") {
                check("Location meets my requirements", "location")
                check("Published base pay meets my policy", "salary")
                check("Employer application is open", "application")
                check("I haven’t already applied", "history")
            }
            Section("Review Notes") {
                TextField("Reviewer (optional)", text: $draft.reviewer)
                TextField("What did you verify?", text: $draft.note, axis: .vertical)
                    .lineLimit(3...8)
            }
        } save: {
            try await workspace.save("/api/jobs/\(job.id)/review", draft)
            dismiss()
        } reload: {
            if let current = workspace.dashboard?.jobs.first(where: { $0.id == job.id }) {
                job = current
                draft = ReviewDraft(current)
            }
        }
    }

    private func check(_ title: String, _ key: String) -> some View {
        Toggle(title, isOn: Binding(
            get: { draft.checks[key] ?? false },
            set: { draft.checks[key] = $0 }
        ))
    }
}

private struct TrackingDraft: Encodable {
    let version: Int
    var status: String
    var applicationDate: String
    var followUp: String
    var notes: String

    init(_ job: Job) {
        version = job.version
        status = job.status
        applicationDate = job.applicationDate
        followUp = job.followUp
        notes = job.notes
    }
}

private struct TrackingEditor: View {
    @Environment(\.dismiss) private var dismiss
    let workspace: Workspace
    let job: Job
    @State private var draft: TrackingDraft

    init(workspace: Workspace, job: Job) {
        self.workspace = workspace
        self.job = job
        _draft = State(initialValue: TrackingDraft(job))
    }

    var body: some View {
        SaveForm(title: "Application Tracking", workspace: workspace) {
            Section("Application") {
                Picker("Status", selection: $draft.status) {
                    ForEach(workspace.dashboard?.statuses ?? [], id: \.self) { Text($0).tag($0) }
                }
                OptionalDateField(label: "Application Date", value: $draft.applicationDate)
                OptionalDateField(label: "Follow-up Date", value: $draft.followUp)
            }
            Section("Notes") {
                TextField("Application notes", text: $draft.notes, axis: .vertical).lineLimit(3...10)
            }
        } save: {
            try await workspace.save("/api/jobs/\(job.id)/tracking", draft)
            dismiss()
        } reload: {
            if let current = workspace.dashboard?.jobs.first(where: { $0.id == job.id }) {
                draft = TrackingDraft(current)
            }
        }
    }
}
