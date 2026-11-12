import SwiftUI

struct InterestUpdate: Encodable {
    let state: String
    let version: Int
}

struct ForYou: View {
    let workspace: Workspace
    let openBrowse: () -> Void
    let openSettings: () -> Void
    let openSearch: () -> Void
    @State private var showingReview = false
    @State private var undo: (id: Int, state: String, version: Int)?
    @State private var message: String?

    var body: some View {
        let jobs = workspace.dashboard?.jobs ?? []
        let sampleFloor = workspace.dashboard?.preferences.salaryFloor ?? 0
        let candidates = jobs.filter {
            $0.availability == "Open" && $0.interest?.state != "passed"
                && ($0.bucket == .review || $0.bucket == .ready)
                && (!workspace.isSample || ($0.score > 0 && ($0.salaryMax ?? .infinity) >= Double(sampleFloor)))
        }
        let ranked = candidates.sorted { first, second in
            let firstDuties = first.matchedDutyCount ?? 0
            let secondDuties = second.matchedDutyCount ?? 0
            if firstDuties != secondDuties { return firstDuties > secondDuties }
            let firstPriority = priority(first)
            let secondPriority = priority(second)
            if firstPriority != secondPriority { return firstPriority > secondPriority }
            if first.score != second.score { return first.score > second.score }
            return first.id > second.id
        }
        let ready = ranked.filter { priority($0) > 0 && $0.locationEligibility == "Eligible"
            && $0.publishedAnnualBaseMax != nil && $0.reviewBlockers.isEmpty }
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
                if jobs.isEmpty && !workspace.isSample {
                    let hasSources = workspace.dashboard?.sources.contains(where: { !$0.disabled }) == true
                    ContentUnavailableView {
                        Label("Your job feed is empty", systemImage: "briefcase")
                    } description: {
                        Text(hasSources ? "Run an employer search to check your sources against your profile."
                                        : "Set your search profile and add an employer board to start finding roles.")
                    } actions: {
                        if hasSources {
                            Button("Open Employer Search", action: openSearch).buttonStyle(.borderedProminent)
                        }
                        Button("Open Search Settings", action: openSettings)
                    }
                    .background(JobsTheme.surface, in: .rect(cornerRadius: 22))
                } else if visible.isEmpty {
                    ContentUnavailableView {
                        Label(showingReview ? "Nothing to review" : "No strong matches yet", systemImage: "briefcase")
                    } description: {
                        Text("Explore the full list or adjust your search profile.")
                    } actions: {
                        if !showingReview && !review.isEmpty {
                            Button("See Roles to Review") { showingReview = true }.buttonStyle(.borderedProminent)
                        }
                        Button("Browse listings", action: openBrowse)
                        Button("Open settings", action: openSettings)
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
                        .disabled(workspace.saving || !workspace.canWrite)
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
                            .disabled(workspace.saving || !workspace.canWrite)
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
            if job.isExternalApplication {
                Label("Added by you", systemImage: "person.crop.circle")
                    .font(.caption).foregroundStyle(.secondary)
            } else {
                Text(job.concisePay).font(.subheadline.weight(.semibold))
            }
            if job.source != "Fictional sample listing", job.availability == "Open" {
                let utcDay = Date.now.ISO8601Format().prefix(10)
                if job.queue == "Confirmed", job.applicationVerified?.prefix(10) == utcDay {
                    Label("Verified Today", systemImage: "checkmark.seal")
                        .font(.caption).foregroundStyle(JobsTheme.accent)
                }
                if job.created.prefix(10) == utcDay {
                    Label("New Today", systemImage: "sparkle")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            if showScore {
                if let count = job.matchedDutyCount, count > 0 {
                    Label(count == 1 ? "1 duty uses a profile skill" : "\(count) duties use profile skills",
                          systemImage: "list.bullet.clipboard")
                        .font(.footnote).foregroundStyle(JobsTheme.accent)
                }
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
                Label("Follow-up \(displayTimestamp(job.followUp))", systemImage: "calendar")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }

    private var employer: some View {
        HStack(spacing: 9) {
            Text(job.employer.prefix(1).uppercased())
                .font(.subheadline.bold())
                .fixedSize()
                .padding(9)
                .background(JobsTheme.accent.opacity(0.12), in: .rect(cornerRadius: 9))
                .foregroundStyle(JobsTheme.accent)
                .accessibilityHidden(true)
            Text(job.employer)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
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
    var openEmployerSearch: (() -> Void)? = nil
    @State private var bucket: JobBucket = .all
    @State private var query = ""
    @FocusState private var filtering: Bool
    @State private var filters = JobFilters()
    @State private var showingFilters = false

    @State private var interestError: String?
    @State private var trackingJob: Job?
    @State private var addingApplication = false

    var body: some View {
        let jobs = (workspace.dashboard?.jobs ?? []).filter { trackingOnly || !$0.isExternalApplication }
        let today = dateString(.now)
        let due = jobs.filter { $0.needsFollowUp(on: today) }
        let upcoming = jobs.filter { $0.trackingStage != .archive && $0.followUp > today }
        let stages: [JobBucket] = trackingOnly ? [.all, .applied, .interviews, .offers, .archive] : JobBucket.allCases
        let tracked = trackingOnly ? Dictionary(grouping: jobs, by: \.trackingStage) : [:]
        let source = filters.followUp == .due ? due : filters.followUp == .upcoming ? upcoming
            : trackingOnly ? tracked[bucket] ?? []
            : bucket == .all ? jobs : jobs.filter { $0.bucket == bucket }
        let visible = source.filter { filters.includes($0, query: query) }.sorted {
            if filters.followUp != .none, $0.followUp != $1.followUp { return $0.followUp < $1.followUp }
            return filters.sort.precedes($0, $1)
        }

        List {
            Section {
                HStack {
                    Image(systemName: "magnifyingglass").foregroundStyle(.secondary).accessibilityHidden(true)
                    TextField(trackingOnly ? "Filter tracked jobs" : "Filter listings", text: $query)
                        .accessibilityIdentifier("listingFilter")
                        .autocorrectionDisabled()
                        .submitLabel(.search)
                        .focused($filtering)
                        .onSubmit { filtering = false }
                    if !query.isEmpty {
                        Button("Clear search", systemImage: "xmark.circle.fill") { query = "" }
                            .labelStyle(.iconOnly).buttonStyle(.borderless)
                    }
                }
                if let openEmployerSearch {
                    Button(workspace.isSample ? "Connect for Live Search" : "Find New Jobs",
                           systemImage: workspace.isSample ? "desktopcomputer" : "arrow.clockwise") {
                        filtering = false
                        openEmployerSearch()
                    }
                }
            } footer: {
                if !trackingOnly {
                    Text(workspace.isSample ? "Filter the fictional listings in this sample."
                         : "Filter listings already in Jobs, or find new jobs from employer sources.")
                }
            }
            if trackingOnly {
                if workspace.dashboard?.externalApplicationTracking == true {
                    Button("Add Application", systemImage: "plus.circle") {
                        filtering = false
                        addingApplication = true
                    }
                    .disabled(!workspace.canWrite || workspace.saving)
                }
                Section("Follow-ups") {
                    followUpRow("Due or overdue", icon: "calendar.badge.clock", count: due.count, scope: .due)
                    followUpRow("Upcoming", icon: "calendar", count: upcoming.count, scope: .upcoming)
                }
            }
            Section {
                Picker(trackingOnly ? "Application Stage" : "Listing View", selection: $bucket) {
                    ForEach(stages) { item in
                        Text(trackingOnly ? "\(label(for: item)) (\(tracked[item]?.count ?? 0))" : label(for: item))
                            .tag(item)
                    }
                }
                .accessibilityIdentifier(trackingOnly ? "applicationStage" : "listingView")
                .onChange(of: bucket) { _, _ in filters.followUp = .none }
                if filters.followUp != .none {
                    Button("Back to \(label(for: bucket))", systemImage: "arrow.uturn.backward") {
                        filters.followUp = .none
                    }
                } else if !trackingOnly {
                    browseControls(jobs: jobs)
                }
                if filters.activeCount > 0 {
                    Button("Clear filters (\(filters.activeCount))", systemImage: "xmark.circle") {
                        let sort = filters.sort
                        filters = JobFilters()
                        filters.sort = sort
                    }
                }
            }
            Section("\(filters.followUp.title ?? label(for: bucket)) · \(visible.count)") {
                if visible.isEmpty {
                    ContentUnavailableView(
                        filters.followUp != .none ? "No follow-ups in this view"
                            : !query.isEmpty ? "No matching listings"
                            : trackingOnly && bucket == .all ? "No saved roles here" : "No listings here",
                        systemImage: trackingOnly ? "bookmark" : "magnifyingglass",
                        description: Text(filters.followUp != .none
                            ? "You can set a date from a job’s application tracking form."
                            : trackingOnly && bucket == .all && query.isEmpty
                            ? "Save a role from For You or Browse to keep it here."
                            : jobs.isEmpty ? "Add an employer board in Settings and run a search from Alerts."
                            : "Try changing your search or filters.")
                    )
                }
                ForEach(visible) { job in
                    NavigationLink(value: job.id) {
                        VStack(alignment: .leading, spacing: 4) {
                            JobCard(job: job, showScore: !trackingOnly && filters.sort == .score)
                            if trackingOnly, job.status != "Not Applied" {
                                Text(job.status).font(.footnote.weight(.medium)).foregroundStyle(JobsTheme.accent)
                            } else if !trackingOnly, job.interest?.state == "saved" {
                                Label("Saved", systemImage: "bookmark.fill")
                                    .font(.footnote.weight(.medium)).foregroundStyle(JobsTheme.accent)
                            }
                        }
                    }
                    .swipeActions(allowsFullSwipe: false) {
                        if trackingOnly {
                            Button("Tracking", systemImage: "checklist") { trackingJob = job }
                                .tint(JobsTheme.accent)
                        } else {
                            let saved = job.interest?.state == "saved"
                            Button(saved ? "Unsave" : "Save", systemImage: saved ? "bookmark.slash" : "bookmark") {
                                Task { await toggleSaved(job) }
                            }
                            .tint(JobsTheme.accent)
                            .disabled(workspace.saving || !workspace.canWrite)
                        }
                    }
                }
            }
        }
        .scrollContentBackground(.hidden)
        .background(JobsTheme.canvas.ignoresSafeArea())
        .navigationTitle(trackingOnly ? "My Jobs" : "Browse")
        .navigationDestination(for: Int.self) { JobDetail(workspace: workspace, jobID: $0) }
        .scrollDismissesKeyboard(.interactively)
        .refreshable { await workspace.refresh() }
        .toolbar {
            Button("Filters", systemImage: "slider.horizontal.3") { showingFilters = true }
        }
        .sheet(item: $trackingJob) { TrackingEditor(workspace: workspace, job: $0) }
        .sheet(isPresented: $addingApplication) {
            AddApplicationForm(workspace: workspace) { stage in
                filters = JobFilters()
                query = ""
                bucket = stage
            }
        }
        .alert("Couldn’t update saved job", isPresented: Binding(
            get: { interestError != nil }, set: { if !$0 { interestError = nil } }
        )) { Button("OK", role: .cancel) {} } message: { Text(interestError ?? "") }
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

    private func followUpRow(_ title: String, icon: String, count: Int, scope: JobFilters.FollowUp) -> some View {
        Button {
            filters.followUp = filters.followUp == scope ? .none : scope
        } label: {
            LabeledContent {
                Text(count.formatted()).monospacedDigit()
            } label: {
                Label(title, systemImage: icon)
            }
        }
        .accessibilityAddTraits(filters.followUp == scope ? .isSelected : [])
    }

    @ViewBuilder
    private func browseControls(jobs: [Job]) -> some View {
        Picker("Sort", selection: $filters.sort) {
            ForEach(JobFilters.Sort.allCases, id: \.self) { Text($0.rawValue).tag($0) }
        }
        Picker("Work Setting", selection: $filters.workSetting) {
            Text("Any").tag("")
            ForEach(["Remote", "Hybrid", "On-site"], id: \.self) { setting in
                let count = jobs.filter { $0.workSetting == setting }.count
                Text("\(setting) (\(count))").tag(setting)
            }
        }
        Toggle("Open Listings Only", isOn: $filters.openOnly)
    }

    private func toggleSaved(_ job: Job) async {
        let next = job.interest?.state == "saved" ? "none" : "saved"
        do {
            try await workspace.updateInterest(for: job.id, to: next, version: job.interest?.version ?? 0)
        } catch {
            interestError = error.localizedDescription
            await workspace.refresh()
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
    var workSetting = ""
    var openOnly = false
    var followUp = FollowUp.none
    var sort = Sort.newest

    var activeCount: Int {
        [employer, status, category, area, queue, posted, verified, workSetting].filter { !$0.isEmpty }.count
            + [minScore > 0, minPay > 0, followUp != .none, openOnly].filter { $0 }.count
    }

    enum FollowUp {
        case none, due, upcoming

        var title: String? {
            switch self {
            case .none: return nil
            case .due: return "Follow-ups Due"
            case .upcoming: return "Upcoming Follow-ups"
            }
        }
    }

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
                if first.publishedAnnualBaseMax != second.publishedAnnualBaseMax {
                    return (first.publishedAnnualBaseMax ?? -1) > (second.publishedAnnualBaseMax ?? -1)
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
        let terms = query.split(whereSeparator: \.isWhitespace)
        let fields = [job.employer, job.title, job.location ?? "", job.description ?? "", job.notes, job.reviewNote]
            + (job.matchedSkills ?? [])
        return terms.allSatisfy { term in fields.contains { $0.localizedCaseInsensitiveContains(String(term)) } }
            && (!openOnly || job.availability == "Open")
            && (workSetting.isEmpty || job.workSetting == workSetting)
            && (employer.isEmpty || job.employer == employer)
            && (status.isEmpty || job.status == status)
            && (category.isEmpty || (job.category ?? "Imported") == category)
            && (area.isEmpty || job.area == area)
            && (queue.isEmpty || job.queue == queue)
            && job.score >= minScore
            && (minPay == 0 || (job.publishedAnnualBaseMax ?? 0) >= Double(minPay))
            && (posted.isEmpty || String((job.posted ?? "").prefix(10)) >= posted)
            && (verified.isEmpty || String((job.applicationVerified ?? "").prefix(10)) >= verified)
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
            Toggle("Open Listings Only", isOn: $filters.openOnly)
            choice("Work Setting", $filters.workSetting, ["Remote", "Hybrid", "On-site"])
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
            OptionalDateField(label: "Application Verified On or After", value: $filters.verified)
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
                        JobCard(job: job, showScore: !job.isExternalApplication)
                            .accessibilityAddTraits(.isHeader)
                        if !workspace.isSample && !job.isExternalApplication {
                            LabeledContent("Employer Pay Details", value: job.publishedPay)
                        }
                        if !job.isExternalApplication, let availability = job.availability, !availability.isEmpty {
                            LabeledContent("Listing Status", value: availability)
                        }
                        if let url = job.postingURL {
                            let label = job.isExternalApplication ? "Open saved link"
                                : workspace.isSample ? "Open sample link"
                                : job.hasVerifiedPostingLink ? "Open checked employer posting"
                                : "Open unverified posting link"
                            if job.hasVerifiedPostingLink {
                                Link(destination: url) {
                                    Label(label, systemImage: "arrow.up.right.square")
                                        .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.borderedProminent)
                                .controlSize(.large)
                            } else {
                                Link(destination: url) {
                                    Label(label, systemImage: "arrow.up.right.square")
                                }
                            }
                        }
                        Button { editor = .tracking } label: {
                            LabeledContent("Application Tracking", value: job.status)
                        }
                        .accessibilityIdentifier("openApplicationTracking")
                    }
                    if job.isExternalApplication {
                        Section("Posting Details") {
                            Text("You entered these details. Jobs hasn’t verified the posting.")
                        }
                    } else {
                        Section("Why It Matches") {
                            if let breakdown = job.scoreBreakdown {
                                scoreRow("Target role", points: breakdown.targetRole, maximum: 45)
                                scoreRow("Selected skills", points: breakdown.selectedSkills, maximum: 30)
                                scoreRow("Skill groups", points: breakdown.skillGroups, maximum: 25)
                                if let groups = job.matchedGroups, !groups.isEmpty {
                                    LabeledContent("Matched groups", value: groups.joined(separator: ", "))
                                }
                            } else if let explanation = job.explanation, !explanation.isEmpty {
                                Text(explanation)
                            }
                            if let skills = job.matchedSkills, !skills.isEmpty {
                                LabeledContent("Matched skills", value: skills.joined(separator: ", "))
                            }
                        }
                        if let evidence = job.dutyEvidence, !evidence.isEmpty {
                            Section("Duties Using Your Profile Skills") {
                                ForEach(evidence, id: \.skill) { item in
                                    VStack(alignment: .leading, spacing: 5) {
                                        Text(item.skill).font(.subheadline.bold())
                                        Text(item.duty).font(.subheadline).foregroundStyle(.secondary)
                                    }
                                }
                            }
                        }
                        Section("Employer Verification") {
                            LabeledContent("Automatic Checks", value: verificationLabel(for: job))
                            if let reason = job.locationReason, !reason.isEmpty { Text(reason) }
                            if let evidence = job.applicationEvidence, !evidence.isEmpty { Text(evidence) }
                            if let source = job.source, !source.isEmpty { LabeledContent("Source", value: source) }
                            if let checked = job.lastVerified, !checked.isEmpty {
                                LabeledContent("Employer Source Checked", value: displayTimestamp(checked))
                            }
                            if let checked = job.postingVerified, !checked.isEmpty {
                                LabeledContent("Direct Posting Checked", value: displayTimestamp(checked))
                                    .accessibilityIdentifier("directPostingChecked")
                            }
                            if let verified = job.applicationVerified, !verified.isEmpty {
                                LabeledContent("Application Form Verified", value: displayTimestamp(verified))
                                    .accessibilityIdentifier("applicationFormChecked")
                            }
                            ForEach(job.reviewBlockers + (job.matchGaps ?? []), id: \.self) { blocker in
                                Label(blocker, systemImage: "exclamationmark.circle")
                                    .foregroundStyle(.secondary)
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
                            .disabled(workspace.saving || !workspace.canWrite)
                            if let interestError { Text(interestError).foregroundStyle(.secondary) }
                            if let action = job.interest {
                                LabeledContent("Last List Action", value: displayTimestamp(action.updated))
                            }
                            if !workspace.isSample {
                                Button { editor = .review } label: {
                                    LabeledContent("Review and Approval", value: job.reviewDecision)
                                }
                            }
                        }
                        if let description = job.description, !description.isEmpty {
                            Section("Employer Description") { Text(description).textSelection(.enabled) }
                        }
                        if !workspace.isSample { adviceSection(job) }
                    }
                }
                .scrollContentBackground(.hidden)
                .background(JobsTheme.canvas.ignoresSafeArea())
                .toolbar {
                    if let url = job.postingURL {
                        ShareLink(item: url) { Label("Share posting", systemImage: "square.and.arrow.up") }
                    }
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
        .workspaceNotice(workspace)
        .navigationTitle("Job Details")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func scoreRow(_ title: String, points: Int, maximum: Int) -> some View {
        ProgressView(value: Double(points), total: Double(maximum)) {
            Text(title)
        } currentValueLabel: {
            Text("\(points) of \(maximum) points").font(.caption).foregroundStyle(.secondary)
        }
    }

    private func verificationLabel(for job: Job) -> String {
        if job.availability == "Closed" { return "Closed" }
        if job.stale == true { return "Recheck needed" }
        switch job.queue {
        case "Confirmed": return "Verified"
        case "Location Review": return "Check location"
        case "Excluded": return "Outside search preferences"
        default: return "Needs review"
        }
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
                        .disabled(requestingAdvice || workspace.saving || !workspace.canWrite)
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

private struct AddApplicationForm: View {
    @Environment(\.dismiss) private var dismiss
    let workspace: Workspace
    let saved: (JobBucket) -> Void
    @State private var draft = Draft()

    private struct Draft: Encodable {
        var title = ""
        var employer = ""
        var location = ""
        var url = ""
        var status = "Applied"
        var applicationDate = ""
        var followUp = ""
        var notes = ""

        var stage: JobBucket {
            switch status {
            case "Interview Scheduled", "Interview Completed": return .interviews
            case "Offer Received": return .offers
            case "Rejected", "Withdrawn", "Position Closed": return .archive
            default: return .applied
            }
        }
    }

    private var canSave: Bool {
        !draft.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !draft.employer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        SaveForm(title: "Add Application", workspace: workspace, saveDisabled: !canSave, reloadOnConflict: false) {
            Section("Job Details") {
                TextField("Job title", text: $draft.title)
                TextField("Employer", text: $draft.employer)
                TextField("Location (optional)", text: $draft.location)
                TextField("Posting link (optional)", text: $draft.url)
                    .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
            }
            Section("Application") {
                Picker("Status", selection: $draft.status) {
                    ForEach(workspace.dashboard?.statuses.filter {
                        !["Needs Verification", "Not Applied", "Planning to Apply"].contains($0)
                    } ?? [], id: \.self) { Text($0).tag($0) }
                }
                OptionalDateField(label: "Application Date", value: $draft.applicationDate)
                OptionalDateField(label: "Follow-up Date", value: $draft.followUp)
                TextField("Application notes", text: $draft.notes, axis: .vertical).lineLimit(3...10)
            }
        } save: {
            try await workspace.save("/api/applications", draft)
            saved(draft.stage)
            dismiss()
        } reload: {}
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
