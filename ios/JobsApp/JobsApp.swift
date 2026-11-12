import SwiftUI
import UserNotifications

@main
struct JobsApp: App {
    @UIApplicationDelegateAdaptor(NotificationsDelegate.self) private var notificationDelegate

    var body: some Scene {
        WindowGroup { WorkspaceView() }
    }
}

@MainActor
@Observable
final class Workspace {
    private(set) var address = ""
    private(set) var dashboard: Dashboard?
    private(set) var loading = false
    private(set) var saving = false
    private(set) var startingSearch = false
    private(set) var connected = false
    private(set) var lastSyncedAt: Date?
    private(set) var cacheError: String?
    var connectionError: String?
    var searchError: String?
    private var latestLoad = UUID()
    let isSample: Bool
    private var keepOfflineCopy = true
    @ObservationIgnored private var cachedSnapshot: DashboardAPI.Snapshot?

    init(isSample: Bool = false) {
        self.isSample = isSample
        if isSample { dashboard = SampleWorkspace.restore() }
    }

    var canWrite: Bool { isSample || connected }

    func connect(to address: String, verified snapshot: DashboardAPI.Snapshot? = nil) {
        guard self.address != address || snapshot != nil else { return }
        self.address = address
        loading = false
        connected = false
        connectionError = nil
        searchError = nil
        latestLoad = UUID()
        cachedSnapshot = keepOfflineCopy && snapshot == nil ? OfflineWorkspace.load(for: address) : nil
        dashboard = cachedSnapshot?.dashboard
        lastSyncedAt = cachedSnapshot?.syncedAt
        if let snapshot { accept(snapshot) }
    }

    func setOfflineCopyEnabled(_ enabled: Bool) {
        keepOfflineCopy = enabled
        do {
            if !enabled {
                cachedSnapshot = nil
                try OfflineWorkspace.remove()
            }
            cacheError = nil
        } catch {
            cacheError = "The offline copy couldn’t be removed. Try again while your iPhone is unlocked."
        }
    }

    private func accept(_ snapshot: DashboardAPI.Snapshot) {
        dashboard = snapshot.dashboard
        lastSyncedAt = snapshot.syncedAt
        connected = true
        connectionError = nil
        let cacheAge = cachedSnapshot.map { snapshot.syncedAt.timeIntervalSince($0.syncedAt) } ?? .infinity
        if keepOfflineCopy && (cachedSnapshot?.data != snapshot.data || cacheAge >= 60) {
            do {
                try OfflineWorkspace.save(snapshot, for: address)
                cachedSnapshot = snapshot
                cacheError = nil
            } catch {
                cacheError = "This workspace couldn’t be saved for offline access."
            }
        }
    }

    func refresh(replacingInFlight: Bool = false) async {
        guard !isSample, !address.isEmpty, !loading || replacingInFlight else { return }
        let load = UUID()
        latestLoad = load
        loading = true
        defer { if latestLoad == load { loading = false } }
        do {
            let result = try await DashboardAPI.load(at: address)
            guard latestLoad == load, !Task.isCancelled else { return }
            accept(result)
            await MatchNotifications.deliver(result.dashboard.matchAlerts ?? [], server: address)
        } catch {
            guard latestLoad == load, !Task.isCancelled else { return }
            connected = false
            connectionError = DashboardAPI.connectionMessage(for: error)
        }
    }

    func save<T: Encodable>(_ path: String, _ body: T) async throws {
        guard !isSample else {
            throw DashboardAPI.ServerError(status: 0, message: "Connect your Mac to use this feature.")
        }
        guard connected else {
            throw DashboardAPI.ServerError(status: 0, message: "Reconnect to your Mac to save this change.")
        }
        guard !saving else {
            throw DashboardAPI.ServerError(status: 409, message: "Another change is being saved.")
        }
        saving = true
        defer { saving = false }
        do {
            try await DashboardAPI.post(path, at: address, body: body)
        } catch let error as URLError where error.code != .cancelled {
            connected = false
            connectionError = DashboardAPI.connectionMessage(for: error)
            throw DashboardAPI.ServerError(status: 0, message: "Couldn’t confirm the save. Reconnect to check the current values before retrying.")
        }
        await refresh(replacingInFlight: true)
    }

    func updateInterest(for jobID: Int, to state: String, version: Int) async throws {
        guard isSample else {
            try await save("/api/jobs/\(jobID)/interest", InterestUpdate(state: state, version: version))
            return
        }
        try editSampleJob(jobID) { job in
            guard (job.interest?.version ?? 0) == version else { throw Self.sampleConflict }
            job.interest = Job.Interest(state: state, version: version + 1,
                                        updated: Date.now.ISO8601Format())
        }
    }

