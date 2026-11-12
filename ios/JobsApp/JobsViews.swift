import SwiftUI

struct InterestUpdate: Encodable {
    let state: String
    let version: Int
}

struct ForYou: View {
    let workspace: Workspace
    let openBrowse: () -> Void
    let openSettings: () -> Void
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
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                EditorialPanel(label: "Your job feed", title: "Find your next fit.",
                               detail: "Matched skills, published pay and what to check before you apply.",
                               compact: true)
                Picker("Feed", selection: $showingReview) {
                    Text("Top Matches").tag(false)
                    Text("Needs Review").tag(true)
                }
                .pickerStyle(.segmented)
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .firstTextBaseline) {
                        feedHeading
                        Spacer(minLength: 12)
                        Text(visible.count == 1 ? "1 role" : "\(visible.count) roles").font(.subheadline).foregroundStyle(.secondary)
                    }
                    VStack(alignment: .leading, spacing: 4) {
                        feedHeading
                        Text(visible.count == 1 ? "1 role" : "\(visible.count) roles").font(.subheadline).foregroundStyle(.secondary)
                    }
                }
                if visible.isEmpty {
                    ContentUnavailableView {
                        Label(showingReview ? "Nothing to review" : "No strong matches yet", systemImage: "briefcase")
                    } description: {
                        Text("Explore the full list or adjust your search profile.")
                    } actions: {
                        Button("Browse listings", action: openBrowse).buttonStyle(.borderedProminent)
                        if !workspace.isSample { Button("Open settings", action: openSettings) }
                    }
                    .background(JobsTheme.surface, in: .rect(cornerRadius: 22))
                }
                ForEach(visible) { job in
                    VStack(alignment: .leading, spacing: 15) {
                        NavigationLink(value: job.id) {
                            JobCard(job: job, showScore: true)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        Divider()
                        HStack(spacing: 12) {
                            let saved = job.interest?.state == "saved"
                            Button(saved ? "Saved" : "Save", systemImage: saved ? "bookmark.fill" : "bookmark") {
                                Task { await change(job, to: saved ? "none" : "saved") }
                            }
                            .accessibilityHint(saved ? "Remove from My Jobs" : "Add to My Jobs")
                            Button("Pass", systemImage: "xmark") { Task { await change(job, to: "passed") } }
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.large)
                        .disabled(workspace.saving)
                    }
                    .padding(18)
                    .background(JobsTheme.surface, in: .rect(cornerRadius: 22))
                    .overlay {
                        RoundedRectangle(cornerRadius: 22).strokeBorder(.primary.opacity(0.07))
                            .allowsHitTesting(false)
                    }
                }
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 12)
            .frame(maxWidth: 700)
            .frame(maxWidth: .infinity)
        }
        .background(JobsTheme.canvas.ignoresSafeArea())
        .navigationTitle("For You")
        .navigationBarTitleDisplayMode(.inline)
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

    private var feedHeading: some View {
        Text(showingReview ? "Worth a closer look" : "Recommended for you")
            .font(.title3.bold())
            .accessibilityAddTraits(.isHeader)
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
            try await workspace.updateInterest(for: job.id, to: state, version: version)
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
            try await workspace.updateInterest(for: previous.id, to: previous.state, version: previous.version)
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
        VStack(alignment: .leading, spacing: 9) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .center, spacing: 10) {
                    employer
                    Spacer(minLength: 4)
                    if showScore { score }
                }
                VStack(alignment: .leading, spacing: 8) {
                    employer
                    if showScore { score }
                }
            }
            Text(job.title).font(showScore ? .title3.bold() : .headline)
                .foregroundStyle(.primary)
            if let location = job.location, !location.isEmpty {
                Label(location, systemImage: "mappin.and.ellipse")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            Text(job.concisePay).font(.subheadline.weight(.semibold))
            if showScore {
                if let skills = job.matchedSkills, !skills.isEmpty {
                    Label(skills.prefix(3).joined(separator: " · "), systemImage: "checkmark.circle")
                        .font(.footnote)
                        .foregroundStyle(JobsTheme.accent)
                        .accessibilityLabel("Matched skills: \(skills.prefix(3).joined(separator: ", "))")
                } else if let group = job.matchedGroups?.first {
                    Text(group).font(.footnote).foregroundStyle(JobsTheme.accent)
                }
                if let gap = job.matchGaps?.first {
                    Label(gap, systemImage: "info.circle").font(.footnote).foregroundStyle(.secondary)
                } else if job.locationEligibility != "Eligible" {
                    Label("Check location eligibility", systemImage: "info.circle")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                if job.stale == true {
                    Label("Verification needs a refresh", systemImage: "clock")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            if let posted = job.posted, !posted.isEmpty {
                Text("Posted \(displayTimestamp(posted))").font(.caption).foregroundStyle(.secondary)
            }
            if !job.followUp.isEmpty {
                Label("Follow-up \(job.followUp)", systemImage: "calendar")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }

    private var employer: some View {
        Label {
            Text(job.employer)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
        } icon: {
            Text(job.employer.prefix(1).uppercased())
                .font(.subheadline.bold())
                .padding(9)
                .background(JobsTheme.accent.opacity(0.12), in: .rect(cornerRadius: 9))
                .foregroundStyle(JobsTheme.accent)
                .accessibilityHidden(true)
        }
    }

    private var score: some View {
        Text("\(job.score)/100 match")
            .font(.caption.weight(.bold).monospacedDigit())
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .foregroundStyle(JobsTheme.accent)
            .background(JobsTheme.accent.opacity(0.12), in: .capsule)
            .accessibilityLabel("Match score \(job.score) out of 100")
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
        let today = dateString(.now)
        let due = jobs.filter { $0.needsFollowUp(on: today) }
        let stages: [JobBucket] = trackingOnly ? [.all, .applied, .interviews, .offers, .archive] : JobBucket.allCases
        let tracked = trackingOnly ? Dictionary(grouping: jobs) { $0.trackingStage } : [:]
        let source = filters.followUps ? due
            : trackingOnly ? tracked[bucket] ?? []
            : bucket == .all ? jobs : jobs.filter { $0.bucket == bucket }
        let visible = source.filter { filters.includes($0, query: query) }.sorted {
            if filters.followUps, $0.followUp != $1.followUp { return $0.followUp < $1.followUp }
            return filters.sort.precedes($0, $1)
        }

        List {
            Section {
                if trackingOnly {
                    Button {
                        filters = JobFilters()
                        filters.followUps = true
                        query = ""
                    } label: {
                        LabeledContent {
                            Text(due.count.formatted()).monospacedDigit()
                        } label: {
                            Label("Follow-ups Due", systemImage: "calendar.badge.clock")
                        }
                    }
                    .accessibilityAddTraits(filters.followUps ? .isSelected : [])
                }
                Picker(trackingOnly ? "Application Stage" : "Listing View", selection: $bucket) {
                    ForEach(stages) { item in
                        Text(trackingOnly ? "\(label(for: item)) (\(tracked[item]?.count ?? 0))" : label(for: item))
                            .tag(item)
                    }
                }
                .onChange(of: bucket) { _, _ in filters.followUps = false }
                if filters.followUps {
                    Button("Back to \(label(for: bucket))", systemImage: "arrow.uturn.backward") {
                        filters.followUps = false
                    }
                } else if !trackingOnly {
                    Picker("Sort", selection: $filters.sort) {
                        ForEach(JobFilters.Sort.allCases, id: \.self) { Text($0.rawValue).tag($0) }
                    }
                }
            }
            Section("\(filters.followUps ? "Follow-ups Due" : label(for: bucket)) · \(visible.count)") {
                if visible.isEmpty {
                    ContentUnavailableView(
                        filters.followUps ? "No follow-ups in this view"
                            : trackingOnly && bucket == .all && query.isEmpty ? "No saved roles here" : "No listings here",
                        systemImage: trackingOnly ? "bookmark" : "magnifyingglass",
                        description: Text(filters.followUps && due.isEmpty
                            ? "Add a follow-up date in Application Tracking. Due and overdue roles appear here."
                            : trackingOnly && bucket == .all && !filters.followUps && query.isEmpty
                            ? "Save a role from For You or Browse to keep it here."
                            : jobs.isEmpty ? "Add an employer board in Settings and run a search from Alerts."
                            : "Try changing your search or filters.")
                    )
                }
                ForEach(visible) { job in
                    NavigationLink(value: job.id) {
                        VStack(alignment: .leading, spacing: 2) {
                            JobCard(job: job, showScore: !trackingOnly && filters.sort == .score)
                            if trackingOnly, job.status != "Not Applied" {
                                Text(job.status).font(.footnote.weight(.medium)).foregroundStyle(JobsTheme.accent)
                            }
                        }
                    }
                }
            }
        }
        .scrollContentBackground(.hidden)
        .background(JobsTheme.canvas.ignoresSafeArea())
        .navigationTitle(trackingOnly ? "My Jobs" : "Browse")
        .navigationDestination(for: Int.self) { JobDetail(workspace: workspace, jobID: $0) }
        .searchable(text: $query, prompt: "Role, employer, or location")
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
        if trackingOnly && item == .archive { return "Archived" }
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
        let query = query.trimmingCharacters(in: .whitespacesAndNewlines)
        let words = [job.employer, job.title, job.location ?? "", job.description ?? "", job.notes, job.reviewNote]
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
                        JobCard(job: job, showScore: true)
                            .accessibilityAddTraits(.isHeader)
                        if !workspace.isSample {
                            LabeledContent("Employer Pay Details", value: job.publishedPay)
                        }
                        if let availability = job.availability, !availability.isEmpty {
                            LabeledContent("Listing Status", value: availability)
                        }
                        if let url = job.postingURL {
                            Link(destination: url) {
                                Label(job.recruiter?.linkStatus == "verified" ? "Open checked employer application" : "Open posting — check details", systemImage: "arrow.up.right.square")
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.borderedProminent)
                            .controlSize(.large)
                        }
                    }
                    Section("Match and Verification") {
                        LabeledContent("Automatic Checks", value: job.queue ?? "Pending")
                        if let skills = job.matchedSkills, !skills.isEmpty {
                            LabeledContent("Matched skills", value: skills.joined(separator: ", "))
                        }
                        if let explanation = job.explanation, !explanation.isEmpty { Text(explanation) }
                        if let reason = job.locationReason, !reason.isEmpty { Text(reason) }
                        if let evidence = job.applicationEvidence, !evidence.isEmpty { Text(evidence) }
                        if let source = job.source, !source.isEmpty { LabeledContent("Source", value: source) }
                        if let verified = job.lastVerified, !verified.isEmpty {
                            LabeledContent("Last Verified", value: displayTimestamp(verified))
                        }
                    }
                    if let evidence = job.recruiter {
                        Section("Your Evidence and Preparation") {
                            LabeledContent("Application link", value: evidence.linkStatus.capitalized)
                            Text(evidence.adviceMethod).font(.footnote)
                            ForEach(evidence.hardRequirements, id: \.self) { Text($0) }
                            ForEach(evidence.preferences, id: \.self) { Text($0).foregroundStyle(.secondary) }
                            ForEach(evidence.unknowns, id: \.self) { Text($0) }
                            if !evidence.selectedWithoutEvidence.isEmpty {
                                Text("Selected skills without résumé evidence: " + evidence.selectedWithoutEvidence.joined(separator: ", "))
                            }
                            ForEach(evidence.preparation, id: \.self) { Text($0).textSelection(.enabled) }
                            if evidence.preparation.isEmpty {
                                Text("No reviewed résumé excerpts overlap this posting yet. Review your profile before preparing an application.")
                            }
                        }
                    }
                    Section("Your Workflow") {
                        let saved = job.interest?.state == "saved"
                        Button(saved ? "Remove from Saved" : "Save to My Jobs", systemImage: saved ? "bookmark.fill" : "bookmark") {
                            Task {
                                do {
                                    try await workspace.updateInterest(for: job.id, to: saved ? "none" : "saved",
                                                                       version: job.interest?.version ?? 0)
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
                        if !workspace.isSample {
                            Button { editor = .review } label: {
                                LabeledContent("Review and Approval", value: job.reviewDecision)
                            }
                        }
                        Button { editor = .tracking } label: {
                            LabeledContent("Application Tracking", value: job.status)
                        }
                    }
                    if let description = job.description, !description.isEmpty {
                        Section("Employer Description") { Text(description).textSelection(.enabled) }
                    }
                    if !workspace.isSample { adviceSection(job) }
                }
                .scrollContentBackground(.hidden)
                .background(JobsTheme.canvas.ignoresSafeArea())
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
        .workspaceNotice(workspace)
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

struct TrackingDraft: Codable {
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
            try await workspace.updateTracking(for: job.id, draft: draft)
            dismiss()
        } reload: {
            if let current = workspace.dashboard?.jobs.first(where: { $0.id == job.id }) {
                draft = TrackingDraft(current)
            }
        }
    }
}