    func updateTracking(for jobID: Int, draft: TrackingDraft) async throws {
        guard isSample else {
            try await save("/api/jobs/\(jobID)/tracking", draft)
            return
        }
        try editSampleJob(jobID) { job in
            guard job.version == draft.version else { throw Self.sampleConflict }
            job.status = draft.status
            job.applicationDate = draft.applicationDate
            job.followUp = draft.followUp
            job.notes = draft.notes
            job.version += 1
        }
    }

    private static var sampleConflict: DashboardAPI.ServerError {
        DashboardAPI.ServerError(status: 409, message: "This sample job has changed. Reload to edit it.")
    }

    private func editSampleJob(_ id: Int, change: (inout Job) throws -> Void) throws {
        guard var snapshot = dashboard, let index = snapshot.jobs.firstIndex(where: { $0.id == id })
        else { throw DashboardAPI.ServerError(status: 404, message: "Sample job unavailable.") }
        try change(&snapshot.jobs[index])
        try SampleWorkspace.save(snapshot.jobs)
        dashboard = snapshot
    }

    func updateSampleProfile(skills: [String], salaryFloor: Int) throws {
        guard isSample, var snapshot = dashboard else { return }
        try SampleWorkspace.updateProfile(&snapshot, skills: skills, salaryFloor: salaryFloor)
        dashboard = snapshot
    }

    func resetSample() {
        guard isSample else { return }
        dashboard = SampleWorkspace.reset()
    }

    func startSearch() async {
        guard !startingSearch else { return }
        startingSearch = true
        searchError = nil
        defer { startingSearch = false }
        do {
            try await save("/api/run", [String: String]())
        } catch {
            searchError = error.localizedDescription
            if (error as? DashboardAPI.ServerError)?.status == 409 { await refresh() }
        }
    }
}

private struct WorkspaceView: View {
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage("backendURL") private var address = ""
    @AppStorage("keepOfflineWorkspace") private var keepOfflineWorkspace = true
    @State private var workspace = Workspace()
    @State private var editingServer = false

    @State private var sample: Workspace?
    @State private var editingSampleProfile = false
    @State private var confirmingSampleReset = false
    @State private var selectedTab: Tab = .forYou

    private enum Tab: Hashable { case forYou, browse, myJobs, search, settings }

    var body: some View {
        Group {
            if let sample {
                tabs(sample)
            } else if workspace.dashboard != nil {
                tabs(workspace)
            } else {
                NavigationStack {
                    WorkspaceWelcome(hasAddress: !address.isEmpty, loading: workspace.loading,
                                     error: workspace.connectionError) {
                        selectedTab = .forYou
                        sample = Workspace(isSample: true)
                    } connect: {
                        editingServer = true
                    } retry: {
                        Task { await workspace.refresh() }
                    }
                }
            }
        }
        .tint(JobsTheme.accent)
        .sheet(isPresented: $editingServer) {
            ServerSettings(address: address) { newAddress, snapshot in
                if address != newAddress || sample != nil { selectedTab = .forYou }
                sample = nil
                workspace.connect(to: newAddress, verified: snapshot)
                address = newAddress
            }
        }
        .task(id: scenePhase) {
            guard scenePhase == .active else { return }
            workspace.setOfflineCopyEnabled(keepOfflineWorkspace)
            workspace.connect(to: DashboardAPI.serverAddress(address) ?? "")
            await workspace.refresh()
            while !Task.isCancelled {
                let running = workspace.connected && workspace.dashboard?.running == true
                do { try await Task.sleep(for: .seconds(running ? 2 : 10)) }
                catch { break }
                if !workspace.saving && sample == nil {
                    await workspace.refresh()
                }
            }
        }
    }

    private func tabs(_ current: Workspace) -> some View {
        TabView(selection: $selectedTab) {
            NavigationStack {
                ForYou(workspace: current, openBrowse: { selectedTab = .browse },
                       openSettings: { selectedTab = .settings }, openSearch: { selectedTab = .search })
                    .workspaceNotice(current)
            }
            .tabItem { Label("For You", systemImage: "sparkles") }
            .tag(Tab.forYou)
            NavigationStack {
                JobList(workspace: current, openEmployerSearch: {
                    if current.isSample { editingServer = true }
                    else { selectedTab = .search }
                })
                .workspaceNotice(current)
            }
                .tabItem { Label("Browse", systemImage: "magnifyingglass") }
                .tag(Tab.browse)
            NavigationStack { JobList(workspace: current, trackingOnly: true).workspaceNotice(current) }
                .tabItem { Label("My Jobs", systemImage: "bookmark") }
                .tag(Tab.myJobs)
            if !current.isSample {
                NavigationStack { SearchScreen(workspace: current).workspaceNotice(current) }
                    .tabItem { Label("Alerts", systemImage: "bell") }
                    .tag(Tab.search)
                    .badge(current.dashboard?.unreadMatchCount ?? 0)
            }
            NavigationStack {
                if current.isSample {
                    List {
                        Section("Sample Workspace") {
                            Text("These listings are fictional. Your sample progress stays on this iPhone.")
                            Button("Edit Search Profile", systemImage: "slider.horizontal.3") { editingSampleProfile = true }
                            Button("Connect to your Mac", systemImage: "desktopcomputer") { editingServer = true }
                            Button("Reset Sample Progress", role: .destructive) {
                                confirmingSampleReset = true
                            }
                            Button("Leave Sample Workspace") {
                                selectedTab = .forYou
                                sample = nil
                            }
                        }
                    }
                    .navigationTitle("Settings")
                    .sheet(isPresented: $editingSampleProfile) { SampleProfileEditor(workspace: current) }
                    .confirmationDialog("Reset sample progress?", isPresented: $confirmingSampleReset,
                                        titleVisibility: .visible) {
                        Button("Reset Sample Progress", role: .destructive) {
                            current.resetSample()
                            // Recreate the sample tabs so stale Undo actions cannot affect a new session.
                            sample = nil
                            selectedTab = .forYou
                        }
                    } message: {
                        Text("This restores the sample profile and clears sample application changes.")
                    }
                } else {
                    PreferencesScreen(workspace: current, keepOfflineCopy: $keepOfflineWorkspace,
                                      editServer: { editingServer = true }) {
                        selectedTab = .forYou
                        sample = Workspace(isSample: true)
                    }
                    .workspaceNotice(current)
                }
            }
            .tabItem { Label("Settings", systemImage: "gearshape") }
            .tag(Tab.settings)
        }
        .id(current.isSample ? "sample" : current.address)
        .onChange(of: keepOfflineWorkspace) { _, enabled in
            workspace.setOfflineCopyEnabled(enabled)
            if enabled { Task { await workspace.refresh() } }
        }
    }
}

extension View {
    @MainActor
    func workspaceNotice(_ current: Workspace) -> some View {
        safeAreaInset(edge: .top, spacing: 0) {
            if current.isSample {
                Label("Sample workspace · Fictional listings", systemImage: "eye")
                    .font(.footnote.weight(.semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                    .background(.regularMaterial)
            } else if !current.connected {
                VStack(spacing: 3) {
                    Label("Offline · Read-only", systemImage: "wifi.slash")
                        .font(.footnote.weight(.semibold))
                    if let synced = current.lastSyncedAt {
                        Text("Last synced \(synced.formatted(date: .abbreviated, time: .shortened))")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Button(current.loading ? "Connecting…" : "Retry Connection") {
                        Task { await current.refresh() }
                    }
                    .font(.footnote.weight(.semibold))
                    .disabled(current.loading)
                }
                .padding(.vertical, 8)
                .frame(maxWidth: .infinity)
                .background(.regularMaterial)
            }
        }
    }
}

private struct ServerSettings: View {
    @Environment(\.dismiss) private var dismiss
    @State var address: String
    let save: (String, DashboardAPI.Snapshot) -> Void
    @State private var pendingAddress: String?
    @State private var failure: String?

    private var checking: Bool { pendingAddress != nil }

    var body: some View {
        NavigationStack {
            Form {
                Section("Mac workspace address") {
                    TextField("http://your-mac.local:8084", text: $address)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .accessibilityIdentifier("serverAddress")
                        .disabled(checking)
                    Text("Enter your Mac’s private address. A hostname or IP alone uses port 8084.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                if checking { ProgressView("Checking workspace…") }
                if let failure { Text(failure).foregroundStyle(.red) }
            }
            .navigationTitle("Server Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Connect") {
                        failure = nil
                        pendingAddress = DashboardAPI.serverAddress(address)
                    }
                        .disabled(checking || DashboardAPI.serverAddress(address) == nil)
                }
            }
        }
        .task(id: pendingAddress) {
            if let pendingAddress { await connect(pendingAddress) }
        }
    }

    private func connect(_ normalized: String) async {
        defer { pendingAddress = nil }
        do {
            let snapshot = try await DashboardAPI.load(at: normalized)
            try Task.checkCancellation()
            save(normalized, snapshot)
            dismiss()
        } catch {
            guard !Task.isCancelled else { return }
            failure = DashboardAPI.connectionMessage(for: error)
        }
    }
}
